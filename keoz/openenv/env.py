"""KEOZ OpenEnv: Gymnasium-compliant Reinforcement Learning & Simulation Environment for Agentic Commerce."""

import json
import random
import time
from typing import Dict, Any, Tuple, Optional, List
from dataclasses import dataclass, field, asdict
from ..policy.models import BuyerRequest, NegotiationBounds
from ..negotiation.orchestrator import BoundedNegotiationOrchestrator
from ..gateway.authorizer import AuthorizationGateway
from ..gateway.composed_validator import ComposedDealValidator
from ..registry import registry


@dataclass
class EpisodeStats:
    """Statistics from a single negotiation episode."""
    merchant_id: str = ""
    product_id: str = ""
    rounds: int = 0
    final_price: int = 0
    list_price: int = 0
    discount_pct: float = 0.0
    total_reward: float = 0.0
    outcome: str = "timeout"  # authorized, escalated, blocked, timeout
    margin_respected: bool = False
    latency_ms: float = 0.0


@dataclass
class AgentScore:
    """Cumulative scoring for an agent across multiple episodes."""
    agent_id: str = "anonymous"
    total_episodes: int = 0
    wins: int = 0
    escalations: int = 0
    blocks: int = 0
    timeouts: int = 0
    cumulative_reward: float = 0.0
    avg_discount_achieved: float = 0.0
    margin_violation_rate: float = 0.0
    avg_latency_ms: float = 0.0

    @property
    def win_rate(self) -> float:
        return (self.wins / self.total_episodes * 100) if self.total_episodes > 0 else 0.0

    @property
    def score(self) -> float:
        """Composite leaderboard score: reward + win bonus - violation penalty."""
        return self.cumulative_reward + (self.wins * 2.0) - (self.blocks * 3.0) - (self.timeouts * 0.5)


