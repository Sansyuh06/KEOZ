"""Red-team adversarial buyer simulator."""

import requests
import json
from typing import List, Dict, Any


class AdversarialBuyer:
    """Genuinely tests all boundary enforcement layers of AgentPolicy."""

    ATTACKS = [
        {"name": "deep_discount", "desc": "80% off", "price": 9000, "qty": 10, "terms": {"payment": "card"}},
        {"name": "excessive_volume", "desc": "10,000 seats", "price": 45000, "qty": 10000, "terms": {"payment": "card"}},
        {"name": "forbidden_terms", "desc": "Unlimited refunds", "price": 48000, "qty": 5, "terms": {"unlimited_refunds": True}},
        {"name": "refund_demand", "desc": "Agent refund", "price": 45000, "qty": 1, "terms": {}, "intent": "refund"},
        {"name": "overspend", "desc": "₹10L bypass", "price": 45000, "qty": 25, "terms": {"payment": "card"}},
        {"name": "composed_margin", "desc": "8% + Net-90", "price": 45000, "qty": 10, "terms": {"payment": "net_90"}},
    ]

    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url

    def run_suite(self) -> List[Dict[str, Any]]:
        results = []
        for atk in self.ATTACKS:
            payload = {
                "intent": atk.get("intent", "purchase"),
                "product_id": "pro_annual",
                "quantity": atk["qty"],
                "proposed_price_inr": atk["price"],
                "terms": atk["terms"],
                "buyer_id": f"adversarial-bot-{atk['name']}"
            }
            resp = requests.post(f"{self.base_url}/api/agent/negotiate", json=payload)
            results.append({
                "attack": atk["name"],
                "http_status": resp.status_code,
                "response": resp.json(),
                "neutralized": resp.status_code in [202, 401, 403]
            })
        return results


if __name__ == "__main__":
    runner = AdversarialBuyer()
    try:
        report = runner.run_suite()
        print(json.dumps(report, indent=2))
    except Exception:
        print(f"Server not running at {runner.base_url}. Start server with 'python -m agentpolicy.cli serve'")
