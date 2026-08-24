"""Multi-merchant policy registry with hot-reload per merchant for KEOZ."""

import asyncio
import time
from typing import Dict, Optional, List
from pathlib import Path
from .policy.compiler import PolicyCompiler, CompiledPolicyBundle
from .policy.dsl import PolicyDSL
from .storage import get_db, init_db, get_db_sync, init_db_sync


DEFAULT_ACME_POLICY_YAML = """
version: "1.0"
merchant: "acme-saas"
authorization:
  max_autonomous_inr: 500000
  discount_ceiling_pct: 8.0
  margin_floor_pct: 0.37
  require_human_approval_when:
    - "amount_inr > 500000"
    - "customer_tier == 'new'"
    - "payment_instrument == 'net_terms'"
products:
  - id: "pro_annual"
    name: "Pro Annual License"
    min_price_inr: 45000
    list_price_inr: 50000
    unit_cost_inr: 28350
    max_seats_per_transaction: 50
    auto_renew: true
  - id: "enterprise_custom"
    name: "Enterprise Custom Suite"
    min_price_inr: 150000
    list_price_inr: 200000
    unit_cost_inr: 90000
    max_seats_per_transaction: 500
    requires_human_approval: true
payment:
  accepted_instruments:
    - "card"
    - "upi_mandate"
    - "x402"
    - "razorpay_payment_link"
  settlement_currency: "INR"
refund:
  agent_initiated_allowed: false
  max_refund_pct: 15.0
  requires_human_approval: true
agent_identity:
  require_signed_token: true
  trusted_principals:
    - "acme-corp"
    - "bigco-procurement"
    - "enterprise-agent-hub"
  max_commitment_per_agent_inr: 5000000
"""

DEFAULT_BIGCO_POLICY_YAML = """
version: "1.0"
merchant: "bigco-enterprise"
authorization:
  max_autonomous_inr: 2000000
  discount_ceiling_pct: 15.0
  margin_floor_pct: 0.30
  require_human_approval_when:
    - "amount_inr > 2000000"
    - "customer_tier == 'new'"
    - "payment_instrument == 'net_90'"
products:
  - id: "pro_annual"
    name: "BigCo Pro License"
    min_price_inr: 40000
    list_price_inr: 50000
    unit_cost_inr: 25000
    max_seats_per_transaction: 200
    auto_renew: true
  - id: "enterprise"
    name: "BigCo Enterprise Platform"
    min_price_inr: 120000
    list_price_inr: 180000
    unit_cost_inr: 70000
    max_seats_per_transaction: 1000
    requires_human_approval: false
payment:
  accepted_instruments:
    - "card"
    - "upi_mandate"
    - "x402"
    - "razorpay_payment_link"
    - "net_30"
  settlement_currency: "INR"
refund:
  agent_initiated_allowed: false
  max_refund_pct: 20.0
  requires_human_approval: true
agent_identity:
  require_signed_token: true
  trusted_principals:
    - "acme-corp"
    - "bigco-procurement"
    - "enterprise-agent-hub"
  max_commitment_per_agent_inr: 10000000
"""


