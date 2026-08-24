from keoz.gateway.authorizer import AuthorizationGateway
from keoz.policy.compiler import PolicyCompiler
from keoz.policy.models import MerchantPolicy, ProductConfig, BuyerRequest, NegotiationResult


def test_authorization_gateway_4_layers():
    policy = MerchantPolicy(
        authorization={
            "max_autonomous_inr": 500000,
            "discount_ceiling_pct": 8,
            "margin_floor_pct": 0.37
        },
        products=[
            ProductConfig(id="pro", min_price_inr=45000, list_price_inr=50000, unit_cost_inr=28350)
        ]
    )
    bundle = PolicyCompiler.compile(policy)
    gateway = AuthorizationGateway()

    # Case 1: Standard Authorized deal (10 seats @ 48,000 = ₹4.8L < ₹5L)
    req1 = BuyerRequest(product_id="pro", quantity=10, proposed_price_inr=48000, terms={"payment": "card"})
    res1 = NegotiationResult(status="accepted", product_id="pro", quantity=10, final_price_inr=48000, terms={"payment": "card"})
    outcome1 = gateway.authorize(req1, res1, bundle.bounds)
    assert outcome1.authorized is True
    assert outcome1.http_status_code == 200

    # Case 2: Net-Terms triggers Human Approval (HTTP 202)
    req2 = BuyerRequest(product_id="pro", quantity=10, proposed_price_inr=48000, terms={"payment": "net_30"})
    res2 = NegotiationResult(status="accepted", product_id="pro", quantity=10, final_price_inr=48000, terms={"payment": "net_30"})
    outcome2 = gateway.authorize(req2, res2, bundle.bounds)
    assert outcome2.authorized is False
    assert outcome2.status == "pending_approval"
    assert outcome2.http_status_code == 202
    assert "net_30" in outcome2.reason

    # Case 3: Overspend (> ₹5L autonomous limit triggers 202)
    req3 = BuyerRequest(product_id="pro", quantity=20, proposed_price_inr=48000, terms={"payment": "card"})  # 9.6L > 5L
    res3 = NegotiationResult(status="accepted", product_id="pro", quantity=20, final_price_inr=48000, terms={"payment": "card"})
    outcome3 = gateway.authorize(req3, res3, bundle.bounds)
    assert outcome3.status == "pending_approval"
    assert outcome3.http_status_code == 202
