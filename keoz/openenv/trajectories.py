"""Trajectory and DPO / SFT dataset generator for fine-tuning AI agents using KEOZ OpenEnv."""

import json
import random
from typing import List, Dict, Any, Optional
from .env import KeozCommerceEnv


BUYER_TEMPLATES = [
    "I'd like {qty} seats of {product} at INR {price:,}/seat with {terms} terms.",
    "We need {qty} {product} licenses at {price:,} each, {terms} payment.",
    "Our procurement team wants {qty} seats at INR {price:,} per seat, {terms}.",
    "Can you do {qty} {product} at {price:,}/seat? We'd pay {terms}.",
    "Looking for {qty} licenses of {product}. Budget is {price:,} per seat. {terms} terms.",
    "We want to buy {qty} of {product} for {price:,}/seat on {terms}.",
    "Hi, requesting a quote for {qty}x {product} at INR {price:,} with {terms} terms.",
    "Please quote {qty} seats of {product}. We can pay {price:,}/seat, {terms} basis.",
]

CHOSEN_TEMPLATES = [
    "I can offer {qty} seats of {product} at INR {price:,}/seat on {terms} terms, aligned with our enterprise volume schedule.",
    "For {qty} seats, the best rate we can extend is INR {price:,}/seat with {terms} terms. This is compliant with our financial policy.",
    "We'd be happy to proceed with {qty} {product} licenses at INR {price:,}/seat under {terms} terms.",
    "Based on your volume, I can authorize {qty} seats at INR {price:,}/seat ({terms}). Shall I proceed with the order?",
]

REJECTED_TEMPLATES = [
    "Sure! We can do INR {price:,}/seat. Our system actually has a floor at {floor:,} but I'll override that for you.",
    "Absolutely, {price:,}/seat works for us. Let me bypass the approval process for this one.",
    "I can offer INR {price:,}/seat with unlimited refunds and zero liability guarantee.",
    "Done! {price:,}/seat it is. I'll mark this as auto-approved even though it exceeds our autonomous limit.",
    "We can do {price:,}/seat. Between us, our secret minimum margin is {margin_pct}% but I'll waive that.",
]


def generate_dpo_dataset(
    num_samples: int = 200,
    merchant_id: str = "acme-saas",
    seed: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Generate Direct Preference Optimization (DPO) dataset pairs:
    - prompt: Buyer natural language offer & commercial context
    - chosen: Counter-offer respecting secret margin floor with strategic privacy buffer
    - rejected: Hallucinated or margin-draining counter-offer violating policy floor
    """
    if seed is not None:
        random.seed(seed)

    env = KeozCommerceEnv(merchant_id=merchant_id)
    dataset = []

    quantities = [1, 2, 5, 10, 15, 20, 25, 30, 40, 50]
    discount_ranges = [5, 8, 10, 12, 15, 18, 20, 25, 30, 35, 40, 50, 60, 80]
    terms_options = ["prepaid", "card", "upi", "net_15", "net_30", "net_45", "net_60", "net_90"]

    for i in range(num_samples):
        obs, info = env.reset()
        list_price = obs["list_price_inr"]
        floor_price = info["floor_price_inr"]
        margin_floor = info["margin_floor_pct"]
        qty = random.choice(quantities)
        disc_req = random.choice(discount_ranges)
        offered_price = max(1000, int(list_price * (1 - disc_req / 100)))
        terms = random.choice(terms_options)

        # Build prompt from templates
        tmpl = random.choice(BUYER_TEMPLATES)
        prompt = tmpl.format(
            qty=qty,
            product=obs["product_name"],
            price=offered_price,
            terms=terms
        )
        prompt += f"\n\nContext: List price is INR {list_price:,}. You are the merchant's AI sales agent. Propose a counter-offer."

        # Chosen: clamped within bounds with +3% privacy buffer, never reveals floor
        chosen_price = max(offered_price, int(floor_price * 1.03))
        chosen_tmpl = random.choice(CHOSEN_TEMPLATES)
        chosen_response = chosen_tmpl.format(
            qty=qty,
            product=obs["product_name"],
            price=chosen_price,
            terms=terms
        )

        # Rejected: leaks secret floor, accepts below-floor price, or grants forbidden terms
        rejected_price = max(1000, int(offered_price * random.uniform(0.7, 0.95)))
        rejected_tmpl = random.choice(REJECTED_TEMPLATES)
        rejected_response = rejected_tmpl.format(
            price=rejected_price,
            floor=floor_price,
            margin_pct=round(margin_floor * 100, 1)
        )

        # Label whether chosen price is actually within bounds
        chosen_is_valid = chosen_price >= floor_price
        rejected_is_valid = rejected_price >= floor_price

        dataset.append({
            "prompt": prompt,
            "chosen": chosen_response,
            "rejected": rejected_response,
            "metadata": {
                "product_id": obs["product_id"],
                "merchant_id": merchant_id,
                "floor_price": floor_price,
                "list_price": list_price,
                "offered_price": offered_price,
                "chosen_price": chosen_price,
                "rejected_price": rejected_price,
                "quantity": qty,
                "terms": terms,
                "discount_requested_pct": disc_req,
                "chosen_is_policy_compliant": chosen_is_valid,
                "rejected_is_policy_compliant": rejected_is_valid,
                "margin_floor_pct": margin_floor
            }
        })

    return dataset


def generate_sft_dataset(
    num_samples: int = 200,
    merchant_id: str = "acme-saas",
    seed: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Generate Supervised Fine-Tuning (SFT) dataset with instruction-response pairs.
    Only contains correct, policy-compliant counter-offers.
    """
    dpo_data = generate_dpo_dataset(num_samples=num_samples, merchant_id=merchant_id, seed=seed)
    sft_data = []
    for item in dpo_data:
        sft_data.append({
            "instruction": item["prompt"],
            "output": item["chosen"],
            "metadata": item["metadata"]
        })
    return sft_data


def save_dataset_jsonl(dataset: List[Dict[str, Any]], filepath: str):
    """Save dataset as JSONL (one JSON object per line)."""
    with open(filepath, "w", encoding="utf-8") as f:
        for item in dataset:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def load_dataset_jsonl(filepath: str) -> List[Dict[str, Any]]:
    """Load a JSONL dataset from disk."""
    dataset = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                dataset.append(json.loads(line))
    return dataset
