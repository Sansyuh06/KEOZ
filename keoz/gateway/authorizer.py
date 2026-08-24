"""4-Layer Authorization Gateway for Agentic Commerce with Metrics Integration."""

from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from .agent_identity import AgentIdentityVerifier, AgentIdentity
from .composed_validator import ComposedDealValidator, ValidationResult
from .approvals import ApprovalBridge, ApprovalRecord
from ..policy.models import NegotiationBounds, NegotiationResult, BuyerRequest
from ..metrics import metrics


@dataclass
class AuthorizationOutcome:
    authorized: bool
    status: str                         # "authorized", "pending_approval", "denied"
    http_status_code: int               # 200, 202, 401, 403
    reason: Optional[str] = None
    code: Optional[str] = None
    approval_record: Optional[ApprovalRecord] = None
    approval_url: Optional[str] = None
    agent_identity: Optional[AgentIdentity] = None
    composed_validation: Optional[ValidationResult] = None
    razorpay_payload: Optional[Dict[str, Any]] = None


class AuthorizationGateway:
    """
    Pre-Razorpay Authorization Gateway implementing 4 deterministic defense layers:
    1. Agent Identity & Spending Cap
    2. Per-Parameter Policy Bounds
    3. Composed Deal Margin Floor
    4. Human Approval Routing
    """

    def __init__(
        self,
        identity_verifier: Optional[AgentIdentityVerifier] = None,
        composed_validator: Optional[ComposedDealValidator] = None,
        approval_bridge: Optional[ApprovalBridge] = None
    ):
        self.identity_verifier = identity_verifier or AgentIdentityVerifier()
        self.composed_validator = composed_validator or ComposedDealValidator()
        self.approval_bridge = approval_bridge or ApprovalBridge()

    def evaluate_human_approval_triggers(
        self,
        request: BuyerRequest,
        result: NegotiationResult,
        bounds: NegotiationBounds
    ) -> List[str]:
        """Check if request hits any merchant-configured human approval escalation triggers."""
        triggers = []
        total_amount = (result.final_price_inr or 0) * result.quantity

        # Rule 1: Amount exceeds autonomous ceiling
        if total_amount > bounds.max_autonomous_inr:
            triggers.append(f"Transaction amount (₹{total_amount:,}) exceeds autonomous limit (₹{bounds.max_autonomous_inr:,})")

        # Rule 2: Customer Tier is new
        if request.customer_tier.lower() == "new":
            triggers.append("First-time / new customer tier requires initial merchant verification")

        # Rule 3: Payment instrument is net terms / invoice
        payment_terms = str(request.terms.get("payment", request.terms.get("instrument", ""))).lower()
        if "net_" in payment_terms or "invoice" in payment_terms:
            triggers.append(f"Requested payment terms ({payment_terms}) require credit & finance approval")

        # Rule 4: Explicit product requirement
        if result.requires_human_approval and result.approval_reason:
            triggers.append(result.approval_reason)

        return triggers

    def authorize(
        self,
        request: BuyerRequest,
        result: NegotiationResult,
        bounds: NegotiationBounds
    ) -> AuthorizationOutcome:
        """Execute 4-layer authorization pipeline."""
        deal_value = (result.final_price_inr or 0) * result.quantity
        metrics.update_policy_version(bounds.policy_version)

        # LAYER 1: AGENT IDENTITY & SPENDING CAP
        identity: Optional[AgentIdentity] = None
        if request.agent_token:
            id_res = self.identity_verifier.verify(request.agent_token, required_amount_inr=deal_value)
            if not id_res.verified:
                metrics.record_attack(id_res.code or "AGENT_IDENTITY_FAILED", blocked=True, description=id_res.reason, amount_inr=deal_value)
                return AuthorizationOutcome(
                    authorized=False,
                    status="denied",
                    http_status_code=401,
                    reason=id_res.reason,
                    code=id_res.code or "AGENT_IDENTITY_FAILED"
                )
            identity = id_res.identity

        # LAYER 2: PER-PARAMETER BOUNDS
        if not bounds.validate(result):
            metrics.record_attack("PARAMETER_BOUNDS_VIOLATION", blocked=True, description=f"Parameter violation on {result.product_id}", amount_inr=deal_value)
            return AuthorizationOutcome(
                authorized=False,
                status="denied",
                http_status_code=403,
                reason=f"Proposal violates individual parameter bounds for product {result.product_id}",
                code="PARAMETER_BOUNDS_VIOLATION"
            )

        # LAYER 3: COMPOSED DEAL MARGIN FLOOR
        final_price = result.final_price_inr or bounds.floor_prices.get(result.product_id, 0)
        margin_res = self.composed_validator.validate(
            product_id=result.product_id,
            price_inr=final_price,
            quantity=result.quantity,
            terms=result.terms or request.terms,
            bounds=bounds
        )
        if not margin_res.passed:
            metrics.record_attack("MARGIN_FLOOR_VIOLATION", blocked=True, description="Composed deal margin drain attack blocked", amount_inr=deal_value)
            return AuthorizationOutcome(
                authorized=False,
                status="denied",
                http_status_code=403,
                reason=margin_res.reason,
                code=margin_res.code,
                composed_validation=margin_res
            )

        # LAYER 4: HUMAN APPROVAL ROUTING
        triggers = self.evaluate_human_approval_triggers(request, result, bounds)
        if triggers:
            record, approval_url = self.approval_bridge.create_approval_request(
                buyer_request=request,
                proposed_result=result,
                trigger_reasons=triggers,
                policy_version=bounds.policy_version
            )
            metrics.record_ai_transaction(auto_closed=False, escalated=True, amount_inr=deal_value)
            return AuthorizationOutcome(
                authorized=False,
                status="pending_approval",
                http_status_code=202,  # HTTP 202 Accepted for async human approval
                reason="; ".join(triggers),
                code="REQUIRES_HUMAN_APPROVAL",
                approval_record=record,
                approval_url=approval_url,
                agent_identity=identity,
                composed_validation=margin_res
            )

        # ALL 4 LAYERS PASSED -> AUTHORIZED FOR RAZORPAY
        metrics.record_ai_transaction(auto_closed=True, escalated=False, amount_inr=deal_value)
        razorpay_payload = {
            "amount": deal_value * 100,  # Razorpay amounts in paise
            "currency": "INR",
            "receipt": f"rcpt_{result.product_id}_{result.quantity}",
            "notes": {
                "policy_version": bounds.policy_version,
                "buyer_id": request.buyer_id,
                "product_id": result.product_id,
                "quantity": result.quantity,
                "effective_margin": margin_res.effective_margin
            }
        }

        return AuthorizationOutcome(
            authorized=True,
            status="authorized",
            http_status_code=200,
            reason="All 4 authorization layers verified successfully",
            agent_identity=identity,
            composed_validation=margin_res,
            razorpay_payload=razorpay_payload
        )
