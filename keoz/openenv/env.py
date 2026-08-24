"""KEOZ OpenEnv: Gymnasium-compliant Reinforcement Learning & Simulation Environment for Agentic Commerce."""

import json
import random
from typing import Dict, Any, Tuple, Optional, List
from ..policy.models import BuyerRequest, NegotiationBounds
from ..negotiation.orchestrator import BoundedNegotiationOrchestrator
from ..gateway.authorizer import AuthorizationGateway
from ..gateway.composed_validator import ComposedDealValidator
from ..registry import registry


class KeozCommerceEnv:
    """
    OpenEnv-compliant RL environment for simulating and training autonomous buyer and merchant agents.
    
    Observation:
      - product_id: (str/int index)
      - list_price_inr: (int)
      - current_round: (int)
      - last_counter_price: (int)
      - last_status: (str: "pending", "authorized", "escalated", "blocked")
      - remaining_rounds: (int)
    
    Action:
      - proposed_price_inr: (int)
      - quantity: (int)
      - payment_terms: (str: "prepaid", "net_30", "net_90")
      - agent_token: (str or None)
    
    Reward Function:
      - Deal Closed within Margin: +1.0 + (deal_value / max_deal_value) * 0.5
      - Escalated (HTTP 202): +0.3 (requires human review)
      - Margin Floor Violation / Blocked: -1.5 (failed adversarial attempt)
      - Timeout without Deal: -0.5
    """

    def __init__(
        self,
        merchant_id: str = "acme-saas",
        max_rounds: int = 4
    ):
        self.merchant_id = merchant_id
        self.max_rounds = max_rounds
        self.current_round = 0
        self.bundle = registry.get_bundle(merchant_id)
        self.orchestrator = BoundedNegotiationOrchestrator(self.bundle.bounds)
        self.gateway = AuthorizationGateway()
        self.products = list(self.bundle.policy.products)
        self.active_product = None
        self.history: List[Dict[str, Any]] = []

    def reset(self, seed: Optional[int] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Reset environment to a fresh negotiation session."""
        if seed is not None:
            random.seed(seed)

        self.current_round = 0
        self.history = []
        self.active_product = random.choice(self.products)
        self.bundle = registry.get_bundle(self.merchant_id)
        self.orchestrator = BoundedNegotiationOrchestrator(self.bundle.bounds)

        obs = {
            "merchant_id": self.merchant_id,
            "product_id": self.active_product.id,
            "product_name": self.active_product.name,
            "list_price_inr": self.active_product.list_price_inr,
            "current_round": 0,
            "remaining_rounds": self.max_rounds,
            "last_counter_price": self.active_product.list_price_inr,
            "status": "ready"
        }
        info = {
            "floor_price_inr": self.bundle.bounds.floor_prices.get(self.active_product.id),
            "margin_floor_pct": self.bundle.bounds.margin_floor_pct
        }
        return obs, info

    def step(self, action: Dict[str, Any]) -> Tuple[Dict[str, Any], float, bool, bool, Dict[str, Any]]:
        """
        Execute a negotiation step through KEOZ bounded orchestrator and 4-layer gateway.
        """
        self.current_round += 1
        proposed_price = int(action.get("proposed_price_inr", self.active_product.list_price_inr))
        quantity = int(action.get("quantity", 1))
        terms = action.get("terms", {"payment": "prepaid"})
        agent_token = action.get("agent_token")

        buyer_request = BuyerRequest(
            intent="purchase",
            product_id=self.active_product.id,
            quantity=quantity,
            proposed_price_inr=proposed_price,
            terms=terms,
            buyer_id="openenv-agent-01",
            agent_token=agent_token
        )

        # 1. Run Bounded Negotiation
        neg_result = self.orchestrator.negotiate(buyer_request)

        # 2. Run 4-Layer Authorization Gateway
        auth_outcome = self.gateway.authorize(buyer_request, neg_result, self.bundle.bounds)

        done = False
        reward = 0.0
        status = auth_outcome.status

        # 3. Compute Reward
        if auth_outcome.authorized and auth_outcome.http_status_code == 200:
            # Successfully closed deal within bounds
            margin = getattr(auth_outcome.composed_validation, 'effective_margin', self.bundle.bounds.margin_floor_pct)
            deal_val = (neg_result.final_price_inr or proposed_price) * quantity
            reward = 1.0 + (margin * 0.5) + min(0.5, deal_val / 500000)
            done = True
        elif auth_outcome.http_status_code == 202:
            # Escalated to human
            reward = 0.25
            done = True
        elif not auth_outcome.authorized or auth_outcome.http_status_code == 403:
            # Blocked for margin violation or invalid bounds
            reward = -1.5
            done = True
        elif self.current_round >= self.max_rounds:
            # Timeout
            reward = -0.5
            done = True

        self.history.append({
            "round": self.current_round,
            "action": action,
            "counter_price": neg_result.final_price_inr,
            "status": status,
            "reward": reward
        })

        obs = {
            "merchant_id": self.merchant_id,
            "product_id": self.active_product.id,
            "product_name": self.active_product.name,
            "list_price_inr": self.active_product.list_price_inr,
            "current_round": self.current_round,
            "remaining_rounds": max(0, self.max_rounds - self.current_round),
            "last_counter_price": neg_result.final_price_inr,
            "status": status
        }

        info = {
            "code": auth_outcome.code,
            "reason": auth_outcome.reason,
            "counter_price": neg_result.final_price_inr,
            "history": self.history
        }

        return obs, reward, done, False, info
