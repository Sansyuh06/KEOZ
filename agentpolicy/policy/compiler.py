"""Policy Compiler: transforms high-level MerchantPolicy into deterministic executable bounds and protocol artifacts."""

import json
from pathlib import Path
from typing import Dict, Any
from .models import MerchantPolicy, NegotiationBounds
from .manifests import ManifestGenerator
from .dsl import PolicyDSL


class CompiledPolicyBundle:
    def __init__(
        self,
        policy: MerchantPolicy,
        bounds: NegotiationBounds,
        acp_manifest: Dict[str, Any],
        x402_config: Dict[str, Any],
        openapi_spec: Dict[str, Any],
        policy_hash: str
    ):
        self.policy = policy
        self.bounds = bounds
        self.acp_manifest = acp_manifest
        self.x402_config = x402_config
        self.openapi_spec = openapi_spec
        self.policy_hash = policy_hash
        self.version = policy.version

    def export(self, output_dir: Path) -> None:
        """Save all compiled artifacts to the designated directory."""
        output_dir.mkdir(parents=True, exist_ok=True)

        with open(output_dir / "policy_bounds.json", "w", encoding="utf-8") as f:
            json.dump(self.bounds.model_dump(), f, indent=2)

        with open(output_dir / "acp_manifest.json", "w", encoding="utf-8") as f:
            json.dump(self.acp_manifest, f, indent=2)

        with open(output_dir / "x402_config.json", "w", encoding="utf-8") as f:
            json.dump(self.x402_config, f, indent=2)

        with open(output_dir / "openapi.json", "w", encoding="utf-8") as f:
            json.dump(self.openapi_spec, f, indent=2)

        with open(output_dir / "compiled_meta.json", "w", encoding="utf-8") as f:
            json.dump({
                "merchant": self.policy.merchant,
                "version": self.policy.version,
                "hash": self.policy_hash,
                "compiled_at": str(Path(output_dir).stat().st_mtime if output_dir.exists() else "")
            }, f, indent=2)


class PolicyCompiler:
    @staticmethod
    def compile(policy: MerchantPolicy, base_url: str = "http://localhost:8000") -> CompiledPolicyBundle:
        """Compile a MerchantPolicy into deterministic executable bounds and manifests."""
        floor_prices: Dict[str, int] = {}
        list_prices: Dict[str, int] = {}
        unit_costs: Dict[str, int] = {}
        max_quantities: Dict[str, int] = {}
        negotiable_products = []

        for p in policy.products:
            floor_prices[p.id] = p.min_price_inr
            list_prices[p.id] = p.list_price_inr or (int(p.min_price_inr * 1.15) if p.min_price_inr > 0 else 50000)
            unit_costs[p.id] = p.unit_cost_inr or int(p.min_price_inr * 0.6)  # fallback 60% COGS
            max_quantities[p.id] = p.max_seats_per_transaction
            if p.min_price_inr == 0 or not p.requires_human_approval:
                negotiable_products.append(p.id)

        bounds = NegotiationBounds(
            policy_version=policy.version,
            max_autonomous_inr=policy.authorization.max_autonomous_inr,
            discount_ceiling_pct=policy.authorization.discount_ceiling_pct,
            margin_floor_pct=policy.authorization.margin_floor_pct,
            floor_prices=floor_prices,
            list_prices=list_prices,
            unit_costs=unit_costs,
            max_quantity_per_product=max_quantities,
            negotiable_products=negotiable_products,
            accepted_instruments=policy.payment.accepted_instruments,
            agent_initiated_refund=policy.refund.agent_initiated_allowed,
            human_approval_rules=policy.authorization.require_human_approval_when
        )

        acp_manifest = ManifestGenerator.generate_acp_manifest(policy, base_url)
        x402_config = ManifestGenerator.generate_x402_config(policy, base_url)
        openapi_spec = ManifestGenerator.generate_openapi_spec(policy, base_url)
        policy_hash = PolicyDSL.compute_hash(policy)

        return CompiledPolicyBundle(
            policy=policy,
            bounds=bounds,
            acp_manifest=acp_manifest,
            x402_config=x402_config,
            openapi_spec=openapi_spec,
            policy_hash=policy_hash
        )
