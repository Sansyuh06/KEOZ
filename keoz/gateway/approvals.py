"""ApprovalBridge for KEOZ: Human-in-the-loop with SQLite persistence."""

import time
import uuid
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List, Tuple
from ..policy.models import NegotiationResult, BuyerRequest
from ..storage import get_db_sync, get_db, init_db_sync, init_db


@dataclass
class ApprovalRecord:
    id: str
    request: Dict[str, Any]
    proposed_deal: Dict[str, Any]
    trigger_reasons: List[str]
    policy_version: str
    created_at: float = field(default_factory=time.time)
    status: str = "pending"  # "pending", "approved", "rejected", "countered"
    decided_by: Optional[str] = None
    decided_at: Optional[float] = None
    decision_notes: Optional[str] = None
    counter_terms: Optional[Dict[str, Any]] = None

    @property
    def decision_by(self) -> Optional[str]:
        return self.decided_by

    @decision_by.setter
    def decision_by(self, val: Optional[str]):
        self.decided_by = val

    @property
    def decision_at(self) -> Optional[float]:
        return self.decided_at

    @decision_at.setter
    def decision_at(self, val: Optional[float]):
        self.decided_at = val


class ApprovalBridge:
    """Manages persistent human approvals when an agent triggers an escalation rule."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self._store: Dict[str, ApprovalRecord] = {}
        init_db_sync()
        self._load_from_db()

    def _load_from_db(self) -> None:
        """Load pending & past approvals from SQLite into memory store."""
        try:
            with get_db_sync() as conn:
                cursor = conn.execute("SELECT * FROM approvals ORDER BY created_at DESC")
                rows = cursor.fetchall()
                for row in rows:
                    record = self._row_to_record(row)
                    self._store[record.id] = record
        except Exception:
            pass

    def _row_to_record(self, row) -> ApprovalRecord:
        return ApprovalRecord(
            id=row["id"],
            status=row["status"],
            request=json.loads(row["request"]) if isinstance(row["request"], str) else row["request"],
            proposed_deal=json.loads(row["proposed_deal"]) if isinstance(row["proposed_deal"], str) else row["proposed_deal"],
            trigger_reasons=json.loads(row["trigger_reasons"]) if isinstance(row["trigger_reasons"], str) else row["trigger_reasons"],
            policy_version=row["policy_version"],
            created_at=row["created_at"],
            decided_by=row["decided_by"],
            decided_at=row["decided_at"],
            decision_notes=row["decision_notes"],
            counter_terms=json.loads(row["counter_terms"]) if row["counter_terms"] and isinstance(row["counter_terms"], str) else row["counter_terms"]
        )

    def create_approval_request(
        self,
        buyer_request: BuyerRequest,
        proposed_result: NegotiationResult,
        trigger_reasons: List[str],
        policy_version: str
    ) -> Tuple[ApprovalRecord, str]:
        """Create a pending approval record, persist to SQLite, and return unique URL."""
        approval_id = f"appr_{uuid.uuid4().hex[:10]}"
        approval_url = f"{self.base_url}/approve/{approval_id}"

        record = ApprovalRecord(
            id=approval_id,
            request=buyer_request.model_dump(),
            proposed_deal=proposed_result.model_dump(),
            trigger_reasons=trigger_reasons,
            policy_version=policy_version,
            created_at=time.time(),
            status="pending"
        )
        self._store[approval_id] = record

        # Persist to SQLite
        try:
            with get_db_sync() as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO approvals 
                       (id, status, request, proposed_deal, trigger_reasons, policy_version, created_at, decided_by, decided_at, decision_notes, counter_terms)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (record.id, record.status, json.dumps(record.request),
                     json.dumps(record.proposed_deal), json.dumps(record.trigger_reasons),
                     record.policy_version, record.created_at, record.decided_by, record.decided_at,
                     record.decision_notes, json.dumps(record.counter_terms) if record.counter_terms else None)
                )
                conn.commit()
        except Exception:
            pass

        return record, approval_url

    async def create_approval_request_async(
        self,
        buyer_request: BuyerRequest,
        proposed_result: NegotiationResult,
        trigger_reasons: List[str],
        policy_version: str
    ) -> Tuple[ApprovalRecord, str]:
        """Async create approval request with direct aiosqlite persist."""
        await init_db()
        approval_id = f"appr_{uuid.uuid4().hex[:10]}"
        approval_url = f"{self.base_url}/approve/{approval_id}"
        req_dict = buyer_request.model_dump()
        deal_dict = proposed_result.model_dump()
        now = time.time()

        record = ApprovalRecord(
            id=approval_id,
            request=req_dict,
            proposed_deal=deal_dict,
            trigger_reasons=trigger_reasons,
            policy_version=policy_version,
            created_at=now,
            status="pending"
        )
        self._store[approval_id] = record

        async with get_db() as db:
            await db.execute(
                """INSERT OR REPLACE INTO approvals 
                   (id, status, request, proposed_deal, trigger_reasons, policy_version, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (approval_id, "pending", json.dumps(req_dict), json.dumps(deal_dict), json.dumps(trigger_reasons), policy_version, now)
            )
            await db.commit()

        return record, approval_url

    def get_approval(self, approval_id: str) -> Optional[ApprovalRecord]:
        return self._store.get(approval_id)

    async def get_approval_async(self, approval_id: str) -> Optional[ApprovalRecord]:
        if approval_id in self._store:
            return self._store[approval_id]
        async with get_db() as db:
            cursor = await db.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,))
            row = await cursor.fetchone()
            if row:
                rec = self._row_to_record(row)
                self._store[approval_id] = rec
                return rec
        return None

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
        """Record a human decision on a pending request and sync to SQLite."""
        record = self._store.get(approval_id)
        if not record:
            return None

        record.status = decision
        record.decided_by = decided_by
        record.decided_at = time.time()
        record.decision_notes = notes
        record.counter_terms = counter_terms

        # Update SQLite
        try:
            with get_db_sync() as conn:
                conn.execute(
                    """UPDATE approvals SET 
                       status = ?, decided_by = ?, decided_at = ?, decision_notes = ?, counter_terms = ?
                       WHERE id = ?""",
                    (decision, decided_by, record.decided_at, notes,
                     json.dumps(counter_terms) if counter_terms else None, approval_id)
                )
                conn.commit()
        except Exception:
            pass

        return record

    async def decide_async(
        self,
        approval_id: str,
        decision: str,
        decided_by: str = "merchant_finance_lead",
        notes: str = "",
        counter_terms: Optional[Dict[str, Any]] = None
    ) -> Optional[ApprovalRecord]:
        """Async decision handler writing to aiosqlite."""
        record = self._store.get(approval_id)
        if not record:
            record = await self.get_approval_async(approval_id)
        if not record:
            return None

        now = time.time()
        record.status = decision
        record.decided_by = decided_by
        record.decided_at = now
        record.decision_notes = notes
        record.counter_terms = counter_terms

        async with get_db() as db:
            await db.execute(
                """UPDATE approvals SET 
                   status = ?, decided_by = ?, decided_at = ?, decision_notes = ?, counter_terms = ?
                   WHERE id = ?""",
                (decision, decided_by, now, notes,
                 json.dumps(counter_terms) if counter_terms else None, approval_id)
            )
            await db.commit()

        return record
