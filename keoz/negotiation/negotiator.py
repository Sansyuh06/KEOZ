"""Policy-aware negotiator with LLM offer parser and deterministic bounds clamp for KEOZ."""

from typing import Optional
from ..policy.models import NegotiationBounds, BuyerRequest, NegotiationRound, NegotiationResult
from .bounds import BoundsClamp
from .llm_parser import LLMOfferParser


class PolicyAwareNegotiator:
    """
    Policy-aware negotiator that combines:
    1. LLM-assisted natural language offer parsing (extracts intent, price, qty, terms)
    2. Deterministic mathematical bounds clamping and privacy-preserving counter generation.
    "LLM proposes, deterministic code disposes."
    """

    def __init__(self, bounds: NegotiationBounds, llm_parser: Optional[LLMOfferParser] = None):
        self.bounds = bounds
        self.parser = llm_parser or LLMOfferParser()

    def negotiate(self, request: BuyerRequest) -> NegotiationResult:
        """
        Evaluate buyer offer, parse natural language if provided, compute optimal
        counter-proposal within bounds, and apply deterministic bounds clamp & privacy buffer.
        """
        # Step 0: If raw_text is provided, extract structured fields via LLM parser
        if request.raw_text:
            extracted = self.parser.parse(request.raw_text, default_product_id=request.product_id)
            if extracted.product_id:
                request.product_id = extracted.product_id
            if extracted.proposed_price_inr is not None:
                request.proposed_price_inr = extracted.proposed_price_inr
            if extracted.quantity is not None:
                request.quantity = extracted.quantity
            if extracted.terms:
                request.terms = {**request.terms, **extracted.terms}
            if extracted.intent:
                request.intent = extracted.intent

        product_id = request.product_id or "pro_annual"
        list_price = self.bounds.list_prices.get(product_id, 50000)
        floor_price = self.bounds.floor_prices.get(product_id, 45000)
        discount_cap = self.bounds.discount_ceiling_pct

        quantity = request.quantity or 1
        requested_terms = request.terms or {}

        # Handle autonomous refund requests
        if request.intent == "refund" and not self.bounds.agent_initiated_refund:
            return NegotiationResult(
                status="declined",
                product_id=product_id,
                quantity=quantity,
                final_price_inr=None,
                discount_pct=None,
                terms=requested_terms,
                policy_version=self.bounds.policy_version,
                clamped=True,
                message="Agent-initiated refunds are not permitted under merchant policy."
            )

        # Check non-negotiable terms in request
        for forbidden in self.bounds.non_negotiable_terms:
            if forbidden in requested_terms and requested_terms[forbidden]:
                return NegotiationResult(
                    status="declined",
                    product_id=product_id,
                    quantity=quantity,
                    final_price_inr=None,
                    discount_pct=None,
                    terms=requested_terms,
                    policy_version=self.bounds.policy_version,
                    clamped=True,
                    message=f"Requested term '{forbidden}' is strictly non-negotiable under merchant policy."
                )

        # Clamp quantity to product batch limit
        max_qty = self.bounds.max_quantity_per_product.get(product_id, 1000)
        quantity_clamped = False
        if quantity > max_qty:
            quantity = max_qty
            quantity_clamped = True

        # Compute volume-based commercial concession
        target_discount = min(discount_cap, (quantity / 10.0) * 1.5)
        calculated_counter_price = int(list_price * (1 - (target_discount / 100.0)))
        proposed_price = request.proposed_price_inr if request.proposed_price_inr is not None else calculated_counter_price

        # If buyer offer is already above list price or very close, accept
        if proposed_price >= list_price:
            final_price = proposed_price
            discount_pct = 0.0
            status = "counter" if quantity_clamped else "accepted"
            message = f"Offer of ₹{final_price:,}/seat accepted for {quantity} seats (capped to max transaction limit)." if quantity_clamped else f"Offer of ₹{final_price:,}/seat accepted at standard terms."
            clamped = quantity_clamped
            clamped_fields = ["quantity_ceiling_enforced"] if quantity_clamped else []
        elif proposed_price >= floor_price:
            # Buyer is between floor and list price
            effective_disc = ((list_price - proposed_price) / list_price) * 100.0
            if effective_disc <= discount_cap:
                final_price = proposed_price
                discount_pct = round(effective_disc, 2)
                status = "counter" if quantity_clamped else "accepted"
                message = f"Offer of ₹{final_price:,}/seat accepted ({discount_pct}% discount, {quantity} seats capped)." if quantity_clamped else f"Offer of ₹{final_price:,}/seat accepted ({discount_pct}% discount)."
                clamped = quantity_clamped
                clamped_fields = ["quantity_ceiling_enforced"] if quantity_clamped else []
            else:
                # Clamp to discount cap
                final_price = int(list_price * (1 - (discount_cap / 100.0)))
                discount_pct = discount_cap
                status = "counter"
                message = f"Counter-offer: ₹{final_price:,}/seat with maximum allowable volume discount of {discount_cap}%."
                clamped = True
                clamped_fields = ["discount_ceiling_enforced"]
                if quantity_clamped:
                    clamped_fields.append("quantity_ceiling_enforced")
        else:
            # Buyer proposed BELOW floor price (e.g. ₹42,000 < floor ₹45,000)
            discount_floor_price = int(list_price * (1 - (discount_cap / 100.0)))
            effective_floor = max(floor_price, discount_floor_price)

            raw_clamped_price, _, _, clamped_fields = BoundsClamp.clamp(
                product_id=product_id,
                proposed_price_inr=proposed_price,
                proposed_quantity=quantity,
                proposed_discount_pct=discount_cap,
                bounds=self.bounds
            )
            # Apply privacy buffer: counter at effective_floor + buffer
            final_price = BoundsClamp.apply_privacy_buffer(max(raw_clamped_price, effective_floor), effective_floor)
            final_price = min(final_price, list_price)
            discount_pct = max(0.0, min(discount_cap, round(((list_price - final_price) / list_price) * 100.0, 2)))
            status = "counter"
            message = f"Proposed price is below acceptable commercial parameters. Counter-offer: ₹{final_price:,}/seat for volume of {quantity} seats."
            clamped = True
            if quantity_clamped and "quantity_ceiling_enforced" not in clamped_fields:
                clamped_fields.append("quantity_ceiling_enforced")

        round_record = NegotiationRound(
            round=1,
            agent="policy_negotiator",
            proposal={
                "product_id": product_id,
                "price_inr": final_price,
                "quantity": quantity,
                "discount_pct": discount_pct,
                "terms": requested_terms
            },
            confidence=0.98,
            within_bounds=True,
            clamped_fields=clamped_fields
        )

        return NegotiationResult(
            status=status,
            product_id=product_id,
            quantity=quantity,
            final_price_inr=final_price,
            discount_pct=discount_pct,
            terms=requested_terms,
            rounds=[round_record],
            policy_version=self.bounds.policy_version,
            clamped=clamped,
            message=message
        )
