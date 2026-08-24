"""Audit Atom data structures for immutable decision logging."""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional
import time
import json
import hashlib


@dataclass
class AuditAtom:
    atom_id: str
    atom_type: str  # "bounds_compiled", "negotiation_round", "authorization_decision", "human_approval", "settlement", "policy_recompiled"
    policy_version: str
    policy_hash: str
    timestamp: float = field(default_factory=time.time)
    payload: Dict[str, Any] = field(default_factory=dict)
    provenance_hash: Optional[str] = None
    prev_hash: Optional[str] = None
    atom_hash: Optional[str] = None

    def __post_init__(self):
        if not self.atom_hash:
            self.atom_hash = self.compute_hash()
        if not self.provenance_hash:
            self.provenance_hash = self.atom_hash

    def compute_hash(self) -> str:
        content = f"{self.prev_hash or ''}{self.atom_type}{self.policy_version}{self.policy_hash}{json.dumps(self.payload, sort_keys=True)}{self.timestamp}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())
