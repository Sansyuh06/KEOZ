import pytest
from agentpolicy.policy.dsl import PolicyDSL
from agentpolicy.policy.compiler import PolicyCompiler
from agentpolicy.policy.models import MerchantPolicy, ProductConfig


def test_policy_dsl_validation():
    policy = MerchantPolicy(
        merchant="test-merchant",
        products=[
            ProductConfig(id="pro", min_price_inr=1000, list_price_inr=1200, unit_cost_inr=600)
        ]
    )
    PolicyDSL.validate_semantics(policy)

    # Invariant failure
    with pytest.raises(ValueError):
        invalid_policy = MerchantPolicy(
            merchant="bad",
            authorization={"discount_ceiling_pct": 150}
        )
        PolicyDSL.validate_semantics(invalid_policy)


def test_policy_compiler(tmp_path):
    policy = MerchantPolicy(
        merchant="test-merchant",
        products=[
            ProductConfig(id="pro", min_price_inr=1000, list_price_inr=1200, unit_cost_inr=600)
        ]
    )
    bundle = PolicyCompiler.compile(policy)
    assert bundle.bounds.floor_prices["pro"] == 1000
    assert bundle.acp_manifest["merchant_name"] == "test-merchant"
    assert bundle.x402_config["x402_version"] == "1.0"

    bundle.export(tmp_path)
    assert (tmp_path / "policy_bounds.json").exists()
    assert (tmp_path / "acp_manifest.json").exists()
