"""Provenance and hash chain generator for audit atoms."""

import hashlib
import json
from typing import Dict, Any


class ProvenanceTracker:
    @staticmethod
    def compute_atom_hash(previous_hash: str, atom_data: Dict[str, Any]) -> str:
        """Compute SHA-256 hash chaining previous atom hash with current payload."""
        content = json.dumps(atom_data, sort_keys=True)
        combined = f"{previous_hash}:{content}"
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]
