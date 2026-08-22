"""Negotiation bounds clamping and strategic privacy buffering."""

from typing import Tuple
from ..policy.models import NegotiationBounds


class BoundsClamp:
    """
    Ensures deterministic enforcement of policy limits on any proposal generated
    by LLMs or external agents. "LLM proposes, deterministic code disposes."
    """

    @staticmethod
    def clamp(
        product_id: str,
        proposed_price_inr: int,
        proposed_quantity: int,
        proposed_discount_pct: float,
        bounds: NegotiationBounds
    ) -> Tuple[int, int, float, list[str]]:
        """
        Hard clamp proposal parameters to merchant-configured bounds.
        Returns: (clamped_price, clamped_quantity, clamped_discount, clamped_fields)
        """
        clamped_fields = []

        # 1. Floor Price Check
        floor_price = bounds.floor_prices.get(product_id, 0)
        clamped_price = proposed_price_inr
        if clamped_price < floor_price:
            clamped_price = floor_price
            clamped_fields.append("price_floor_enforced")

        # 2. Discount Ceiling Check
        clamped_discount = proposed_discount_pct
        if clamped_discount > bounds.discount_ceiling_pct:
            clamped_discount = bounds.discount_ceiling_pct
            clamped_fields.append("discount_ceiling_enforced")

        # 3. Maximum Quantity Check
        max_qty = bounds.max_quantity_per_product.get(product_id, 1000)
        clamped_quantity = proposed_quantity
        if clamped_quantity > max_qty:
            clamped_quantity = max_qty
            clamped_fields.append("quantity_ceiling_enforced")

        return clamped_price, clamped_quantity, clamped_discount, clamped_fields

    @staticmethod
    def apply_privacy_buffer(price_inr: int, floor_price: int, buffer_pct: float = 0.03, max_buffer_inr: int = 500) -> int:
        """
        Privacy Protection Property:
        Never counter at the exact floor price (e.g. ₹4,500) which would leak the merchant's secret margin.
        Instead, counter at floor + strategic buffer (e.g. ₹4,650), so the buyer only discovers
        a strategic price zone (~₹4,600-4,700) without ever discovering the exact margin floor.
        """
        if price_inr <= floor_price:
            calculated_buffer = int(floor_price * buffer_pct)
            buffer = min(calculated_buffer, max_buffer_inr)
            if buffer < 50 and floor_price > 500:
                buffer = 50
            return floor_price + buffer
        return price_inr
