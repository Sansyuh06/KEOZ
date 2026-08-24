"""KEOZ — The Merchant Command Center for Agentic Commerce.

Pre-Razorpay financial policy layer, multi-merchant registry, and authorization engine for autonomous buyer agents.
"""

from .policy import (
    MerchantPolicy,
    ProductConfig,
    AuthorizationRules,
    NegotiationBounds,
    BuyerRequest,
    NegotiationResult,
    PolicyCompiler,
    PolicyDSL
)
from .gateway import (
    AuthorizationGateway,
    AgentIdentityVerifier,
    ComposedDealValidator,
    ApprovalBridge
)
from .memory import AuditLogger, AuditAtom
from .payments import RazorpayClient, X402Handler
from .registry import MerchantRegistry, registry
from .metrics import metrics, MetricsCollector

__version__ = "1.0.0"

__all__ = [
    "MerchantPolicy",
    "ProductConfig",
    "AuthorizationRules",
    "NegotiationBounds",
    "BuyerRequest",
    "NegotiationResult",
    "PolicyCompiler",
    "PolicyDSL",
    "AuthorizationGateway",
    "AgentIdentityVerifier",
    "ComposedDealValidator",
    "ApprovalBridge",
    "AuditLogger",
    "AuditAtom",
    "RazorpayClient",
    "X402Handler",
    "MerchantRegistry",
    "registry",
    "metrics",
    "MetricsCollector",
]
