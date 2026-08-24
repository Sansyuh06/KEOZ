"""API Routes for KEOZ Merchant Command Center & Gateway."""

import json
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Response, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel

from ..policy.models import BuyerRequest
from ..policy.compiler import PolicyCompiler, CompiledPolicyBundle
from ..policy.dsl import PolicyDSL
from ..gateway.authorizer import AuthorizationGateway
from ..negotiation.orchestrator import BoundedNegotiationOrchestrator
from ..memory.audit_logger import AuditLogger
from ..payments.razorpay_client import RazorpayClient
from ..payments.x402_handler import X402Handler
from ..registry import MerchantRegistry, registry
from ..metrics import metrics


def create_router(
    merchant_registry: Optional[MerchantRegistry] = None,
    gateway: Optional[AuthorizationGateway] = None,
    audit_logger: Optional[AuditLogger] = None,
    razorpay_client: Optional[RazorpayClient] = None
) -> APIRouter:
    router = APIRouter()
    reg = merchant_registry or registry
    logger = audit_logger or AuditLogger()
    rzp = razorpay_client or RazorpayClient()
    gw = gateway or AuthorizationGateway()

    # 1. WEBSOCKET METRICS BROADCAST
    @router.websocket("/ws/metrics")
    async def websocket_metrics(websocket: WebSocket):
        await websocket.accept()
        q = metrics.subscribe()
        try:
            # Send initial snapshot
            await websocket.send_text(json.dumps(metrics.get_snapshot_dict()))
            while True:
                message = await q.get()
                await websocket.send_text(message)
        except WebSocketDisconnect:
            metrics.unsubscribe(q)
        except Exception:
            metrics.unsubscribe(q)

    # 2. METRICS REST SNAPSHOT
    @router.get("/api/metrics")
    async def get_metrics_snapshot():
        return metrics.get_snapshot_dict()

    # 3. ACP & x402 DISCOVERY
    @router.get("/.well-known/agent-commerce.json")
    async def get_acp_manifest(merchant_id: Optional[str] = None):
        bundle = reg.get_bundle(merchant_id)
        return bundle.acp_manifest

    @router.get("/x402-config.json")
    async def get_x402_config(merchant_id: Optional[str] = None):
        bundle = reg.get_bundle(merchant_id)
        return bundle.x402_config

    # 4. MULTI-MERCHANT REGISTRY APIS
    @router.get("/api/merchants")
    async def list_merchants():
        return {
            "merchants": reg.list_merchants(),
            "default": reg.get_default_merchant()
        }

    @router.post("/api/merchants")
    async def create_or_register_merchant(payload: Dict[str, Any]):
        merchant_id = payload.get("merchant_id")
        policy_yaml = payload.get("policy_yaml") or payload.get("yaml")
        make_default = payload.get("make_default", False)
        if not merchant_id or not policy_yaml:
            raise HTTPException(status_code=400, detail="merchant_id and policy_yaml are required")
        bundle = await reg.register_merchant(merchant_id, policy_yaml, make_default)
        return {
            "merchant_id": merchant_id,
            "version": bundle.version,
            "hash": bundle.policy_hash,
            "status": "registered"
        }

    @router.get("/api/merchants/{merchant_id}/policy")
    async def get_merchant_policy(merchant_id: str):
        bundle = reg.get_bundle(merchant_id)
        return {
            "merchant_id": merchant_id,
            "policy": bundle.policy.model_dump(),
            "bounds": bundle.bounds.model_dump(),
            "policy_hash": bundle.policy_hash,
            "version": bundle.version,
            "yaml": reg.get_policy_yaml(merchant_id)
        }

    @router.put("/api/merchants/{merchant_id}/policy")
    async def update_merchant_policy(merchant_id: str, payload: Dict[str, Any]):
        """Update and live-recompile merchant policy for a specific merchant."""
        try:
            old_bundle = reg.get_bundle(merchant_id)
            old_version = old_bundle.version

            if "yaml" in payload:
                policy_yaml = payload["yaml"]
                new_bundle = await reg.update_policy(merchant_id, policy_yaml)
            else:
                new_policy = PolicyDSL.from_dict(payload.get("policy", payload))
                import yaml
                policy_yaml = yaml.dump(new_policy.model_dump())
                new_bundle = await reg.update_policy(merchant_id, policy_yaml)

            logger.record(
                atom_type="policy_recompiled",
                policy_version=new_bundle.version,
                policy_hash=new_bundle.policy_hash,
                payload={
                    "merchant": merchant_id,
                    "old_version": old_version,
                    "new_version": new_bundle.version,
                    "max_autonomous_inr": new_bundle.bounds.max_autonomous_inr,
                    "discount_ceiling_pct": new_bundle.bounds.discount_ceiling_pct,
                    "floor_prices": new_bundle.bounds.floor_prices
                }
            )
            metrics.update_policy_version(new_bundle.version)
            return {
                "status": "updated",
                "merchant_id": merchant_id,
                "version": new_bundle.version,
                "hash": new_bundle.policy_hash
            }
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Policy update failed: {str(e)}")

    # 5. CURRENT POLICY (Default Merchant)
    @router.get("/api/policy/current")
    async def get_current_policy(merchant_id: Optional[str] = None):
        bundle = reg.get_bundle(merchant_id)
        return {
            "policy": bundle.policy.model_dump(),
            "bounds": bundle.bounds.model_dump(),
            "policy_hash": bundle.policy_hash,
            "version": bundle.version,
            "yaml": reg.get_policy_yaml(merchant_id)
        }

    @router.put("/api/policy")
    async def update_current_policy(payload: Dict[str, Any], merchant_id: Optional[str] = None):
        m_id = merchant_id or reg.get_default_merchant() or "acme-saas"
        return await update_merchant_policy(m_id, payload)

    # 6. BOUNDED NEGOTIATION & AUTHORIZATION
    @router.post("/api/agent/negotiate")
    async def negotiate(request: BuyerRequest, response: Response, merchant_id: Optional[str] = Query(None)):
        bundle = reg.get_bundle(merchant_id)
        bounds = bundle.bounds

        # Step 1: Bounded Negotiation (LLM proposes, code clamps)
        orchestrator = BoundedNegotiationOrchestrator(bounds)
        negotiation_result = orchestrator.negotiate(request)

        # Record negotiation atom
        logger.record(
            atom_type="negotiation_round",
            policy_version=bounds.policy_version,
            policy_hash=bundle.policy_hash,
            payload={
                "merchant": bundle.policy.merchant,
                "request": request.model_dump(),
                "result": negotiation_result.model_dump()
            }
        )

        if negotiation_result.status == "declined":
            response.status_code = 403
            metrics.record_attack("NON_NEGOTIABLE_TERM_REJECTED", blocked=True, description=negotiation_result.message)
            return {
                "status": "declined",
                "reason": negotiation_result.message,
                "policy_version": bounds.policy_version,
                "merchant": bundle.policy.merchant
            }

        # Step 2: 4-Layer Authorization Check
        auth_outcome = gw.authorize(request, negotiation_result, bounds)

        # Record authorization atom
        logger.record(
            atom_type="authorization_decision",
            policy_version=bounds.policy_version,
            policy_hash=bundle.policy_hash,
            payload={
                "merchant": bundle.policy.merchant,
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
                "policy_version": bounds.policy_version,
                "merchant": bundle.policy.merchant
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
                "merchant": bundle.policy.merchant,
                "message": "Transaction parameters require merchant human sign-off (HTTP 202 Accepted)"
            }

        # Status: Authorized
        return {
            "status": negotiation_result.status,
            "counter_price_inr": negotiation_result.final_price_inr,
            "discount_pct": negotiation_result.discount_pct,
            "terms": negotiation_result.terms,
            "policy_version": bounds.policy_version,
            "merchant": bundle.policy.merchant,
            "message": negotiation_result.message,
            "razorpay_payload": auth_outcome.razorpay_payload
        }

    # 7. PAYMENT & SETTLEMENT
    class PayRequest(BaseModel):
        product_id: str
        quantity: int
        amount_inr: int
        currency: str = "INR"
        x402_proof: Optional[str] = None
        negotiation_id: Optional[str] = None
        buyer_id: str = "agent-buyer-01"
        merchant_id: Optional[str] = None

    @router.post("/api/agent/pay")
    async def pay(payload: PayRequest, response: Response):
        bundle = reg.get_bundle(payload.merchant_id)

        # Validate x402 payment proof
        if payload.x402_proof:
            valid, msg = X402Handler.verify_proof(payload.x402_proof, payload.amount_inr, bundle.policy.merchant)
            if not valid:
                response.status_code = 402
                return X402Handler.format_402_challenge(payload.amount_inr, bundle.policy.merchant, "/api/agent/pay")

        # Create Razorpay Order
        order = rzp.create_order(
            amount_inr=payload.amount_inr,
            currency=payload.currency,
            notes={
                "buyer_id": payload.buyer_id,
                "product_id": payload.product_id,
                "quantity": payload.quantity,
                "policy_version": bundle.version,
                "merchant": bundle.policy.merchant
            }
        )

        # Mock capture payment
        capture_event = rzp.capture_payment_mock(order["id"], payload.amount_inr)

        # Record Settlement Atom
        atom = logger.record(
            atom_type="settlement",
            policy_version=bundle.version,
            policy_hash=bundle.policy_hash,
            payload={
                "merchant": bundle.policy.merchant,
                "authorization_id": payload.negotiation_id or order["id"],
                "order_id": order["id"],
                "amount_inr": payload.amount_inr,
                "buyer_id": payload.buyer_id,
                "payment_id": capture_event["payload"]["payment"]["entity"]["id"],
                "status": "captured",
                "x402_verified": bool(payload.x402_proof)
            }
        )

        # Record metrics
        metrics.record_ai_transaction(auto_closed=True, escalated=False, amount_inr=payload.amount_inr)

        return {
            "status": "settled",
            "merchant": bundle.policy.merchant,
            "razorpay_order_id": order["id"],
            "razorpay_payment_id": capture_event["payload"]["payment"]["entity"]["id"],
            "amount_inr": payload.amount_inr,
            "currency": payload.currency,
            "audit_atom_id": atom.atom_id,
            "fulfillment_status": "fulfilled",
            "access_token": f"token_{uuid_token()}"
        }

    # 8. APPROVALS API
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
                "decided_by": a.decided_by,
                "decided_at": a.decided_at,
                "decision_notes": a.decision_notes,
                "counter_terms": a.counter_terms
            }
            for a in gw.approval_bridge.list_all()
        ]

    class DecisionRequest(BaseModel):
        decision: str  # "approved", "rejected", "countered"
        decided_by: str = "merchant_finance_lead"
        notes: str = ""
        counter_terms: Optional[Dict[str, Any]] = None

    @router.post("/api/approvals/{approval_id}/decide")
    async def decide_approval(approval_id: str, payload: DecisionRequest):
        rec = gw.approval_bridge.decide(
            approval_id=approval_id,
            decision=payload.decision,
            decided_by=payload.decided_by,
            notes=payload.notes,
            counter_terms=payload.counter_terms
        )
        if not rec:
            raise HTTPException(status_code=404, detail="Approval record not found")

        bundle = reg.get_bundle()
        logger.record(
            atom_type="human_approval",
            policy_version=rec.policy_version,
            policy_hash=bundle.policy_hash,
            payload={
                "approval_id": approval_id,
                "decision": payload.decision,
                "decided_by": payload.decided_by,
                "notes": payload.notes,
                "counter_terms": payload.counter_terms
            }
        )

        if payload.decision == "approved":
            amount = rec.proposed_deal.get("final_price_inr", 45000) * rec.request.get("quantity", 1)
            metrics.record_ai_transaction(auto_closed=False, escalated=False, amount_inr=amount)

        return {"status": "success", "approval": rec.__dict__}

    # 9. AUDIT LOG REPLAY
    @router.get("/api/audit/replay")
    async def replay_audit(since_seconds: Optional[float] = None, limit: int = 1000):
        atoms = logger.replay(since_seconds=since_seconds, limit=limit)
        contradictions = logger.detect_contradictions()
        return {
            "total_atoms": len(atoms),
            "atoms": atoms,
            "contradictions": contradictions
        }

    # 10. ADVERSARIAL ATTACK TEST RUNNER
    @router.post("/api/test/adversarial")
    async def run_adversarial_suite(merchant_id: Optional[str] = Query(None)):
        from ..examples_helper import run_attack_suite_helper
        bundle = reg.get_bundle(merchant_id)
        results = run_attack_suite_helper(bundle, gw)
        for atk in results:
            metrics.record_attack(
                attack_type=atk["attack_name"],
                blocked=atk["blocked"],
                description=atk["description"]
            )
        return {"results": results, "merchant": bundle.policy.merchant}

    return router


def uuid_token():
    import uuid
    return uuid.uuid4().hex[:16]
