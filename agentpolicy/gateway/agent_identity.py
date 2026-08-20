"""Agent Identity token issuer and verifier (JWS)."""

import time
from dataclasses import dataclass
from typing import List, Dict, Optional
import jwt


@dataclass
class AgentIdentity:
    agent_id: str                          # e.g., "procurement-bot-01@acme-corp"
    principal_id: str                      # e.g., "acme-corp"
    scope: List[str]                       # e.g., ["procure:saas", "procure:licenses"]
    max_commitment_inr: int                # e.g., 5000000 (₹50 Lakhs)
    issued_at: int
    expires_at: int
    metadata: Dict[str, str] = None


@dataclass
class IdentityVerificationResult:
    verified: bool
    identity: Optional[AgentIdentity] = None
    reason: Optional[str] = None
    code: Optional[str] = None

    @classmethod
    def success(cls, identity: AgentIdentity) -> 'IdentityVerificationResult':
        return cls(verified=True, identity=identity)

    @classmethod
    def failure(cls, reason: str, code: str = "INVALID_IDENTITY") -> 'IdentityVerificationResult':
        return cls(verified=False, reason=reason, code=code)


class AgentIdentityVerifier:
    """Verifies counterparty agent tokens and ensures spending authority."""

    DEFAULT_SECRET = "agentpolicy_shared_test_secret_key_2026"

    def __init__(self, trusted_principals: List[str] = None, secrets: Dict[str, str] = None):
        self.trusted_principals = set(trusted_principals or ["acme-corp", "bigco-procurement", "enterprise-agent-hub"])
        self.secrets = secrets or {}

    def get_secret(self, principal_id: str) -> str:
        return self.secrets.get(principal_id, self.DEFAULT_SECRET)

    def issue_token(
        self,
        agent_id: str,
        principal_id: str,
        max_commitment_inr: int = 5000000,
        scope: List[str] = None,
        validity_seconds: int = 86400
    ) -> str:
        """Helper to issue a signed test token for AI buyer agents."""
        now = int(time.time())
        payload = {
            "agent_id": agent_id,
            "principal_id": principal_id,
            "scope": scope or ["procure:saas"],
            "max_commitment_inr": max_commitment_inr,
            "iat": now,
            "exp": now + validity_seconds
        }
        secret = self.get_secret(principal_id)
        return jwt.encode(payload, secret, algorithm="HS256")

    def verify(self, token: str, required_amount_inr: Optional[int] = None) -> IdentityVerificationResult:
        """Verify the cryptographic signature, validity, principal whitelist, and spending limits."""
        if not token:
            return IdentityVerificationResult.failure("Agent identity token missing", "TOKEN_MISSING")

        try:
            # First decode unverified to find principal_id
            unverified = jwt.decode(token, options={"verify_signature": False})
            principal_id = unverified.get("principal_id")

            if not principal_id:
                return IdentityVerificationResult.failure("Token missing principal_id", "INVALID_PAYLOAD")

            if principal_id not in self.trusted_principals:
                return IdentityVerificationResult.failure(
                    f"Untrusted principal '{principal_id}'. Allowed: {list(self.trusted_principals)}",
                    "UNTRUSTED_PRINCIPAL"
                )

            secret = self.get_secret(principal_id)
            payload = jwt.decode(token, secret, algorithms=["HS256"])

            identity = AgentIdentity(
                agent_id=payload["agent_id"],
                principal_id=payload["principal_id"],
                scope=payload.get("scope", []),
                max_commitment_inr=payload.get("max_commitment_inr", 0),
                issued_at=payload.get("iat", 0),
                expires_at=payload.get("exp", 0),
                metadata=payload.get("metadata", {})
            )

            # Check commitment amount
            if required_amount_inr is not None and required_amount_inr > identity.max_commitment_inr:
                return IdentityVerificationResult.failure(
                    f"Transaction value (₹{required_amount_inr:,}) exceeds agent's authorized limit (₹{identity.max_commitment_inr:,})",
                    "AGENT_COMMITMENT_EXCEEDED"
                )

            return IdentityVerificationResult.success(identity)

        except jwt.ExpiredSignatureError:
            return IdentityVerificationResult.failure("Agent identity token expired", "TOKEN_EXPIRED")
        except jwt.InvalidTokenError as e:
            return IdentityVerificationResult.failure(f"Invalid token signature: {str(e)}", "TOKEN_INVALID")
