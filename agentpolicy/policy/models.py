"""Data models for AgentPolicy policies, bounds, and negotiation objects."""

from __future__ import annotations
from typing import List, Dict, Optional, Any, Literal
from enum import Enum
from pydantic import BaseModel, Field


class ApprovalTrigger(str, Enum):
    AMOUNT_EXCEEDS = "amount_exceeds"
    NEW_CUSTOMER = "new_customer"
    NET_TERMS = "net_terms"
    REFUND_REQUEST = "refund_request"
    MARGIN_VIOLATION = "margin_violation"
    CUSTOM = "custom"


class ProductConfig(BaseModel):
    id: str
    name: Optional[str] = None
    min_price_inr: int = Field(default=0, description="Floor price per unit in INR (secret)")
    list_price_inr: Optional[int] = Field(default=None, description="Standard list price per unit in INR")
    unit_cost_inr: int = Field(default=0, description="Internal cost of goods per unit in INR (secret)")
    max_seats_per_transaction: int = Field(default=100, description="Max units/seats per transaction")
    auto_renew: bool = False
    requires_human_approval: bool = False


class AuthorizationRules(BaseModel):
    max_autonomous_inr: int = Field(default=500000, description="Max spend without human signoff")
    discount_ceiling_pct: float = Field(default=8.0, description="Max allowed discount percentage")
    margin_floor_pct: float = Field(default=0.37, description="Minimum acceptable margin percentage (e.g. 0.37 = 37%)")
    require_human_approval_when: List[str] = Field(default_factory=lambda: [
        "amount_inr > 500000",
        "customer_tier == 'new'",
        "payment_instrument == 'net_terms'"
    ])


class PaymentConfig(BaseModel):
    accepted_instruments: List[str] = Field(default_factory=lambda: [
        "card", "upi_mandate", "x402", "razorpay_payment_link"
    ])
    settlement_currency: str = "INR"


class RefundConfig(BaseModel):
    agent_initiated_allowed: bool = False
    max_refund_pct: float = 15.0
    requires_human_approval: bool = True


class AgentIdentityConfig(BaseModel):
    require_signed_token: bool = True
    trusted_principals: List[str] = Field(default_factory=lambda: ["acme-corp", "bigco-procurement", "enterprise-agent-hub"])
    max_commitment_per_agent_inr: int = 5000000


class MerchantPolicy(BaseModel):
    version: str = "1.0"
    merchant: str = "acme-saas"
    authorization: AuthorizationRules = Field(default_factory=AuthorizationRules)
    products: List[ProductConfig] = Field(default_factory=list)
    payment: PaymentConfig = Field(default_factory=PaymentConfig)
    refund: RefundConfig = Field(default_factory=RefundConfig)
    agent_identity: AgentIdentityConfig = Field(default_factory=AgentIdentityConfig)


class NegotiationBounds(BaseModel):
    policy_version: str
    max_autonomous_inr: int
    discount_ceiling_pct: float
    margin_floor_pct: float
    floor_prices: Dict[str, int]
    list_prices: Dict[str, int]
    unit_costs: Dict[str, int]
    max_quantity_per_product: Dict[str, int]
    negotiable_products: List[str]
    non_negotiable_terms: List[str] = Field(default_factory=lambda: ["unlimited_refunds", "zero_liability", "post_settlement_dispute"])
    accepted_instruments: List[str]
    agent_initiated_refund: bool
    human_approval_rules: List[str]

    def validate_price(self, product_id: str, proposed_price: int) -> bool:
        floor = self.floor_prices.get(product_id, 0)
        return proposed_price >= floor

    def validate_discount(self, discount_pct: float) -> bool:
        return discount_pct <= self.discount_ceiling_pct

    def validate(self, result: Any) -> bool:
        """Validate if a NegotiationResult is within bounds."""
        if hasattr(result, "final_price_inr") and result.final_price_inr is not None:
            prod_id = getattr(result, "product_id", "")
            if prod_id and prod_id in self.floor_prices:
                if result.final_price_inr < self.floor_prices[prod_id]:
                    return False
        if hasattr(result, "discount_pct") and result.discount_pct is not None:
            if result.discount_pct > self.discount_ceiling_pct:
                return False
        return True


class BuyerRequest(BaseModel):
    intent: Literal["purchase", "renew", "refund", "negotiate"] = "purchase"
    product_id: str = "pro_annual"
    quantity: int = 1
    terms: Dict[str, Any] = Field(default_factory=dict)
    proposed_price_inr: Optional[int] = None
    buyer_id: str = "anonymous-ai-buyer"
    customer_tier: str = "standard"
    agent_token: Optional[str] = None
    raw_text: Optional[str] = None


class NegotiationRound(BaseModel):
    round: int
    agent: str = "negotiator"
    proposal: Dict[str, Any]
    confidence: float = 0.95
    within_bounds: bool = True
    clamped_fields: List[str] = Field(default_factory=list)


class NegotiationResult(BaseModel):
    status: Literal["accepted", "counter", "declined", "pending_approval"]
    product_id: str
    quantity: int
    final_price_inr: Optional[int] = None
    discount_pct: Optional[float] = None
    terms: Dict[str, Any] = Field(default_factory=dict)
    requires_human_approval: bool = False
    approval_reason: Optional[str] = None
    approval_url: Optional[str] = None
    rounds: List[NegotiationRound] = Field(default_factory=list)
    policy_version: str = "v1.0"
    clamped: bool = False
    message: str = ""
