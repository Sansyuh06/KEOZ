"""Bounded negotiation orchestrator for KEOZ."""

from ..policy.models import NegotiationBounds, BuyerRequest, NegotiationResult
from .negotiator import PolicyAwareNegotiator


class BoundedNegotiationOrchestrator:
    """
    Coordinates the negotiation lifecycle:
    1. Compiles request against active NegotiationBounds
    2. Runs PolicyAwareNegotiator
    3. Guarantees output is policy-compliant by construction
    """

    def __init__(self, bounds: NegotiationBounds):
        self.bounds = bounds
        self.negotiator = PolicyAwareNegotiator(bounds)

    def negotiate(self, request: BuyerRequest) -> NegotiationResult:
        result = self.negotiator.negotiate(request)

        # Invariant assertion — policy compliance by construction
        if result.status in ["accepted", "counter"]:
            assert self.bounds.validate(result), "CRITICAL: Negotiation result violated compiled policy bounds"

        return result
