"""Gateway module exports for AgentPolicy."""

from .agent_identity import AgentIdentity, AgentIdentityVerifier, IdentityVerificationResult
from .composed_validator import ComposedDealValidator, ValidationResult
from .approvals import ApprovalBridge, ApprovalRecord
from .authorizer import AuthorizationGateway, AuthorizationOutcome
from .exceptions import (
    PolicyException,
    PolicyViolation,
    AgentIdentityError,
    MarginFloorViolation,
    PendingApproval
)

__all__ = [
    "AgentIdentity",
    "AgentIdentityVerifier",
    "IdentityVerificationResult",
    "ComposedDealValidator",
    "ValidationResult",
    "ApprovalBridge",
    "ApprovalRecord",
    "AuthorizationGateway",
    "AuthorizationOutcome",
    "PolicyException",
    "PolicyViolation",
    "AgentIdentityError",
    "MarginFloorViolation",
    "PendingApproval"
]
