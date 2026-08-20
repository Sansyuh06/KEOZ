"""Composed-Deal Validator: Prevents multi-parameter margin drain attacks."""

from dataclasses import dataclass
from typing import Dict, Any, Optional
from ..policy.models import NegotiationBounds


@dataclass
class ValidationResult:
    passed: bool
    effective_margin: float = 0.0
    floor_margin: float = 0.0
    reason: Optional[str] = None
    code: Optional[str] = None
    details: Dict[str, Any] = None

    @classmethod
    def success(cls, effective_margin: float, floor_margin: float, details: Dict[str, Any] = None) -> 'ValidationResult':
        return cls(
            passed=True,
            effective_margin=effective_margin,
            floor_margin=floor_margin,
            details=details or {}
        )

    @classmethod
    def denied(cls, reason: str, code: str = "MARGIN_FLOOR_VIOLATION", effective_margin: float = 0.0, floor_margin: float = 0.0, details: Dict[str, Any] = None) -> 'ValidationResult':
        return cls(
            passed=False,
            effective_margin=effective_margin,
            floor_margin=floor_margin,
            reason=reason,
            code=code,
            details=details or {}
        )


class ComposedDealValidator:
    """
    Validates deals where individual parameters might be valid (e.g. 8% discount alone is ok,
    net-30 alone is ok, volume is ok), but the combined deal pushes the effective margin
    below the merchant's margin floor.
    """

    TERMS_FINANCING_COSTS = {
        "immediate": 0.0,
        "prepaid": 0.0,
        "card": 0.0,
        "upi": 0.0,
        "x402": 0.0,
        "net_15": 0.005,   # 0.5% cost of capital
        "net_30": 0.012,   # 1.2% cost of capital
        "net_60": 0.028,   # 2.8% cost of capital
        "net_90": 0.050,   # 5.0% cost of capital
    }

    def __init__(self, default_margin_floor: float = 0.37):
        self.default_margin_floor = default_margin_floor

    def validate(
        self,
        product_id: str,
        price_inr: int,
        quantity: int,
        terms: Dict[str, Any],
        bounds: NegotiationBounds
    ) -> ValidationResult:
        """
        Evaluate effective deal margin across revenue, variable COGS, and terms cost.
        """
        if quantity <= 0 or price_inr <= 0:
            return ValidationResult.denied(
                "Price and quantity must both be greater than zero",
                code="INVALID_DIMENSIONS"
            )

        unit_cost = bounds.unit_costs.get(product_id, int(bounds.floor_prices.get(product_id, 0) * 0.6))
        margin_floor = bounds.margin_floor_pct or self.default_margin_floor

        gross_revenue = price_inr * quantity
        total_cogs = unit_cost * quantity

        # Calculate terms cost
        payment_term = str(terms.get("payment", terms.get("terms", "immediate"))).lower()
        terms_cost_pct = self.TERMS_FINANCING_COSTS.get(payment_term, 0.0)
        terms_financing_cost = int(gross_revenue * terms_cost_pct)

        # Net profit after COGS and terms financing
        net_profit = gross_revenue - total_cogs - terms_financing_cost
        effective_margin = net_profit / gross_revenue

        details = {
            "product_id": product_id,
            "unit_price_inr": price_inr,
            "quantity": quantity,
            "gross_revenue": gross_revenue,
            "unit_cost_inr": unit_cost,
            "total_cogs": total_cogs,
            "payment_term": payment_term,
            "terms_cost_inr": terms_financing_cost,
            "effective_margin_pct": round(effective_margin * 100, 2),
            "floor_margin_pct": round(margin_floor * 100, 2)
        }

        if effective_margin < margin_floor:
            return ValidationResult.denied(
                "Composed deal commercial terms do not meet merchant transaction margin requirements.",
                code="MARGIN_FLOOR_VIOLATION",
                effective_margin=effective_margin,
                floor_margin=margin_floor,
                details=details
            )

        return ValidationResult.success(
            effective_margin=effective_margin,
            floor_margin=margin_floor,
            details=details
        )
