"""Unit tests for x402 payment protocol cryptographic proof generation and verification."""

import time
import pytest
from keoz.payments.x402_handler import X402Handler


def test_x402_generate_and_verify_valid_proof():
    """Valid proof with matching merchant and amount should verify successfully."""
    proof = X402Handler.generate_proof(
        amount_inr=2325000,
        merchant_id="acme-saas",
        payer_id="enterprise-bot-01"
    )
    assert proof.startswith("0x")

    valid, reason = X402Handler.verify_proof(
        x402_proof=proof,
        expected_amount_inr=2325000,
        merchant_id="acme-saas"
    )
    assert valid is True
    assert "Verified cryptographic x402" in reason


def test_x402_tampered_amount_fails():
    """If amount in proof does not match expected settlement amount, it must be rejected."""
    proof = X402Handler.generate_proof(
        amount_inr=1000000,
        merchant_id="acme-saas",
        payer_id="enterprise-bot-01"
    )

    valid, reason = X402Handler.verify_proof(
        x402_proof=proof,
        expected_amount_inr=2000000,  # mismatch!
        merchant_id="acme-saas"
    )
    assert valid is False
    assert "amount mismatch" in reason


def test_x402_merchant_mismatch_fails():
    """Proof signed for Merchant A cannot be replayed on Merchant B."""
    proof = X402Handler.generate_proof(
        amount_inr=50000,
        merchant_id="acme-saas",
        payer_id="enterprise-bot-01"
    )

    valid, reason = X402Handler.verify_proof(
        x402_proof=proof,
        expected_amount_inr=50000,
        merchant_id="bigco-enterprise"  # wrong merchant
    )
    assert valid is False
    assert "merchant mismatch" in reason


def test_x402_expired_proof_fails():
    """Expired payment commitments are rejected."""
    proof = X402Handler.generate_proof(
        amount_inr=50000,
        merchant_id="acme-saas",
        validity_seconds=-10  # already expired
    )

    valid, reason = X402Handler.verify_proof(
        x402_proof=proof,
        expected_amount_inr=50000,
        merchant_id="acme-saas"
    )
    assert valid is False
    assert "expired" in reason


def test_x402_tampered_signature_fails():
    """Tampering with commitment parameters invalidates cryptographic HMAC signature."""
    proof = X402Handler.generate_proof(
        amount_inr=50000,
        merchant_id="acme-saas"
    )
    # Tamper with secret
    valid, reason = X402Handler.verify_proof(
        x402_proof=proof,
        expected_amount_inr=50000,
        merchant_id="acme-saas",
        secret="attacker_fake_secret_key"
    )
    assert valid is False
    assert "tampering detected" in reason or "Invalid x402 cryptographic signature" in reason


def test_x402_format_challenge():
    """Challenge generator returns standards-compliant HTTP 402 structure."""
    challenge = X402Handler.format_402_challenge(
        amount_inr=50000,
        merchant_id="acme-saas",
        payment_url="/api/agent/pay"
    )
    assert challenge["status_code"] == 402
    assert "x402" in challenge
    assert challenge["x402"]["amount"] == 50000
    assert challenge["x402"]["recipient"] == "acme-saas"
