"""Comprehensive Red-Team Adversarial Attack Suite for AgentPolicy.

Verifies that all 6 attack vectors are strictly neutralized by deterministic code,
return the expected reason codes, and NEVER leak secret commercial numbers (floor prices,
unit COGS, or margin percentages) in external responses.
"""

import pytest
from pathlib import Path
from agentpolicy.policy.compiler import PolicyCompiler
from agentpolicy.policy.dsl import PolicyDSL
from agentpolicy.policy.models import BuyerRequest
from agentpolicy.gateway.authorizer import AuthorizationGateway
from agentpolicy.negotiation.orchestrator import BoundedNegotiationOrchestrator
from agentpolicy.examples_helper import run_attack_suite_helper

SECRET_FLOOR_PRICE = 45000
SECRET_UNIT_COST = 28350
SECRET_MARGIN_FLOOR = 0.37


@pytest.fixture
def policy_bundle_and_gateway():
    yaml_path = Path("examples/agentpolicy.yaml")
    policy = PolicyDSL.load_from_yaml(yaml_path)
    bundle = PolicyCompiler.compile(policy)
    gateway = AuthorizationGateway()
    return bundle, gateway


def _assert_no_secret_leaks(payload_str: str):
    """Assert that merchant internal secrets are not leaked to external buyers."""
    assert str(SECRET_UNIT_COST) not in payload_str, f"Secret unit cost {SECRET_UNIT_COST} leaked in payload!"
    assert "28,350" not in payload_str, "Secret unit cost leaked in payload!"
    assert "37%" not in payload_str, "Secret margin percentage 37% leaked in payload!"
    assert "0.37" not in payload_str, "Secret margin fraction 0.37 leaked in payload!"


# ATTACK 1: DEEP DISCOUNT DRAIN
def test_attack_deep_discount(policy_bundle_and_gateway):
    """Buyer demands 80% discount (₹9,000 for ₹45,000 floor / ₹50,000 list)."""
    bundle, gateway = policy_bundle_and_gateway
    orchestrator = BoundedNegotiationOrchestrator(bundle.bounds)

    req = BuyerRequest(
        intent="purchase",
        product_id="pro_annual",
        quantity=10,
        proposed_price_inr=9000,
        terms={"payment": "card"},
        buyer_id="redteam-deep-discount"
    )

    result = orchestrator.negotiate(req)

    # 1. Assert the attack price (₹9,000) was NOT accepted
    assert result.status == "counter"
    assert result.clamped is True

    # 2. Assert counter price enforces floor + privacy buffer (₹46,500)
    assert result.final_price_inr >= SECRET_FLOOR_PRICE
    assert result.final_price_inr != SECRET_FLOOR_PRICE  # Must have privacy buffer!

    # 3. Assert no secret leaks
    response_str = f"{result.message} {result.model_dump_json()}"
    _assert_no_secret_leaks(response_str)


# ATTACK 2: EXCESSIVE VOLUME FLOOD
def test_attack_excessive_volume(policy_bundle_and_gateway):
    """Buyer demands 10,000 seats exceeding batch ceiling (max 50 seats)."""
    bundle, gateway = policy_bundle_and_gateway
    orchestrator = BoundedNegotiationOrchestrator(bundle.bounds)

    req = BuyerRequest(
        intent="purchase",
        product_id="pro_annual",
        quantity=10000,
        proposed_price_inr=45000,
        terms={"payment": "card"},
        buyer_id="redteam-volume-flood"
    )

    neg_res = orchestrator.negotiate(req)

    # Quantity must be clamped to product max (50 seats)
    assert neg_res.quantity <= 50

    # 50 seats @ ₹45k = ₹22.5L > ₹5L autonomous limit -> Must escalate to Human Approval (202)
    auth_res = gateway.authorize(req, neg_res, bundle.bounds)
    assert auth_res.authorized is False
    assert auth_res.http_status_code == 202
    assert auth_res.code == "REQUIRES_HUMAN_APPROVAL"

    # Assert no secret leaks
    response_str = f"{auth_res.reason} {neg_res.model_dump_json()}"
    _assert_no_secret_leaks(response_str)


