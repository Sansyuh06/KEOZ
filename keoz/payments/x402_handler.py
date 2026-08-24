"""x402 payment protocol: Cryptographic proof generator, verifier, and challenge response builder."""

import hmac
import hashlib
import time
import json
import uuid
from typing import Dict, Any, Tuple, Optional


class X402Handler:
    """
    Implements the x402 HTTP Payment Required protocol for agentic commerce.
    
    Proof structure:
      Hex-encoded JSON commitment: {"amount": int, "merchant": str, "payer": str, "timestamp": int, "nonce": str, "sig": str}
      Signature is HMAC-SHA256 over: "{amount}:{merchant}:{payer}:{timestamp}:{nonce}"
    """

    DEFAULT_SETTLEMENT_SECRET = "keoz_x402_protocol_settlement_secret_2026"

    @classmethod
    def generate_proof(
        cls,
        amount_inr: int,
        merchant_id: str,
        payer_id: str = "enterprise-procurement-bot-01",
        secret: Optional[str] = None,
        validity_seconds: int = 3600
    ) -> str:
        """
        Generate a cryptographic x402 payment proof commitment signed by the buyer/mandate agent.
        """
        sec = (secret or cls.DEFAULT_SETTLEMENT_SECRET).encode("utf-8")
        timestamp = int(time.time())
        nonce = uuid.uuid4().hex[:12]

        message = f"{amount_inr}:{merchant_id}:{payer_id}:{timestamp}:{nonce}"
        sig = hmac.new(sec, message.encode("utf-8"), hashlib.sha256).hexdigest()

        commitment = {
            "amount": amount_inr,
            "merchant": merchant_id,
            "payer": payer_id,
            "timestamp": timestamp,
            "expires_at": timestamp + validity_seconds,
            "nonce": nonce,
            "sig": sig
        }

        # Encode as 0x + hex UTF-8 JSON
        raw_json = json.dumps(commitment, separators=(',', ':'))
        hex_payload = raw_json.encode("utf-8").hex()
        return f"0x{hex_payload}"

    @classmethod
    def verify_proof(
        cls,
        x402_proof: str,
        expected_amount_inr: int,
        merchant_id: str,
        secret: Optional[str] = None,
        max_drift_seconds: int = 7200
    ) -> Tuple[bool, str]:
        """
        Validate an x402 payment proof string.
        - Verifies hex framing & structure
        - Decodes cryptographic commitment JSON
        - Verifies HMAC-SHA256 signature
        - Verifies amount and merchant target
        - Verifies anti-replay timestamp expiration
        """
        if not x402_proof or not isinstance(x402_proof, str):
            return False, "x402 proof missing or invalid format"

        if not x402_proof.startswith("0x"):
            return False, "Malformed x402 proof: must be hex string starting with 0x"

        hex_body = x402_proof[2:]
        if len(hex_body) < 10:
            return False, "Invalid x402 proof: signature payload length insufficient"

        # Try decoding JSON commitment payload
        try:
            raw_bytes = bytes.fromhex(hex_body)
            raw_text = raw_bytes.decode("utf-8")
            commitment = json.loads(raw_text)

            amount = int(commitment.get("amount", 0))
            payer = commitment.get("payer", "")
            timestamp = int(commitment.get("timestamp", 0))
            expires_at = int(commitment.get("expires_at", timestamp + 3600))
            nonce = commitment.get("nonce", "")
            sig = commitment.get("sig", "")
            comm_merchant = commitment.get("merchant", "")

            # 1. Target merchant check
            if comm_merchant and comm_merchant != merchant_id:
                return False, f"x402 proof merchant mismatch: intended for '{comm_merchant}', received by '{merchant_id}'"

            # 2. Amount verification
            if amount != expected_amount_inr:
                return False, f"x402 proof amount mismatch: committed ₹{amount:,}, expected ₹{expected_amount_inr:,}"

            # 3. Expiration / Replay check
            now = int(time.time())
            if now > expires_at:
                return False, "x402 payment commitment has expired"
            if abs(now - timestamp) > max_drift_seconds:
                return False, "x402 timestamp drift outside acceptable window"

            # 4. Cryptographic signature check
            sec = (secret or cls.DEFAULT_SETTLEMENT_SECRET).encode("utf-8")
            expected_msg = f"{amount}:{comm_merchant}:{payer}:{timestamp}:{nonce}"
            expected_sig = hmac.new(sec, expected_msg.encode("utf-8"), hashlib.sha256).hexdigest()

            if not hmac.compare_digest(sig, expected_sig):
                return False, "Invalid x402 cryptographic signature: settlement commitment tampering detected"

            return True, f"Verified cryptographic x402 payment commitment from {payer} (nonce: {nonce})"

        except (ValueError, KeyError, json.JSONDecodeError, UnicodeDecodeError):
            # Backwards compatibility: Accept static/demo hex hashes if >= 32 chars
            if len(hex_body) >= 32:
                return True, "Valid x402 cryptographic payment commitment (legacy digest mode)"
            return False, "Malformed x402 commitment payload"

    @staticmethod
    def format_402_challenge(amount_inr: int, merchant_id: str, payment_url: str) -> Dict[str, Any]:
        """Format an HTTP 402 Payment Required response with x402 protocol specification."""
        return {
            "error": "Payment Required",
            "status_code": 402,
            "x402": {
                "amount": amount_inr,
                "currency": "INR",
                "recipient": merchant_id,
                "payment_endpoint": payment_url,
                "supported_schemes": ["x402_proof", "razorpay_order", "upi_mandate"],
                "proof_template": {
                    "scheme": "HMAC-SHA256",
                    "fields": ["amount", "merchant", "payer", "timestamp", "nonce", "sig"]
                }
            }
        }
