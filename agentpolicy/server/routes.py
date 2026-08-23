"""API Routes for AgentPolicy Server."""

from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from ..policy.models import BuyerRequest
from ..policy.compiler import PolicyCompiler, CompiledPolicyBundle
from ..policy.dsl import PolicyDSL
from ..gateway.authorizer import AuthorizationGateway
from ..negotiation.orchestrator import BoundedNegotiationOrchestrator
from ..memory.audit_logger import AuditLogger
from ..payments.razorpay_client import RazorpayClient
from ..payments.x402_handler import X402Handler


def create_router(
    bundle_ref: Dict[str, CompiledPolicyBundle],
    gateway: AuthorizationGateway,
    audit_logger: AuditLogger,
    razorpay_client: RazorpayClient
) -> APIRouter:
    router = APIRouter()

    # 1. ACP DISCOVERY
    @router.get("/.well-known/agent-commerce.json")
    async def get_acp_manifest():
        bundle = bundle_ref["bundle"]
        return bundle.acp_manifest

    @router.get("/x402-config.json")
    async def get_x402_config():
        bundle = bundle_ref["bundle"]
        return bundle.x402_config

    @router.get("/api/policy/current")
    async def get_current_policy():
        bundle = bundle_ref["bundle"]
        return {
            "policy": bundle.policy.model_dump(),
            "bounds": bundle.bounds.model_dump(),
            "policy_hash": bundle.policy_hash,
            "version": bundle.version
        }

    @router.put("/api/policy")
    async def update_policy(payload: Dict[str, Any]):
        """Update and live-recompile merchant policy."""
        try:
            if "yaml" in payload:
                new_policy = PolicyDSL.load_from_yaml(payload["yaml"])
            else:
                new_policy = PolicyDSL.from_dict(payload.get("policy", payload))

            new_bundle = PolicyCompiler.compile(new_policy)
            bundle_ref["bundle"] = new_bundle

            audit_logger.record(
                atom_type="policy_recompiled",
                policy_version=new_bundle.version,
                policy_hash=new_bundle.policy_hash,
                payload={
                    "merchant": new_bundle.policy.merchant,
                    "max_autonomous_inr": new_bundle.bounds.max_autonomous_inr,
                    "discount_ceiling_pct": new_bundle.bounds.discount_ceiling_pct,
                    "floor_prices": new_bundle.bounds.floor_prices
                }
            )
            return {"status": "updated", "version": new_bundle.version, "hash": new_bundle.policy_hash}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Policy update failed: {str(e)}")

    # 2. BOUNDED NEGOTIATION & AUTHORIZATION
    @router.post("/api/agent/negotiate")
    async def negotiate(request: BuyerRequest, response: Response):
        bundle = bundle_ref["bundle"]
        bounds = bundle.bounds

        # Step 1: Bounded Negotiation (LLM proposes, code clamps)
        orchestrator = BoundedNegotiationOrchestrator(bounds)
        negotiation_result = orchestrator.negotiate(request)

        # Record negotiation atom
        audit_logger.record(
            atom_type="negotiation_round",
            policy_version=bounds.policy_version,
            policy_hash=bundle.policy_hash,
            payload={
                "request": request.model_dump(),
                "result": negotiation_result.model_dump()
            }
        )

        if negotiation_result.status == "declined":
            response.status_code = 403
            return {
                "status": "declined",
                "reason": negotiation_result.message,
                "policy_version": bounds.policy_version
            }

        # Step 2: 4-Layer Authorization Check
        auth_outcome = gateway.authorize(request, negotiation_result, bounds)

        # Record authorization atom
        audit_logger.record(
            atom_type="authorization_decision",
            policy_version=bounds.policy_version,
            policy_hash=bundle.policy_hash,
            payload={
                "buyer_id": request.buyer_id,
                "status": auth_outcome.status,
                "reason": auth_outcome.reason,
                "code": auth_outcome.code,
                "http_status": auth_outcome.http_status_code
            }
        )

        response.status_code = auth_outcome.http_status_code

        if auth_outcome.status == "denied":
            return {
                "status": "denied",
                "code": auth_outcome.code,
                "reason": auth_outcome.reason,
                "policy_version": bounds.policy_version
            }

        if auth_outcome.status == "pending_approval":
            return {
                "status": "pending_approval",
                "code": auth_outcome.code,
                "approval_url": auth_outcome.approval_url,
                "approval_id": auth_outcome.approval_record.id if auth_outcome.approval_record else None,
                "reason": auth_outcome.reason,
                "counter_price_inr": negotiation_result.final_price_inr,
                "discount_pct": negotiation_result.discount_pct,
                "policy_version": bounds.policy_version,
                "message": "Transaction parameters require merchant human sign-off (HTTP 202 Accepted)"
            }

        # Status: Authorized
        return {
            "status": negotiation_result.status,
            "counter_price_inr": negotiation_result.final_price_inr,
            "discount_pct": negotiation_result.discount_pct,
            "terms": negotiation_result.terms,
            "policy_version": bounds.policy_version,
            "message": negotiation_result.message,
            "razorpay_payload": auth_outcome.razorpay_payload
        }

    # 3. PAYMENT & SETTLEMENT
    class PayRequest(BaseModel):
        product_id: str
        quantity: int
        amount_inr: int
        currency: str = "INR"
        x402_proof: Optional[str] = None
        negotiation_id: Optional[str] = None
        buyer_id: str = "agent-buyer-01"

    @router.post("/api/agent/pay")
    async def pay(payload: PayRequest, response: Response):
        bundle = bundle_ref["bundle"]

        # Validate x402 payment proof
        if payload.x402_proof:
            valid, msg = X402Handler.verify_proof(payload.x402_proof, payload.amount_inr, bundle.policy.merchant)
            if not valid:
                response.status_code = 402
                return X402Handler.format_402_challenge(payload.amount_inr, bundle.policy.merchant, "/api/agent/pay")

        # Create Razorpay Order
        order = razorpay_client.create_order(
            amount_inr=payload.amount_inr,
            currency=payload.currency,
            notes={
                "buyer_id": payload.buyer_id,
                "product_id": payload.product_id,
                "quantity": payload.quantity,
                "policy_version": bundle.version
            }
        )

        # Mock capture payment
        capture_event = razorpay_client.capture_payment_mock(order["id"], payload.amount_inr)

        # Record Settlement Atom
        atom = audit_logger.record(
            atom_type="settlement",
            policy_version=bundle.version,
            policy_hash=bundle.policy_hash,
            payload={
                "authorization_id": payload.negotiation_id or order["id"],
                "order_id": order["id"],
                "amount_inr": payload.amount_inr,
                "buyer_id": payload.buyer_id,
                "payment_id": capture_event["payload"]["payment"]["entity"]["id"],
                "status": "captured",
                "x402_verified": bool(payload.x402_proof)
            }
        )

        return {
            "status": "settled",
            "razorpay_order_id": order["id"],
            "razorpay_payment_id": capture_event["payload"]["payment"]["entity"]["id"],
            "amount_inr": payload.amount_inr,
            "currency": payload.currency,
            "audit_atom_id": atom.atom_id,
            "fulfillment_status": "fulfilled",
            "access_token": f"token_{uuid_token()}"
        }

    # 4. APPROVALS API
    @router.get("/api/approvals/all")
    async def get_all_approvals():
        return [
            {
                "id": a.id,
                "status": a.status,
                "request": a.request,
                "proposed_deal": a.proposed_deal,
                "trigger_reasons": a.trigger_reasons,
                "created_at": a.created_at,
                "decision_by": a.decision_by,
                "decision_notes": a.decision_notes
            }
            for a in gateway.approval_bridge.list_all()
        ]

    class DecisionRequest(BaseModel):
        decision: str  # "approved", "rejected", "countered"
        decided_by: str = "finance_lead"
        notes: str = ""
        counter_price_inr: Optional[int] = None

    @router.post("/api/approvals/{approval_id}/decide")
    async def decide_approval(approval_id: str, payload: DecisionRequest):
        rec = gateway.approval_bridge.decide(
            approval_id=approval_id,
            decision=payload.decision,
            decided_by=payload.decided_by,
            notes=payload.notes
        )
        if not rec:
            raise HTTPException(status_code=404, detail="Approval record not found")

        audit_logger.record(
            atom_type="human_approval",
            policy_version=rec.policy_version,
            policy_hash=bundle_ref["bundle"].policy_hash,
            payload={
                "approval_id": approval_id,
                "decision": payload.decision,
                "decided_by": payload.decided_by,
                "notes": payload.notes
            }
        )
        return {"status": "success", "approval": rec.__dict__}

    # 5. AUDIT LOG REPLAY
    @router.get("/api/audit/replay")
    async def replay_audit():
        atoms = audit_logger.replay()
        contradictions = audit_logger.detect_contradictions()
        return {
            "total_atoms": len(atoms),
            "atoms": atoms,
            "contradictions": contradictions
        }

    # 6. ADVERSARIAL ATTACK TEST RUNNER
    @router.post("/api/test/adversarial")
    async def run_adversarial_suite():
        from ..examples_helper import run_attack_suite_helper
        results = run_attack_suite_helper(bundle_ref["bundle"], gateway)
        return {"results": results}

    return router


def uuid_token():
    import uuid
    return uuid.uuid4().hex[:16]
