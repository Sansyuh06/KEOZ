"""Policy DSL loader, validator, and hasher for KEOZ."""

import hashlib
import json
from pathlib import Path
from typing import Union, Dict, Any
import yaml
from .models import MerchantPolicy


class PolicyDSL:
    @staticmethod
    def load_from_yaml(source: Union[str, Path]) -> MerchantPolicy:
        """Load and validate policy from YAML string or file path."""
        if isinstance(source, Path) or (isinstance(source, str) and (source.endswith(".yaml") or source.endswith(".yml")) and Path(source).is_file()):
            with open(source, "r", encoding="utf-8") as f:
                content = f.read()
        else:
            content = source

        raw_dict = yaml.safe_load(content)
        if not isinstance(raw_dict, dict):
            raise ValueError("Invalid YAML policy: Root must be a dictionary")

        return PolicyDSL.from_dict(raw_dict)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> MerchantPolicy:
        """Parse dictionary into MerchantPolicy with semantic validation."""
        policy = MerchantPolicy(**data)
        PolicyDSL.validate_semantics(policy)
        return policy

    @staticmethod
    def validate_semantics(policy: MerchantPolicy) -> None:
        """Validate logical invariants of the policy."""
        if policy.authorization.max_autonomous_inr < 0:
            raise ValueError("max_autonomous_inr cannot be negative")

        if not (0 <= policy.authorization.discount_ceiling_pct <= 100):
            raise ValueError("discount_ceiling_pct must be between 0 and 100")

        if not (0 <= policy.authorization.margin_floor_pct <= 1.0):
            raise ValueError("margin_floor_pct must be between 0.0 and 1.0 (e.g. 0.37 for 37%)")

        for product in policy.products:
            if product.min_price_inr < 0:
                raise ValueError(f"Product {product.id} min_price_inr cannot be negative")
            if product.unit_cost_inr < 0:
                raise ValueError(f"Product {product.id} unit_cost_inr cannot be negative")
            if product.list_price_inr is not None and product.list_price_inr < product.min_price_inr:
                raise ValueError(f"Product {product.id} list_price ({product.list_price_inr}) cannot be less than min_price ({product.min_price_inr})")

    @staticmethod
    def compute_hash(policy: MerchantPolicy) -> str:
        """Generate a deterministic SHA-256 hash of the policy contents."""
        dumped = json.dumps(policy.model_dump(), sort_keys=True)
        return hashlib.sha256(dumped.encode("utf-8")).hexdigest()[:16]
