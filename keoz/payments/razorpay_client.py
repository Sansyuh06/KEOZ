"""Razorpay integration client for KEOZ (supporting both live test-mode API keys and deterministic simulator)."""

import os
import uuid
import time
import requests
from requests.auth import HTTPBasicAuth
from typing import Dict, Any, Optional


class RazorpayClient:
    """
    Interfaces with Razorpay Orders, Payment Links, and Webhook verification.
    - When real test keys are configured (RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET), executes actual HTTP calls.
    - When no keys are provided, cleanly falls back to deterministic simulation with 'simulated: true'.
    """

    RAZORPAY_ORDERS_URL = "https://api.razorpay.com/v1/orders"
    RAZORPAY_PAYMENT_LINKS_URL = "https://api.razorpay.com/v1/payment_links"

    def __init__(self, key_id: Optional[str] = None, key_secret: Optional[str] = None):
        self.key_id = key_id or os.environ.get("RAZORPAY_KEY_ID", "rzp_test_keoz_2026")
        self.key_secret = key_secret or os.environ.get("RAZORPAY_KEY_SECRET", "rzp_secret_dummy")
        self.is_live = bool(
            self.key_id
            and self.key_secret
            and not self.key_id.startswith("rzp_test_keoz")
            and not self.key_id.startswith("rzp_test_agentpolicy")
            and self.key_secret != "rzp_secret_dummy"
        )

    def create_order(
        self,
        amount_inr: int,
        currency: str = "INR",
        receipt: Optional[str] = None,
        notes: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a Razorpay Order (live API call if keys configured, simulator fallback otherwise)."""
        amount_paise = amount_inr * 100
        rcpt = receipt or f"rcpt_{uuid.uuid4().hex[:8]}"
        req_notes = notes or {}

        if self.is_live:
            try:
                response = requests.post(
                    self.RAZORPAY_ORDERS_URL,
                    auth=HTTPBasicAuth(self.key_id, self.key_secret),
                    json={
                        "amount": amount_paise,
                        "currency": currency,
                        "receipt": rcpt,
                        "notes": req_notes
                    },
                    timeout=10.0
                )
                if response.status_code in [200, 201]:
                    res_data = response.json()
                    res_data["simulated"] = False
                    res_data["checkout_url"] = f"https://checkout.razorpay.com/v1/checkout.html?order_id={res_data.get('id')}"
                    return res_data
                else:
                    raise RuntimeError(f"Razorpay Orders API error [{response.status_code}]: {response.text}")
            except Exception as e:
                if not isinstance(e, RuntimeError):
                    raise RuntimeError(f"Failed to connect to Razorpay Orders API: {str(e)}")
                raise

        # Deterministic simulation fallback
        order_id = f"order_{uuid.uuid4().hex[:14]}"
        return {
            "id": order_id,
            "entity": "order",
            "amount": amount_paise,
            "amount_paid": 0,
            "amount_due": amount_paise,
            "currency": currency,
            "receipt": rcpt,
            "status": "created",
            "attempts": 0,
            "notes": req_notes,
            "created_at": int(time.time()),
            "checkout_url": f"https://checkout.razorpay.com/v1/checkout.html?order_id={order_id}",
            "simulated": True
        }

    def create_payment_link(
        self,
        amount_inr: int,
        description: str,
        customer_email: Optional[str] = None,
        notes: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a Razorpay Payment Link (live API call if keys configured, simulator fallback otherwise)."""
        amount_paise = amount_inr * 100
        req_notes = notes or {}

        if self.is_live:
            try:
                payload = {
                    "amount": amount_paise,
                    "currency": "INR",
                    "description": description,
                    "notes": req_notes
                }
                if customer_email:
                    payload["customer"] = {"email": customer_email}

                response = requests.post(
                    self.RAZORPAY_PAYMENT_LINKS_URL,
                    auth=HTTPBasicAuth(self.key_id, self.key_secret),
                    json=payload,
                    timeout=10.0
                )
                if response.status_code in [200, 201]:
                    res_data = response.json()
                    res_data["simulated"] = False
                    return res_data
                else:
                    raise RuntimeError(f"Razorpay Payment Links API error [{response.status_code}]: {response.text}")
            except Exception as e:
                if not isinstance(e, RuntimeError):
                    raise RuntimeError(f"Failed to connect to Razorpay Payment Links API: {str(e)}")
                raise

        # Deterministic simulation fallback
        link_id = f"plink_{uuid.uuid4().hex[:14]}"
        return {
            "id": link_id,
            "entity": "payment_link",
            "amount": amount_paise,
            "currency": "INR",
            "description": description,
            "short_url": f"https://rzp.io/i/{link_id}",
            "status": "created",
            "created_at": int(time.time()),
            "simulated": True
        }

    def capture_payment(self, payment_id: str, amount_inr: int, currency: str = "INR") -> Dict[str, Any]:
        """Capture an authorized Razorpay payment."""
        if self.is_live:
            try:
                response = requests.post(
                    f"https://api.razorpay.com/v1/payments/{payment_id}/capture",
                    auth=HTTPBasicAuth(self.key_id, self.key_secret),
                    json={"amount": amount_inr * 100, "currency": currency},
                    timeout=10.0
                )
                if response.status_code == 200:
                    res_data = response.json()
                    res_data["simulated"] = False
                    return res_data
                else:
                    raise RuntimeError(f"Razorpay Capture API error [{response.status_code}]: {response.text}")
            except Exception as e:
                if not isinstance(e, RuntimeError):
                    raise RuntimeError(f"Failed to connect to Razorpay Capture API: {str(e)}")
                raise

        return {
            "id": payment_id,
            "entity": "payment",
            "amount": amount_inr * 100,
            "currency": currency,
            "status": "captured",
            "captured": True,
            "simulated": True
        }

    def capture_payment_mock(self, order_id: str, amount_inr: int) -> Dict[str, Any]:
        """Simulate a successful payment.captured webhook payload."""
        payment_id = f"pay_{uuid.uuid4().hex[:14]}"
        return {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": payment_id,
                        "order_id": order_id,
                        "amount": amount_inr * 100,
                        "currency": "INR",
                        "status": "captured",
                        "method": "x402_agent_mandate",
                        "captured": True,
                        "created_at": int(time.time()),
                        "simulated": True
                    }
                }
            }
        }
