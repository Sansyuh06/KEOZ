"""Unit tests for Razorpay Client live API calls and simulation fallback."""

from unittest.mock import patch, MagicMock
from keoz.payments.razorpay_client import RazorpayClient


def test_razorpay_simulation_fallback():
    """When default or test keys are present, client cleanly marks response as simulated."""
    client = RazorpayClient()
    assert client.is_live is False

    order = client.create_order(amount_inr=5000, currency="INR")
    assert order["simulated"] is True
    assert order["amount"] == 500000
    assert order["id"].startswith("order_")

    plink = client.create_payment_link(amount_inr=5000, description="Test License")
    assert plink["simulated"] is True
    assert plink["amount"] == 500000
    assert plink["short_url"].startswith("https://rzp.io/i/")


def test_razorpay_live_test_mode_order_call():
    """When live test keys are configured, client constructs real HTTP Basic Auth request to Razorpay."""
    client = RazorpayClient(key_id="rzp_live_abc12345", key_secret="secret_xyz98765")
    assert client.is_live is True

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "order_real_12345",
        "entity": "order",
        "amount": 4500000,
        "currency": "INR",
        "receipt": "rcpt_001",
        "status": "created"
    }

    with patch("requests.post", return_value=mock_response) as mock_post:
        order = client.create_order(
            amount_inr=45000,
            currency="INR",
            receipt="rcpt_001",
            notes={"buyer_id": "ai_agent_01"}
        )

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args

        # Assert URL
        assert args[0] == "https://api.razorpay.com/v1/orders"

        # Assert Auth
        auth = kwargs["auth"]
        assert auth.username == "rzp_live_abc12345"
        assert auth.password == "secret_xyz98765"

        # Assert Payload
        json_data = kwargs["json"]
        assert json_data["amount"] == 4500000  # amount in paise
        assert json_data["currency"] == "INR"
        assert json_data["receipt"] == "rcpt_001"
        assert json_data["notes"] == {"buyer_id": "ai_agent_01"}

        # Assert output
        assert order["simulated"] is False
        assert order["id"] == "order_real_12345"
        assert "checkout_url" in order


def test_razorpay_live_test_mode_payment_link_call():
    """Assert real HTTP call construction for payment links."""
    client = RazorpayClient(key_id="rzp_live_abc12345", key_secret="secret_xyz98765")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "plink_real_9999",
        "entity": "payment_link",
        "amount": 200000,
        "currency": "INR",
        "short_url": "https://rzp.io/i/plink_real_9999",
        "status": "created"
    }

    with patch("requests.post", return_value=mock_response) as mock_post:
        link = client.create_payment_link(
            amount_inr=2000,
            description="Pro Annual Seat",
            customer_email="buyer@enterprise.ai",
            notes={"policy_version": "v1.0"}
        )

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://api.razorpay.com/v1/payment_links"
        assert kwargs["json"]["amount"] == 200000
        assert kwargs["json"]["customer"]["email"] == "buyer@enterprise.ai"
        assert link["simulated"] is False
        assert link["id"] == "plink_real_9999"


def test_razorpay_live_capture_payment_call():
    """Assert real HTTP call construction for payment capture."""
    client = RazorpayClient(key_id="rzp_live_abc12345", key_secret="secret_xyz98765")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "pay_real_7777",
        "entity": "payment",
        "amount": 4500000,
        "currency": "INR",
        "status": "captured"
    }

    with patch("requests.post", return_value=mock_response) as mock_post:
        payment = client.capture_payment(payment_id="pay_real_7777", amount_inr=45000)
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://api.razorpay.com/v1/payments/pay_real_7777/capture"
        assert kwargs["json"]["amount"] == 4500000
        assert payment["simulated"] is False

    # Also test mock capture helper explicitly flags simulation
    sim_client = RazorpayClient()
    mock_webhook = sim_client.capture_payment_mock(order_id="order_123", amount_inr=45000)
    assert mock_webhook["payload"]["payment"]["entity"]["simulated"] is True