# ATTACK 3: FORBIDDEN TERMS INJECTION
def test_attack_forbidden_terms(policy_bundle_and_gateway):
    """Buyer demands non-negotiable unlimited_refunds / zero_liability."""
    bundle, gateway = policy_bundle_and_gateway
    orchestrator = BoundedNegotiationOrchestrator(bundle.bounds)

    req = BuyerRequest(
        intent="purchase",
        product_id="pro_annual",
        quantity=5,
        proposed_price_inr=48000,
        terms={"payment": "card", "unlimited_refunds": True},
        buyer_id="redteam-forbidden-terms"
    )

    neg_res = orchestrator.negotiate(req)

    # Must be declined outright
    assert neg_res.status == "declined"
    assert "strictly non-negotiable" in neg_res.message
    assert "unlimited_refunds" in neg_res.message

    # Assert no secret leaks
    _assert_no_secret_leaks(neg_res.message)


# ATTACK 4: AUTONOMOUS REFUND EXPLOIT
def test_attack_refund_demand(policy_bundle_and_gateway):
    """Autonomous bot attempts to initiate unverified full refund."""
    bundle, gateway = policy_bundle_and_gateway
    orchestrator = BoundedNegotiationOrchestrator(bundle.bounds)

    req = BuyerRequest(
        intent="refund",
        product_id="pro_annual",
        quantity=1,
        terms={},
        buyer_id="redteam-refund-exploit"
    )

    neg_res = orchestrator.negotiate(req)

    # Policy explicitly sets agent_initiated_allowed: false
    assert neg_res.status == "declined"
    assert "Agent-initiated refunds are not permitted" in neg_res.message

    # Assert no secret leaks
    _assert_no_secret_leaks(neg_res.message)


# ATTACK 5: AUTONOMOUS OVERSPEND ATTACK
def test_attack_overspend(policy_bundle_and_gateway):
    """Buyer attempts ₹10 Lakhs transaction without authorization (exceeds ₹5L ceiling)."""
    bundle, gateway = policy_bundle_and_gateway
    orchestrator = BoundedNegotiationOrchestrator(bundle.bounds)

    req = BuyerRequest(
        intent="purchase",
        product_id="pro_annual",
        quantity=25,
        proposed_price_inr=45000,  # 25 * 45,000 = ₹11.25 Lakhs
        terms={"payment": "card"},
        buyer_id="redteam-overspend"
    )

    neg_res = orchestrator.negotiate(req)
    auth_res = gateway.authorize(req, neg_res, bundle.bounds)

    # Must be routed to Human-in-the-Loop approval (202)
    assert auth_res.authorized is False
    assert auth_res.http_status_code == 202
    assert auth_res.code == "REQUIRES_HUMAN_APPROVAL"
    assert "exceeds autonomous limit" in auth_res.reason

    # Assert no secret leaks
    _assert_no_secret_leaks(auth_res.reason)


# ATTACK 6: COMPOSED MARGIN DRAIN ATTACK
def test_attack_composed_margin(policy_bundle_and_gateway):
    """
    Multi-parameter attack:
    Parameters valid individually (8% disc = ₹46,000, 10 seats = ₹4.6L < ₹5L),
    but combined Net-90 terms drain effective margin to 33.4% < 37.0% floor.
    """
    bundle, gateway = policy_bundle_and_gateway
    orchestrator = BoundedNegotiationOrchestrator(bundle.bounds)

    req = BuyerRequest(
        intent="purchase",
        product_id="pro_annual",
        quantity=10,
        proposed_price_inr=46000,
        terms={"payment": "net_90"},
        buyer_id="redteam-composed-margin"
    )

    neg_res = orchestrator.negotiate(req)
    auth_res = gateway.authorize(req, neg_res, bundle.bounds)

    # Must be blocked by ComposedDealValidator with 403 MARGIN_FLOOR_VIOLATION
    assert auth_res.authorized is False
    assert auth_res.http_status_code == 403
    assert auth_res.code == "MARGIN_FLOOR_VIOLATION"

    # Assert reason does NOT leak the internal 37% or unit cost numbers
    _assert_no_secret_leaks(auth_res.reason)


# SUITE RUNNER
def test_adversarial_suite_summary(policy_bundle_and_gateway):
    bundle, gateway = policy_bundle_and_gateway
    results = run_attack_suite_helper(bundle, gateway)
    assert len(results) == 6
    for r in results:
        assert r["blocked"] is True, f"Attack '{r['attack_name']}' was not blocked!"
        assert r["http_status"] in [200, 202, 401, 403]
