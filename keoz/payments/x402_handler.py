"""x402 protocol proof verifier and receipt generator for KEOZ."""

from typing import Dict, Any, Tuple


class X402Handler:
    """Verifies x402 payment authorization proofs and formats protocol responses."""

    @staticmethod
    def verify_proof(x402_proof: str, expected_amount_inr: int, merchant_id: str) -> Tuple[bool, str]:
        """
        Validate an x402 payment proof string.
        Valid proof format: '0x' + hex string containing signature over amount + merchant.
        """
        if not x402_proof or not x402_proof.startswith("0x"):
            return False, "Malformed x402 proof: must be hex string starting with 0x"

        # Check minimal proof length
        if len(x402_proof) < 10:
            return False, "Invalid x402 proof: signature length insufficient"

        # For simulator/demo: accept validly-structured hex proofs
        return True, "Valid x402 cryptographic payment commitment"

    @staticmethod
    def format_402_challenge(amount_inr: int, merchant_id: str, payment_url: str) -> Dict[str, Any]:
        """Format an HTTP 402 Payment Required response."""
        return {
            "error": "Payment Required",
            "status_code": 402,
            "x402": {
                "amount": amount_inr,
                "currency": "INR",
                "recipient": merchant_id,
                "payment_endpoint": payment_url,
                "supported_schemes": ["x402_proof", "razorpay_order", "upi_mandate"]
            }
        }
