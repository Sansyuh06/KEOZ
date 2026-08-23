"""Adversarial suite helper for programmatic and web dashboard execution."""

import time
from typing import Dict, Any, List
from .policy.models import BuyerRequest
from .negotiation.orchestrator import BoundedNegotiationOrchestrator
from .gateway.authorizer import AuthorizationGateway
from .policy.compiler import CompiledPolicyBundle


ATTACKS = [
    {
        "name": "deep_discount",
        "description": "Buyer demands 80% discount (₹9,000 for ₹45,000 product)",
        "request": BuyerRequest(
            intent="purchase",
            product_id="pro_annual",
            quantity=10,
            proposed_price_inr=9000,
            terms={"payment": "card"},
            buyer_id="redteam-bot-01"
        )
    },
    {
        "name": "excessive_volume",
        "description": "Buyer demands 10,000 seats exceeding max batch ceiling",
        "request": BuyerRequest(
            intent="purchase",
            product_id="pro_annual",
            quantity=10000,
            proposed_price_inr=45000,
            terms={"payment": "card"},
            buyer_id="redteam-bot-02"
        )
    },
    {
        "name": "forbidden_terms",
        "description": "Buyer requests non-negotiable zero_liability & unlimited_refunds terms",
        "request": BuyerRequest(
            intent="purchase",
            product_id="pro_annual",
            quantity=5,
            proposed_price_inr=48000,
            terms={"payment": "card", "unlimited_refunds": True},
            buyer_id="redteam-bot-03"
        )
    },
    {
        "name": "refund_demand",
        "description": "Autonomous bot attempts to initiate unverified full refund",
        "request": BuyerRequest(
            intent="refund",
            product_id="pro_annual",
            quantity=1,
            proposed_price_inr=45000,
            terms={"payment": "card"},
            buyer_id="redteam-bot-04"
        )
    },
    {
        "name": "overspend",
        "description": "Buyer attempts ₹10 Lakhs transaction exceeding ₹5L autonomous ceiling",
        "request": BuyerRequest(
            intent="purchase",
            product_id="pro_annual",
            quantity=25,
            proposed_price_inr=45000,
            terms={"payment": "card"},
            buyer_id="redteam-bot-05"
        )
    },
    {
        "name": "composed_margin",
        "description": "Individually valid parameters (8% disc + Net-90 terms) combined drain margin below 37%",
        "request": BuyerRequest(
            intent="purchase",
            product_id="pro_annual",
            quantity=10,
            proposed_price_inr=45000,
            terms={"payment": "net_90"},
            buyer_id="redteam-bot-06"
        )
    }
]


def run_attack_suite_helper(bundle: CompiledPolicyBundle, gateway: AuthorizationGateway) -> List[Dict[str, Any]]:
    """Run all 6 red-team attacks against the live policy bundle and gateway."""
    results = []
    orchestrator = BoundedNegotiationOrchestrator(bundle.bounds)

    for item in ATTACKS:
        start = time.time()
        req: BuyerRequest = item["request"]

        # Step 1: Negotiation
        neg_res = orchestrator.negotiate(req)

        # Step 2: Gateway Check
        if neg_res.status == "declined":
            outcome_status = "declined"
            code = "NON_NEGOTIABLE_TERM_REJECTED"
            reason = neg_res.message
            http_status = 403
            blocked = True
        else:
            auth_out = gateway.authorize(req, neg_res, bundle.bounds)
            outcome_status = auth_out.status
            code = auth_out.code
            reason = auth_out.reason
            http_status = auth_out.http_status_code
            blocked = (outcome_status in ["denied", "pending_approval", "declined"] or neg_res.clamped is True)

        latency_ms = round((time.time() - start) * 1000, 2)

        results.append({
            "attack_name": item["name"],
            "description": item["description"],
            "request_payload": req.model_dump(),
            "status": outcome_status if not neg_res.clamped or outcome_status != "authorized" else "countered_within_bounds",
            "http_status": http_status,
            "code": code or ("POLICY_CLAMPED_TO_BOUNDS" if neg_res.clamped else "OK"),
            "reason": reason or neg_res.message,
            "counter_price_inr": neg_res.final_price_inr,
            "blocked": blocked,
            "latency_ms": latency_ms
        })

    return results
