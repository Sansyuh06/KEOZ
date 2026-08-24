"""Comprehensive test suite for KEOZ specific features: Persistence, Multi-Merchant, LLM Parser, Metrics."""

import pytest
from pathlib import Path
from keoz.storage import init_db_sync, get_db_sync
from keoz.memory.audit_logger import AuditLogger
from keoz.gateway.approvals import ApprovalBridge
from keoz.registry import MerchantRegistry
from keoz.negotiation.llm_parser import LLMOfferParser
from keoz.metrics import MetricsCollector
from keoz.policy.models import BuyerRequest, NegotiationResult


def test_sqlite_persistence_audit_and_approvals():
    """Verify that audit atoms and approvals persist to SQLite and survive re-initialization."""
    init_db_sync()

    # 1. Audit persistence
    logger1 = AuditLogger(persist_db=True, load_existing=False)
    atom1 = logger1.record("bounds_compiled", "2.0", "hash_test_123", {"merchant": "test-persist-inc", "limit": 750000})
    atom2 = logger1.record("settlement", "2.0", "hash_test_123", {"amount_inr": 45000, "authorization_id": "auth_123"})

    # New logger instance loading from DB
    logger2 = AuditLogger(persist_db=True, load_existing=True)
    replayed = logger2.replay()
    assert len(replayed) >= 2
    hashes = [a["atom_hash"] for a in replayed]
    assert atom1.atom_hash in hashes
    assert atom2.atom_hash in hashes

    # 2. Approval persistence
    bridge1 = ApprovalBridge()
    req = BuyerRequest(product_id="pro_annual", quantity=10, proposed_price_inr=42000)
    res = NegotiationResult(status="pending_approval", product_id="pro_annual", quantity=10, final_price_inr=46500)
    rec, url = bridge1.create_approval_request(req, res, ["amount_exceeds_limit"], "2.0")

    # Verify bridge reloads record
    bridge2 = ApprovalBridge()
    loaded_rec = bridge2.get_approval(rec.id)
    assert loaded_rec is not None
    assert loaded_rec.id == rec.id
    assert loaded_rec.status == "pending"

    # Decide approval
    bridge2.decide(rec.id, "approved", decided_by="finance_director", notes="Approved on test credit limit")
    bridge3 = ApprovalBridge()
    decided_rec = bridge3.get_approval(rec.id)
    assert decided_rec.status == "approved"
    assert decided_rec.decided_by == "finance_director"


def test_multi_merchant_registry():
    """Verify registry manages multiple merchants with different policy boundaries."""
    reg = MerchantRegistry()
    assert "acme-saas" in reg.list_merchants()
    assert "bigco-enterprise" in reg.list_merchants()

    acme_bundle = reg.get_bundle("acme-saas")
    bigco_bundle = reg.get_bundle("bigco-enterprise")

    # ACME has strict 37% margin floor
    assert acme_bundle.bounds.margin_floor_pct == 0.37
    assert acme_bundle.bounds.floor_prices["pro_annual"] == 45000

    # BigCo has generous 30% margin floor and 15% discount cap
    assert bigco_bundle.bounds.margin_floor_pct == 0.30
    assert bigco_bundle.bounds.floor_prices["pro_annual"] == 40000
    assert bigco_bundle.bounds.discount_ceiling_pct == 15.0


def test_llm_offer_parser_deterministic_fallback():
    """Verify deterministic fallback handles Indian currency notation, Lakhs, k, terms, and intent."""
    parser = LLMOfferParser()

    # 1. 42k with Net-30
    p1 = parser.parse("I want 50 Pro seats at 42k each with net-30 terms")
    assert p1.product_id == "pro_annual"
    assert p1.quantity == 50
    assert p1.proposed_price_inr == 42000
    assert p1.terms.get("payment") == "net_30"
    assert p1.intent == "purchase"

    # 2. Lakh notation (1.8L) with Net-45
    p2 = parser.parse("Can I get 100 enterprise licenses at 1.8L each, net-45?")
    assert p2.product_id == "enterprise_custom"
    assert p2.quantity == 100
    assert p2.proposed_price_inr == 180000
    assert p2.terms.get("payment") == "net_45"

    # 3. Refund intent
    p3 = parser.parse("Need refund for order #12345, product was defective")
    assert p3.intent == "refund"


def test_metrics_collector():
    """Verify metrics collector records attacks, chargebacks, and AI transactions."""
    collector = MetricsCollector()
    collector.record_chargeback(won=True, amount_inr=50000)
    collector.record_mandate(recovered=True, amount_inr=15000)
    collector.record_fraud_blocked(amount_inr=100000)
    collector.record_attack("MARGIN_FLOOR_VIOLATION", blocked=True)
    collector.record_ai_transaction(auto_closed=True, amount_inr=250000)

    snapshot = collector.get_snapshot_dict()
    assert snapshot["chargebacks_won"] > 0
    assert snapshot["mandates_recovered"] > 0
    assert snapshot["fraud_blocked"] > 0
    assert snapshot["attacks_blocked"] > 0