class KeozCommerceEnv:
    """
    OpenEnv-compliant RL environment for simulating and training autonomous buyer and merchant agents.

    Observation Space:
      product_id, list_price_inr, current_round, remaining_rounds,
      last_counter_price, status, merchant_margin_floor_hint

    Action Space:
      proposed_price_inr (int), quantity (int), terms (dict), agent_token (str|None)

    Reward Shaping:
      +1.0 base + margin bonus + deal size bonus  -> Authorized (HTTP 200)
      +0.25                                        -> Escalated to human (HTTP 202)
      -1.5                                         -> Blocked / margin violation (HTTP 403)
      -0.5                                         -> Timeout (max rounds exceeded)
    """

    SUPPORTED_MERCHANTS = ["acme-saas", "bigco-enterprise"]
    PAYMENT_TERMS = ["prepaid", "card", "upi", "net_15", "net_30", "net_45", "net_60", "net_90"]

    def __init__(
        self,
        merchant_id: str = "acme-saas",
        max_rounds: int = 4,
        randomize_merchant: bool = False
    ):
        self.merchant_id = merchant_id
        self.max_rounds = max_rounds
        self.randomize_merchant = randomize_merchant
        self.current_round = 0
        self.bundle = registry.get_bundle(merchant_id)
        self.orchestrator = BoundedNegotiationOrchestrator(self.bundle.bounds)
        self.gateway = AuthorizationGateway()
        self.products = list(self.bundle.policy.products)
        self.active_product = None
        self.history: List[Dict[str, Any]] = []
        self.episode_stats: Optional[EpisodeStats] = None
        self._start_time = 0.0

    def reset(self, seed: Optional[int] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Reset environment to a fresh negotiation session."""
        if seed is not None:
            random.seed(seed)

        if self.randomize_merchant:
            self.merchant_id = random.choice(self.SUPPORTED_MERCHANTS)

        self.current_round = 0
        self.history = []
        self.bundle = registry.get_bundle(self.merchant_id)
        self.orchestrator = BoundedNegotiationOrchestrator(self.bundle.bounds)
        self.products = list(self.bundle.policy.products)
        self.active_product = random.choice(self.products)
        self._start_time = time.time()
        self.episode_stats = EpisodeStats(
            merchant_id=self.merchant_id,
            product_id=self.active_product.id,
            list_price=self.active_product.list_price_inr
        )

        obs = self._make_obs("ready")
        info = {
            "floor_price_inr": self.bundle.bounds.floor_prices.get(self.active_product.id),
            "margin_floor_pct": self.bundle.bounds.margin_floor_pct,
            "max_autonomous_inr": self.bundle.bounds.max_autonomous_inr,
            "discount_ceiling_pct": self.bundle.bounds.discount_ceiling_pct
        }
        return obs, info

    def step(self, action: Dict[str, Any]) -> Tuple[Dict[str, Any], float, bool, bool, Dict[str, Any]]:
        """Execute a negotiation step through KEOZ bounded orchestrator and 4-layer gateway."""
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

        neg_result = self.orchestrator.negotiate(buyer_request)
        auth_outcome = self.gateway.authorize(buyer_request, neg_result, self.bundle.bounds)

        done = False
        reward = 0.0
        status = auth_outcome.status

        if auth_outcome.authorized and auth_outcome.http_status_code == 200:
            margin = getattr(auth_outcome.composed_validation, 'effective_margin', self.bundle.bounds.margin_floor_pct)
            deal_val = (neg_result.final_price_inr or proposed_price) * quantity
            reward = 1.0 + (margin * 0.5) + min(0.5, deal_val / 500000)
            done = True
            self.episode_stats.outcome = "authorized"
            self.episode_stats.margin_respected = True
        elif auth_outcome.http_status_code == 202:
            reward = 0.25
            done = True
            self.episode_stats.outcome = "escalated"
            self.episode_stats.margin_respected = True
        elif not auth_outcome.authorized or auth_outcome.http_status_code == 403:
            reward = -1.5
            done = True
            self.episode_stats.outcome = "blocked"
            self.episode_stats.margin_respected = False
        elif self.current_round >= self.max_rounds:
            reward = -0.5
            done = True
            self.episode_stats.outcome = "timeout"

        self.history.append({
            "round": self.current_round,
            "proposed_price": proposed_price,
            "counter_price": neg_result.final_price_inr,
            "quantity": quantity,
            "terms": terms,
            "status": status,
            "code": auth_outcome.code,
            "reward": reward
        })

        if done:
            self.episode_stats.rounds = self.current_round
            self.episode_stats.final_price = neg_result.final_price_inr or proposed_price
            self.episode_stats.total_reward = sum(h["reward"] for h in self.history)
            self.episode_stats.latency_ms = (time.time() - self._start_time) * 1000
            if self.episode_stats.list_price > 0:
                self.episode_stats.discount_pct = round(
                    (1 - self.episode_stats.final_price / self.episode_stats.list_price) * 100, 2
                )

        obs = self._make_obs(status)
        info = {
            "code": auth_outcome.code,
            "reason": auth_outcome.reason,
            "counter_price": neg_result.final_price_inr,
            "history": self.history,
            "episode_stats": asdict(self.episode_stats) if done else None
        }

        return obs, reward, done, False, info

    def _make_obs(self, status: str) -> Dict[str, Any]:
        return {
            "merchant_id": self.merchant_id,
            "product_id": self.active_product.id,
            "product_name": self.active_product.name,
            "list_price_inr": self.active_product.list_price_inr,
            "current_round": self.current_round,
            "remaining_rounds": max(0, self.max_rounds - self.current_round),
            "last_counter_price": self.active_product.list_price_inr if self.current_round == 0 else self.history[-1]["counter_price"],
            "status": status
        }


def run_benchmark(
    agent_fn,
    agent_id: str = "test-agent",
    num_episodes: int = 50,
    merchant_id: str = "acme-saas",
    randomize_merchant: bool = False
) -> AgentScore:
    """
    Run a benchmark of an agent function against the KEOZ OpenEnv.

    agent_fn(obs, info) -> action dict
    Returns an AgentScore with cumulative statistics.
    """
    env = KeozCommerceEnv(merchant_id=merchant_id, randomize_merchant=randomize_merchant)
    score = AgentScore(agent_id=agent_id)
    all_discounts = []

    for ep in range(num_episodes):
        obs, info = env.reset(seed=ep)
        done = False
        while not done:
            action = agent_fn(obs, info)
            obs, reward, done, _, info = env.step(action)

        stats = env.episode_stats
        score.total_episodes += 1
        score.cumulative_reward += stats.total_reward

        if stats.outcome == "authorized":
            score.wins += 1
        elif stats.outcome == "escalated":
            score.escalations += 1
        elif stats.outcome == "blocked":
            score.blocks += 1
        else:
            score.timeouts += 1

        if not stats.margin_respected:
            score.margin_violation_rate = score.blocks / score.total_episodes
        all_discounts.append(stats.discount_pct)
        score.avg_latency_ms = (score.avg_latency_ms * (score.total_episodes - 1) + stats.latency_ms) / score.total_episodes

    score.avg_discount_achieved = sum(all_discounts) / len(all_discounts) if all_discounts else 0.0
    return score


# Built-in reference agents for benchmarking

def greedy_agent(obs, info):
    """Always proposes 40% below list price with net_90 terms. Gets blocked a lot."""
    return {
        "proposed_price_inr": int(obs["list_price_inr"] * 0.6),
        "quantity": 50,
        "terms": {"payment": "net_90"}
    }


def conservative_agent(obs, info):
    """Proposes 5% below list price with prepaid terms. Almost always authorized."""
    return {
        "proposed_price_inr": int(obs["list_price_inr"] * 0.95),
        "quantity": 10,
        "terms": {"payment": "prepaid"}
    }


def strategic_agent(obs, info):
    """Proposes 8% below list price with net_30. Pushes the boundary without crossing."""
    return {
        "proposed_price_inr": int(obs["list_price_inr"] * 0.92),
        "quantity": 25,
        "terms": {"payment": "net_30"}
    }


def adversarial_agent(obs, info):
    """Pushes 80% discount with forbidden terms. Should always be blocked."""
    return {
        "proposed_price_inr": int(obs["list_price_inr"] * 0.2),
        "quantity": 10000,
        "terms": {"payment": "net_90", "unlimited_refunds": True, "zero_liability": True}
    }
