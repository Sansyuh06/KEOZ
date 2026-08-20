"""Human-in-the-loop approval bridge (HTTP 202 async pause)."""

import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple
from ..policy.models import NegotiationResult, BuyerRequest


@dataclass
class ApprovalRecord:
    id: str
    request: Dict[str, Any]
    proposed_deal: Dict[str, Any]
    trigger_reasons: List[str]
    policy_version: str
    created_at: float = field(default_factory=time.time)
    status: str = "pending"  # "pending", "approved", "rejected", "countered"
    decision_by: Optional[str] = None
    decision_at: Optional[float] = None
    decision_notes: Optional[str] = None
    counter_terms: Optional[Dict[str, Any]] = None


class ApprovalBridge:
    """Manages pending human approvals when an agent triggers an escalation rule."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self._store: Dict[str, ApprovalRecord] = {}

    def create_approval_request(
        self,
        buyer_request: BuyerRequest,
        proposed_result: NegotiationResult,
        trigger_reasons: List[str],
        policy_version: str
    ) -> Tuple[ApprovalRecord, str]:
        """Create a pending approval record and return its unique URL."""
        approval_id = f"appr_{uuid.uuid4().hex[:10]}"
        approval_url = f"{self.base_url}/approve/{approval_id}"

        record = ApprovalRecord(
            id=approval_id,
            request=buyer_request.model_dump(),
            proposed_deal=proposed_result.model_dump(),
            trigger_reasons=trigger_reasons,
            policy_version=policy_version
        )
        self._store[approval_id] = record
        return record, approval_url

    def get_approval(self, approval_id: str) -> Optional[ApprovalRecord]:
        return self._store.get(approval_id)

    def list_pending(self) -> List[ApprovalRecord]:
        return [rec for rec in self._store.values() if rec.status == "pending"]

    def list_all(self) -> List[ApprovalRecord]:
        return sorted(self._store.values(), key=lambda x: x.created_at, reverse=True)

    def decide(
        self,
        approval_id: str,
        decision: str,  # "approved", "rejected", "countered"
        decided_by: str = "merchant_finance_lead",
        notes: str = "",
        counter_terms: Optional[Dict[str, Any]] = None
    ) -> Optional[ApprovalRecord]:
        """Record a human decision on a pending request."""
        record = self._store.get(approval_id)
        if not record:
            return None

        record.status = decision
        record.decision_by = decided_by
        record.decision_at = time.time()
        record.decision_notes = notes
        record.counter_terms = counter_terms
        return record
