from agentpolicy.gateway.composed_validator import ComposedDealValidator
from agentpolicy.policy.compiler import PolicyCompiler
from agentpolicy.policy.models import MerchantPolicy, ProductConfig


def test_composed_deal_margin_floor():
    policy = MerchantPolicy(
        authorization={"margin_floor_pct": 0.37},
        products=[
            ProductConfig(id="pro", min_price_inr=45000, list_price_inr=50000, unit_cost_inr=28350)
        ]
    )
    bundle = PolicyCompiler.compile(policy)
    validator = ComposedDealValidator(default_margin_floor=0.37)

    # Standard healthy deal (immediate card payment)
    # Revenue: 45000, COGS: 28350, Margin: (45000 - 28350)/45000 = 37.0% -> PASS
    res = validator.validate(
        product_id="pro",
        price_inr=45000,
        quantity=1,
        terms={"payment": "card"},
        bounds=bundle.bounds
    )
    assert res.passed is True
    assert res.effective_margin >= 0.37

    # Multi-parameter margin drain attack:
    # 8% discount + Net-90 payment terms (5.0% financing cost)
    # Revenue: 45000, COGS: 28350, Financing cost: 2250 -> Net profit: 14400 / 45000 = 32.0% (< 37%) -> REJECT
    attack_res = validator.validate(
        product_id="pro",
        price_inr=45000,
        quantity=1,
        terms={"payment": "net_90"},
        bounds=bundle.bounds
    )
    assert attack_res.passed is False
    assert attack_res.code == "MARGIN_FLOOR_VIOLATION"
    assert "margin requirements" in attack_res.reason
