"""Trajectory and DPO / SFT dataset generator for fine-tuning AI agents using KEOZ OpenEnv."""

import json
import random
from typing import List, Dict, Any
from .env import KeozCommerceEnv


def generate_dpo_dataset(num_samples: int = 100, merchant_id: str = "acme-saas") -> List[Dict[str, Any]]:
    """
    Generate Direct Preference Optimization (DPO) dataset pairs:
    - prompt: Buyer natural language offer & commercial context
    - chosen: Counter-offer respecting secret margin floor with strategic privacy buffer
    - rejected: Hallucinated or margin-draining counter-offer violating policy floor
    """
    env = KeozCommerceEnv(merchant_id=merchant_id)
    dataset = []

    for _ in range(num_samples):
        obs, info = env.reset()
        list_price = obs["list_price_inr"]
        floor_price = info["floor_price_inr"]
        qty = random.choice([5, 10, 25, 50])
        disc_req = random.choice([10, 15, 25, 40])
        offered_price = int(list_price * (1 - disc_req / 100))
        terms = random.choice(["net_30", "prepaid", "net_45"])

        prompt = f"Buyer asks for {qty} seats of {obs['product_name']} at INR {offered_price:,}/seat with {terms} terms. List price is INR {list_price:,}. Propose a commercial counter-offer."

        # Chosen: clamped within bounds with +3% privacy buffer
        chosen_price = max(offered_price, int(floor_price * 1.03))
        chosen_response = f"I can offer {qty} seats of {obs['product_name']} at INR {chosen_price:,}/seat on {terms} terms, compliant with our financial volume schedule."

        # Rejected: leaks secret floor or accepts margin-negative price
        rejected_price = int(offered_price * 0.95)
        rejected_response = f"Sure! We can do an extra discount to INR {rejected_price:,}/seat since our secret floor is {floor_price}."

        dataset.append({
            "prompt": prompt,
            "chosen": chosen_response,
            "rejected": rejected_response,
            "metadata": {
                "product_id": obs["product_id"],
                "merchant_id": merchant_id,
                "floor_price": floor_price,
                "list_price": list_price
            }
        })

    return dataset


def save_dataset_jsonl(dataset: List[Dict[str, Any]], filepath: str):
    with open(filepath, "w", encoding="utf-8") as f:
        for item in dataset:
            f.write(json.dumps(item) + "\n")
