"""Audit Atom data structures for immutable decision logging."""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional
import time
import json


@dataclass
class AuditAtom:
    atom_id: str
    atom_type: str                      # "bounds_compiled", "negotiation_round", "authorization_decision", "human_approval", "settlement"
    policy_version: str
    policy_hash: str
    timestamp: float = field(default_factory=time.time)
    payload: Dict[str, Any] = field(default_factory=dict)
    provenance_hash: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())
