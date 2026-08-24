from keoz.negotiation.bounds import BoundsClamp
from keoz.negotiation.orchestrator import BoundedNegotiationOrchestrator
from keoz.policy.compiler import PolicyCompiler
from keoz.policy.models import MerchantPolicy, ProductConfig, BuyerRequest


def test_bounds_clamp_and_privacy_buffer():
    policy = MerchantPolicy(
        authorization={"discount_ceiling_pct": 8},
        products=[
            ProductConfig(id="pro", min_price_inr=45000, list_price_inr=50000, max_seats_per_transaction=50)
        ]
    )
    bundle = PolicyCompiler.compile(policy)

    # Privacy buffer test: counter must be > floor
    buffered = BoundsClamp.apply_privacy_buffer(45000, 45000)
    assert buffered > 45000
    assert buffered == 45000 + min(int(45000 * 0.03), 500)

    # Orchestrator test with sub-floor offer (₹42,000 < ₹45,000 floor)
    orchestrator = BoundedNegotiationOrchestrator(bundle.bounds)
    req = BuyerRequest(
        product_id="pro",
        quantity=10,
        proposed_price_inr=42000,
        terms={"payment": "card"}
    )
    result = orchestrator.negotiate(req)
    assert result.status == "counter"
    assert result.final_price_inr >= 45000
    assert result.clamped is True


def test_natural_language_raw_text_parsing():
    policy = MerchantPolicy(
        authorization={"discount_ceiling_pct": 8},
        products=[
            ProductConfig(id="pro_annual", min_price_inr=45000, list_price_inr=50000, max_seats_per_transaction=50)
        ]
    )
    bundle = PolicyCompiler.compile(policy)
    orchestrator = BoundedNegotiationOrchestrator(bundle.bounds)

    # Raw text natural language offer
    req = BuyerRequest(
        raw_text="I want to buy 50 Pro annual seats, net-30 payment, ₹42,000/seat",
        buyer_id="bot-nlp"
    )
    result = orchestrator.negotiate(req)
    assert result.quantity == 50
    assert result.status == "counter"
    assert result.terms.get("payment") == "net_30"
    assert result.final_price_inr >= 45000
    assert result.clamped is True


def test_refund_intent_declined():
    policy = MerchantPolicy(
        refund={"agent_initiated_allowed": False},
        products=[ProductConfig(id="pro_annual", min_price_inr=45000)]
    )
    bundle = PolicyCompiler.compile(policy)
    orchestrator = BoundedNegotiationOrchestrator(bundle.bounds)

    req = BuyerRequest(
        intent="refund",
        product_id="pro_annual",
        quantity=1
    )
    result = orchestrator.negotiate(req)
    assert result.status == "declined"
    assert "not permitted" in result.message


def test_gemini_api_parsing():
    from unittest.mock import patch, MagicMock
    from keoz.negotiation.llm_parser import LLMOfferParser

    parser = LLMOfferParser(api_key="AQ.Ab8RN6MockTestKey", provider="gemini")
    assert parser.gemini_api_key == "AQ.Ab8RN6MockTestKey"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": '{"product_id": "pro_annual", "proposed_price_inr": 42000, "quantity": 50, "terms": {"payment": "net_30"}, "intent": "purchase"}'
                        }
                    ]
                }
            }
        ]
    }

    with patch("requests.post", return_value=mock_resp) as mock_post:
        parsed = parser.parse("Buy 50 Pro annual seats at ₹42,000 net-30")
        assert parsed["quantity"] == 50
        assert parsed["proposed_price_inr"] == 42000
        assert parsed["terms"]["payment"] == "net_30"
        assert parsed["product_id"] == "pro_annual"
        mock_post.assert_called_once()

