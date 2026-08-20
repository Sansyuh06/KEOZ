"""Manifest generator for ACP (Agent Commerce Protocol) and x402 payment protocol."""

from typing import Dict, Any
from .models import MerchantPolicy


class ManifestGenerator:
    @staticmethod
    def generate_acp_manifest(policy: MerchantPolicy, base_url: str = "http://localhost:8000") -> Dict[str, Any]:
        """Generate /.well-known/agent-commerce.json ACP discovery manifest."""
        return {
            "schema_version": "1.0.0",
            "merchant_name": policy.merchant,
            "policy_version": policy.version,
            "endpoints": {
                "negotiation": f"{base_url}/api/agent/negotiate",
                "payment": f"{base_url}/api/agent/pay",
                "status": f"{base_url}/api/agent/status"
            },
            "capabilities": {
                "autonomous_transactions": True,
                "negotiation_supported": True,
                "max_autonomous_limit_inr": policy.authorization.max_autonomous_inr,
                "accepted_instruments": policy.payment.accepted_instruments,
                "settlement_currency": policy.payment.settlement_currency
            },
            "products": [
                {
                    "id": p.id,
                    "name": p.name or p.id,
                    "max_seats": p.max_seats_per_transaction,
                    "auto_renew": p.auto_renew,
                    "requires_approval": p.requires_human_approval,
                    "public_price_inr": p.list_price_inr or (int(p.min_price_inr * 1.1) if p.min_price_inr > 0 else None)
                }
                for p in policy.products
            ],
            "agent_identity": {
                "required": policy.agent_identity.require_signed_token,
                "trusted_issuers": policy.agent_identity.trusted_principals
            }
        }

    @staticmethod
    def generate_x402_config(policy: MerchantPolicy, base_url: str = "http://localhost:8000") -> Dict[str, Any]:
        """Generate x402 configuration for payment requirement protocol."""
        return {
            "x402_version": "1.0",
            "payment_recipient": policy.merchant,
            "currency": policy.payment.settlement_currency,
            "payment_methods": policy.payment.accepted_instruments,
            "proof_verification_endpoint": f"{base_url}/api/agent/pay",
            "facilitator": "razorpay-test-gateway"
        }

    @staticmethod
    def generate_openapi_spec(policy: MerchantPolicy, base_url: str = "http://localhost:8000") -> Dict[str, Any]:
        """Generate OpenAPI 3.1 schema for agent discovery."""
        return {
            "openapi": "3.1.0",
            "info": {
                "title": f"{policy.merchant} Agentic Commerce API",
                "version": policy.version,
                "description": "AgentPolicy-governed endpoint for autonomous buyer agents"
            },
            "servers": [{"url": base_url}],
            "paths": {
                "/.well-known/agent-commerce.json": {
                    "get": {
                        "summary": "ACP Discovery Manifest",
                        "responses": {"200": {"description": "Returns commerce capabilities"}}
                    }
                },
                "/api/agent/negotiate": {
                    "post": {
                        "summary": "Submit purchase or negotiation proposal",
                        "responses": {
                            "200": {"description": "Offer accepted or counter proposed"},
                            "202": {"description": "Requires human approval"},
                            "403": {"description": "Policy violation"}
                        }
                    }
                },
                "/api/agent/pay": {
                    "post": {
                        "summary": "Execute payment with x402 proof or authorization token",
                        "responses": {
                            "200": {"description": "Settled & fulfilled"},
                            "402": {"description": "Payment Required"}
                        }
                    }
                }
            }
        }