class MerchantRegistry:
    """Multi-merchant policy registry with hot-reload per merchant."""

    def __init__(self):
        self._bundles: Dict[str, CompiledPolicyBundle] = {}
        self._yamls: Dict[str, str] = {}
        self._default_merchant: Optional[str] = None
        self.initialize_sync()

    def initialize_sync(self):
        """Synchronously initialize registry from SQLite or defaults."""
        init_db_sync()
        try:
            with get_db_sync() as conn:
                cursor = conn.execute("SELECT merchant_id, policy_yaml, active_version FROM merchant_configs")
                rows = cursor.fetchall()
                for row in rows:
                    m_id = row["merchant_id"]
                    p_yaml = row["policy_yaml"]
                    policy = PolicyDSL.load_from_yaml(p_yaml)
                    bundle = PolicyCompiler.compile(policy)
                    self._bundles[m_id] = bundle
                    self._yamls[m_id] = p_yaml
                    if not self._default_merchant:
                        self._default_merchant = m_id
        except Exception:
            pass

        # If empty, register default demo merchants
        if not self._bundles:
            self.register_merchant_sync("acme-saas", DEFAULT_ACME_POLICY_YAML, make_default=True)
            self.register_merchant_sync("bigco-enterprise", DEFAULT_BIGCO_POLICY_YAML, make_default=False)

    async def initialize(self):
        """Asynchronously initialize registry from SQLite."""
        await init_db()
        async with get_db() as db:
            cursor = await db.execute("SELECT merchant_id, policy_yaml, active_version FROM merchant_configs")
            rows = await cursor.fetchall()
            for row in rows:
                m_id = row["merchant_id"]
                p_yaml = row["policy_yaml"]
                policy = PolicyDSL.load_from_yaml(p_yaml)
                bundle = PolicyCompiler.compile(policy)
                self._bundles[m_id] = bundle
                self._yamls[m_id] = p_yaml
                if not self._default_merchant:
                    self._default_merchant = m_id

        if not self._bundles:
            await self.register_merchant("acme-saas", DEFAULT_ACME_POLICY_YAML, make_default=True)
            await self.register_merchant("bigco-enterprise", DEFAULT_BIGCO_POLICY_YAML, make_default=False)

    def get_bundle(self, merchant_id: Optional[str] = None) -> CompiledPolicyBundle:
        m_id = merchant_id or self._default_merchant or "acme-saas"
        if m_id not in self._bundles:
            if self._default_merchant and self._default_merchant in self._bundles:
                return self._bundles[self._default_merchant]
            raise ValueError(f"Merchant '{m_id}' not found in registry. Available: {list(self._bundles.keys())}")
        return self._bundles[m_id]

    def get_policy_yaml(self, merchant_id: Optional[str] = None) -> str:
        m_id = merchant_id or self._default_merchant or "acme-saas"
        return self._yamls.get(m_id, "")

    def register_merchant_sync(self, merchant_id: str, policy_yaml: str, make_default: bool = False) -> CompiledPolicyBundle:
        policy = PolicyDSL.load_from_yaml(policy_yaml)
        bundle = PolicyCompiler.compile(policy)

        try:
            with get_db_sync() as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO merchant_configs 
                       (merchant_id, policy_yaml, active_version, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (merchant_id, policy_yaml, bundle.version, time.time(), time.time())
                )
                conn.commit()
        except Exception:
            pass

        self._bundles[merchant_id] = bundle
        self._yamls[merchant_id] = policy_yaml
        if make_default or not self._default_merchant:
            self._default_merchant = merchant_id
        return bundle

    async def register_merchant(self, merchant_id: str, policy_yaml: str, make_default: bool = False) -> CompiledPolicyBundle:
        policy = PolicyDSL.load_from_yaml(policy_yaml)
        bundle = PolicyCompiler.compile(policy)

        async with get_db() as db:
            await db.execute(
                """INSERT OR REPLACE INTO merchant_configs 
                   (merchant_id, policy_yaml, active_version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (merchant_id, policy_yaml, bundle.version, time.time(), time.time())
            )
            await db.commit()

        self._bundles[merchant_id] = bundle
        self._yamls[merchant_id] = policy_yaml
        if make_default or not self._default_merchant:
            self._default_merchant = merchant_id
        return bundle

    async def update_policy(self, merchant_id: str, policy_yaml: str) -> CompiledPolicyBundle:
        return await self.register_merchant(merchant_id, policy_yaml)

    def update_policy_sync(self, merchant_id: str, policy_yaml: str) -> CompiledPolicyBundle:
        return self.register_merchant_sync(merchant_id, policy_yaml)

    def list_merchants(self) -> List[str]:
        return list(self._bundles.keys())

    def get_default_merchant(self) -> Optional[str]:
        return self._default_merchant


# Global Registry Instance
registry = MerchantRegistry()
