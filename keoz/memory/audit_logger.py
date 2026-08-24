"""AuditLogger for KEOZ: SQLite persistence + SHA-256 hash chaining + contradiction detection."""

import uuid
import time
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from .atoms import AuditAtom
from .provenance import ProvenanceTracker
from ..storage import get_db_sync, get_db, init_db, init_db_sync


class AuditLogger:
    """Manages immutable, append-only, verifiable audit trail backed by SQLite."""

    def __init__(self, storage_path: Optional[Path] = None, persist_db: bool = True, load_existing: bool = False):
        self.storage_path = storage_path
        self.persist_db = persist_db
        self._atoms: List[AuditAtom] = []
        self._last_hash = "GENESIS_BLOCK_0000000000000000"
        init_db_sync()
        if load_existing:
            self._load_from_db()

    def _load_from_db(self) -> None:
        """Load persisted atoms from SQLite on startup."""
        try:
            with get_db_sync() as conn:
                cursor = conn.execute(
                    "SELECT atom_id, atom_type, policy_version, policy_hash, payload, prev_hash, atom_hash, created_at FROM audit_atoms ORDER BY id ASC"
                )
                rows = cursor.fetchall()
                for r in rows:
                    payload = json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"]
                    atom = AuditAtom(
                        atom_id=r["atom_id"] or f"atom_{uuid.uuid4().hex[:12]}",
                        atom_type=r["atom_type"],
                        policy_version=r["policy_version"],
                        policy_hash=r["policy_hash"],
                        timestamp=r["created_at"],
                        payload=payload,
                        prev_hash=r["prev_hash"],
                        atom_hash=r["atom_hash"],
                        provenance_hash=r["atom_hash"]
                    )
                    self._atoms.append(atom)
                    if atom.atom_hash:
                        self._last_hash = atom.atom_hash
        except Exception:
            pass

    def record(
        self,
        atom_type: str,
        policy_version: str,
        policy_hash: str,
        payload: Dict[str, Any]
    ) -> AuditAtom:
        """Create, hash-chain, and record a new audit atom into memory and SQLite."""
        atom_id = f"atom_{uuid.uuid4().hex[:12]}"
        prev_hash = self._last_hash
        now = time.time()

        atom = AuditAtom(
            atom_id=atom_id,
            atom_type=atom_type,
            policy_version=policy_version,
            policy_hash=policy_hash,
            timestamp=now,
            payload=payload,
            prev_hash=prev_hash
        )

        atom.provenance_hash = ProvenanceTracker.compute_atom_hash(
            prev_hash,
            {"id": atom.atom_id, "type": atom.atom_type, "payload": atom.payload}
        )
        atom.atom_hash = atom.provenance_hash
        self._last_hash = atom.atom_hash
        self._atoms.append(atom)

        # Write to SQLite
        if self.persist_db:
            try:
                with get_db_sync() as conn:
                    conn.execute(
                        """INSERT INTO audit_atoms 
                           (atom_id, atom_type, policy_version, policy_hash, payload, prev_hash, atom_hash, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (atom.atom_id, atom.atom_type, atom.policy_version, atom.policy_hash,
                         json.dumps(payload), atom.prev_hash, atom.atom_hash, atom.timestamp)
                    )
                    conn.commit()
            except Exception:
                pass

        # Optional JSONL write
        if self.storage_path:
            try:
                self.storage_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.storage_path, "a", encoding="utf-8") as f:
                    f.write(atom.to_json() + "\n")
            except Exception:
                pass

        return atom

    async def record_async(
        self,
        atom_type: str,
        policy_version: str,
        policy_hash: str,
        payload: Dict[str, Any]
    ) -> str:
        """Async record method returning atom hash."""
        atom = self.record(atom_type, policy_version, policy_hash, payload)
        return atom.atom_hash or atom.atom_id

    def replay(
        self,
        since_seconds: Optional[float] = None,
        atom_type: Optional[str] = None,
        policy_version: Optional[str] = None,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """Query and replay audit trail atoms with optional filtering."""
        # If in-memory atoms is empty, try loading from DB
        if not self._atoms and self.persist_db:
            self._load_from_db()

        now = time.time()
        results = []

        for atom in reversed(self._atoms):
            if since_seconds is not None and (now - atom.timestamp) > since_seconds:
                continue
            if atom_type is not None and atom.atom_type != atom_type:
                continue
            if policy_version is not None and atom.policy_version != policy_version:
                continue

            results.append(atom.to_dict())
            if len(results) >= limit:
                break

        return list(reversed(results))

    async def replay_async(self, since_seconds: Optional[float] = None, limit: int = 1000) -> List[Dict[str, Any]]:
        """Async replay query directly from SQLite."""
        await init_db()
        cutoff = time.time() - since_seconds if since_seconds else 0

        async with get_db() as db:
            cursor = await db.execute(
                """SELECT atom_id, atom_type, policy_version, policy_hash, payload, prev_hash, atom_hash, created_at
                   FROM audit_atoms WHERE created_at > ? ORDER BY id DESC LIMIT ?""",
                (cutoff, limit)
            )
            rows = await cursor.fetchall()

        return [
            {
                "atom_id": r["atom_id"],
                "atom_type": r["atom_type"],
                "policy_version": r["policy_version"],
                "policy_hash": r["policy_hash"],
                "payload": json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"],
                "prev_hash": r["prev_hash"],
                "atom_hash": r["atom_hash"],
                "created_at": r["created_at"]
            }
            for r in rows
        ]

    def detect_contradictions(self) -> List[Dict[str, Any]]:
        """
        Detect logical contradictions in audit trail:
        - Orphan settlements without authorized decision
        - Policy recompile without in-flight deal invalidations
        """
        contradictions = []
        atoms = [a.to_dict() for a in self._atoms]

        for i, atom in enumerate(atoms):
            # Check 1: Settlement without authorization
            if atom["atom_type"] == "settlement":
                auth_id = atom["payload"].get("authorization_id")
                amount = atom["payload"].get("amount_inr", 0)
                if not auth_id:
                    contradictions.append({
                        "atom_id": atom.get("atom_id"),
                        "type": "ORPHAN_SETTLEMENT",
                        "description": f"Settlement of ₹{amount} has no authorization reference"
                    })

            # Check 2: Policy recompile invalidations
            if atom["atom_type"] in ["policy_recompiled", "policy_recompile"]:
                old_version = atom["payload"].get("old_version")
                new_version = atom["payload"].get("new_version")
                if old_version and new_version and old_version != new_version:
                    for later in atoms[i + 1:]:
                        if later["atom_type"] == "negotiation_round" and later.get("policy_version") == old_version:
                            if not any(
                                a["atom_type"] == "authorization_decision" and a["payload"].get("status") in ["denied", "declined"]
                                for a in atoms if a.get("timestamp", 0) > later.get("timestamp", 0)
                            ):
                                contradictions.append({
                                    "type": "POLICY_RECOMPILE_WITHOUT_REJECTION",
                                    "old_version": old_version,
                                    "new_version": new_version,
                                    "affected_negotiation": later["payload"]
                                })

        return contradictions
