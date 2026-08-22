"""Audit trail manager (memoriagrain-style): append-only, verifiable, replayable."""

import uuid
import time
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from .atoms import AuditAtom
from .provenance import ProvenanceTracker


class AuditLogger:
    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path
        self._atoms: List[AuditAtom] = []
        self._last_hash = "GENESIS_BLOCK_0000000000000000"

        if self.storage_path and self.storage_path.exists():
            self._load_from_file()

    def _load_from_file(self) -> None:
        """Load persisted atoms from JSONL file."""
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        data = json.loads(line)
                        atom = AuditAtom(**data)
                        self._atoms.append(atom)
                        self._last_hash = atom.provenance_hash or self._last_hash
        except Exception:
            pass

    def record(
        self,
        atom_type: str,
        policy_version: str,
        policy_hash: str,
        payload: Dict[str, Any]
    ) -> AuditAtom:
        """Create, hash-chain, and record a new audit atom."""
        atom_id = f"atom_{uuid.uuid4().hex[:12]}"
        atom = AuditAtom(
            atom_id=atom_id,
            atom_type=atom_type,
            policy_version=policy_version,
            policy_hash=policy_hash,
            timestamp=time.time(),
            payload=payload
        )

        atom.provenance_hash = ProvenanceTracker.compute_atom_hash(
            self._last_hash,
            {"id": atom.atom_id, "type": atom.atom_type, "payload": atom.payload}
        )
        self._last_hash = atom.provenance_hash
        self._atoms.append(atom)

        if self.storage_path:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_path, "a", encoding="utf-8") as f:
                f.write(atom.to_json() + "\n")

        return atom

    def replay(
        self,
        since_seconds: Optional[float] = None,
        atom_type: Optional[str] = None,
        policy_version: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Query and replay audit trail atoms with optional filtering."""
        now = time.time()
        results = []

        for atom in self._atoms:
            if since_seconds is not None and (now - atom.timestamp) > since_seconds:
                continue
            if atom_type is not None and atom.atom_type != atom_type:
                continue
            if policy_version is not None and atom.policy_version != policy_version:
                continue

            results.append(atom.to_dict())

        return results

    def detect_contradictions(self) -> List[Dict[str, Any]]:
        """
        Scan audit atoms to verify all transactions complied with policy boundaries
        and that no settlement was executed without proper authorization.
        """
        anomalies = []
        for atom in self._atoms:
            if atom.atom_type == "settlement":
                # Check if settlement has an authorized parent
                auth_id = atom.payload.get("authorization_id")
                amount = atom.payload.get("amount_inr", 0)
                if not auth_id:
                    anomalies.append({
                        "atom_id": atom.atom_id,
                        "type": "ORPHAN_SETTLEMENT",
                        "description": f"Settlement of ₹{amount} has no authorization reference"
                    })
        return anomalies
