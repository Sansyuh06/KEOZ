"""Real-time metrics collector with WebSocket broadcast for KEOZ."""

import asyncio
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from collections import defaultdict
import json


@dataclass
class MetricsSnapshot:
    timestamp: float = field(default_factory=time.time)
    # Revenue & Savings
    revenue_protected_inr: int = 4250000
    revenue_recovered_inr: int = 1850000
    margin_saved_inr: int = 680000
    # Protection Metrics
    chargebacks_total: int = 14
    chargebacks_won: int = 13
    chargebacks_pending: int = 1
    mandates_total: int = 48
    mandates_recovered: int = 45
    mandates_failed: int = 3
    fraud_blocked: int = 29
    # Agentic Commerce
    ai_buyers_total: int = 142
    ai_auto_closed: int = 118
    ai_escalated: int = 24
    ai_revenue_inr: int = 18450000
    # Attacks & Neutralization
    attacks_total: int = 36
    attacks_blocked: int = 36
    attack_types: Dict[str, int] = field(default_factory=lambda: {
        "deep_discount": 12,
        "excessive_volume": 6,
        "forbidden_terms": 5,
        "refund_demand": 4,
        "overspend": 5,
        "composed_margin": 4
    })
    # System
    policy_version: str = "v1.0"
    uptime_seconds: float = 0.0
    cashflow_inflow: int = 18450000
    cashflow_outflow: int = 5420000
    recent_events: List[Dict[str, Any]] = field(default_factory=list)


class MetricsCollector:
    def __init__(self):
        self.snapshot = MetricsSnapshot()
        self.start_time = time.time()
        self._subscribers: List[asyncio.Queue] = []
        self._lock = asyncio.Lock()

    def get_snapshot_dict(self) -> Dict[str, Any]:
        self.snapshot.timestamp = time.time()
        self.snapshot.uptime_seconds = round(time.time() - self.start_time, 1)
        data = asdict(self.snapshot)
        return data

    def _safe_broadcast(self):
        """Safely trigger broadcast from sync or async context."""
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                asyncio.create_task(self.broadcast())
        except RuntimeError:
            pass

    async def broadcast(self):
        data = self.get_snapshot_dict()
        message = json.dumps(data)
        dead = []
        for q in list(self._subscribers):
            try:
                await q.put(message)
            except Exception:
                dead.append(q)
        for q in dead:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def subscribe(self) -> asyncio.Queue:
        q = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self._subscribers:
            self._subscribers.remove(q)

    # --- Protection Tracking ---
    def record_chargeback(self, won: bool = False, amount_inr: int = 0):
        self.snapshot.chargebacks_total += 1
        if won:
            self.snapshot.chargebacks_won += 1
            self.snapshot.revenue_recovered_inr += amount_inr
        else:
            self.snapshot.chargebacks_pending += 1
        self._add_event("CHARGEBACK", f"Chargeback {'WON' if won else 'PENDING'} for ₹{amount_inr:,}")
        self._safe_broadcast()

    def record_mandate(self, recovered: bool = False, amount_inr: int = 0):
        self.snapshot.mandates_total += 1
        if recovered:
            self.snapshot.mandates_recovered += 1
            self.snapshot.revenue_recovered_inr += amount_inr
        else:
            self.snapshot.mandates_failed += 1
        self._add_event("MANDATE", f"Mandate {'RECOVERED' if recovered else 'FAILED'} for ₹{amount_inr:,}")
        self._safe_broadcast()

    def record_fraud_blocked(self, amount_inr: int = 0):
        self.snapshot.fraud_blocked += 1
        self.snapshot.revenue_protected_inr += amount_inr
        self._add_event("FRAUD_BLOCKED", f"Suspicious transaction of ₹{amount_inr:,} blocked")
        self._safe_broadcast()

    # --- Revenue Optimization ---
    def record_margin_saved(self, amount_inr: int):
        self.snapshot.margin_saved_inr += amount_inr
        self._safe_broadcast()

    # --- Agentic Commerce ---
    def record_ai_transaction(self, auto_closed: bool = True, escalated: bool = False, amount_inr: int = 0):
        self.snapshot.ai_buyers_total += 1
        if auto_closed:
            self.snapshot.ai_auto_closed += 1
            self.snapshot.ai_revenue_inr += amount_inr
            self.snapshot.cashflow_inflow += amount_inr
            self._add_event("AI_DEAL_SETTLED", f"Autonomous deal settled for ₹{amount_inr:,}")
        elif escalated:
            self.snapshot.ai_escalated += 1
            self._add_event("AI_ESCALATED", f"Deal escalated for human approval (₹{amount_inr:,})")
        self._safe_broadcast()

    # --- Attacks ---
    def record_attack(self, attack_type: str, blocked: bool = True, description: str = "", amount_inr: int = 0):
        self.snapshot.attacks_total += 1
        if attack_type not in self.snapshot.attack_types:
            self.snapshot.attack_types[attack_type] = 0
        self.snapshot.attack_types[attack_type] += 1
        if blocked:
            self.snapshot.attacks_blocked += 1
            if amount_inr > 0:
                self.snapshot.revenue_protected_inr += amount_inr
        self._add_event("ATTACK_NEUTRALIZED" if blocked else "ATTACK_DETECTED", f"[{attack_type.upper()}] {description or 'Adversarial attempt neutralized'}")
        self._safe_broadcast()

    def update_policy_version(self, version: str):
        self.snapshot.policy_version = version
        self._add_event("POLICY_UPDATED", f"Merchant policy recompiled to {version}")
        self._safe_broadcast()

    def _add_event(self, event_type: str, message: str):
        event = {
            "time": time.strftime("%H:%M:%S"),
            "type": event_type,
            "message": message
        }
        self.snapshot.recent_events.insert(0, event)
        if len(self.snapshot.recent_events) > 50:
            self.snapshot.recent_events.pop()


# Global Singleton
metrics = MetricsCollector()
