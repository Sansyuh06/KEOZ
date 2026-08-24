"""Autonomous AI Buyer Client simulator interacting with AgentPolicy endpoints."""

import requests
from typing import Dict, Any, Optional
from keoz.gateway.agent_identity import AgentIdentityVerifier


class AIBuyerClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8000", principal_id: str = "acme-corp"):
        self.base_url = base_url
        self.principal_id = principal_id
        self.verifier = AgentIdentityVerifier()
        self.agent_token = self.verifier.issue_token(
            agent_id="enterprise-procurement-bot-01",
            principal_id=principal_id,
            max_commitment_inr=5000000
        )

    def discover_merchant(self) -> Dict[str, Any]:
        """Fetch ACP discovery manifest."""
        resp = requests.get(f"{self.base_url}/.well-known/agent-commerce.json")
        return resp.json()

    def negotiate_purchase(
        self,
        product_id: str,
        quantity: int,
        proposed_price_inr: int,
        terms: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Submit purchase proposal to merchant."""
        payload = {
            "intent": "purchase",
            "product_id": product_id,
            "quantity": quantity,
            "proposed_price_inr": proposed_price_inr,
            "terms": terms or {"payment": "card"},
            "buyer_id": "ai-buyer-client",
            "agent_token": self.agent_token
        }
        resp = requests.post(f"{self.base_url}/api/agent/negotiate", json=payload)
        return {
            "status_code": resp.status_code,
            "data": resp.json()
        }

    def pay(self, product_id: str, quantity: int, amount_inr: int, x402_proof: str = "0xdeadbeef1234567890abcdef") -> Dict[str, Any]:
        """Execute settlement with x402 proof."""
        payload = {
            "product_id": product_id,
            "quantity": quantity,
            "amount_inr": amount_inr,
            "currency": "INR",
            "x402_proof": x402_proof,
            "buyer_id": "ai-buyer-client"
        }
        resp = requests.post(f"{self.base_url}/api/agent/pay", json=payload)
        return {
            "status_code": resp.status_code,
            "data": resp.json()
        }
