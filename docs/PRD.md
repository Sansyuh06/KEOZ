# AgentPolicy — Product Requirements Document

> **Product:** AgentPolicy — Merchant-Side Financial Policy Layer for Agentic Commerce  
> **Track:** 01 — AI Growth & Agentic Commerce (Razorpay Hackathon)  
> **Version:** 1.1 (Production & Submission Ready)

---

## 1. Executive Summary

### 1.1 Problem Statement
Merchants configure commercial rules for human interactions (dashboards, email approvals, spreadsheets, sales desks) but have **no machine-readable policy layer** to govern autonomous AI buyers. When enterprise procurement bots or autonomous agents attempt to purchase, negotiate, or subscribe, merchants face an unacceptable binary choice: **reject autonomous transactions entirely** or **accept unconstrained financial risk**.

### 1.2 Solution Overview
**AgentPolicy** is a declarative financial policy engine that establishes enforceable commercial boundaries for agentic commerce:
- **Compiles** merchant rules (`agentpolicy.yaml`) into deterministic runtime bounds.
- **Executes** bounded negotiation where LLMs extract natural-language intent while deterministic code clamps prices, volumes, and terms.
- **Enforces** a 4-layer Authorization Gateway (Agent Identity, Parameter Bounds, Composed Margin Floor, and Human Approval Routing) before any payment executes.
- **Interfaces** natively with Razorpay test-mode Orders, Payment Links, and x402 payment proof protocols.
- **Logs** an immutable, hash-chained audit trail (*memoriagrain*) tying every transaction to its governing policy version.

### 1.3 Core Insight
> It is not "catalog transformation." It is **delegated financial authority.**
>
> A machine-readable policy contract that tells an autonomous buyer: *"Here is what you may execute autonomously with my business, under these exact constraints — and here is precisely where you must route to a human."*

---

## 2. Problem Evidence & Market Context

### 2.1 The Emerging Agentic Commerce Gap
- **Rapid Rise of Autonomous Procurement**: Enterprise procurement teams and consumer platforms are rapidly deploying autonomous shopping and renewal agents (e.g. OpenAI Operator, Perplexity Shopping, corporate procurement bots).
- **Protocol Race**: Emerging standards like **x402**, **Agent Commerce Protocol (ACP)**, and **AP2 / Mandates** define buyer identity and payment transport, but deliberately **omit merchant commercial policy** (floor prices, discount ceilings, financing terms, and margin floors).
- **Merchant Trust Deficit**: Existing checkout flows require human intervention for custom volume, Net-30 credit terms, or discounted renewals. Without machine-readable commercial boundaries, merchants cannot expose autonomous checkout endpoints to third-party bots without risking margin drain.

### 2.2 Verified Merchant Pain Points
| Commercial Risk | Real-World Failure Mode | AgentPolicy Defense |
|---|---|---|
| **Sub-Floor Price Extraction** | Bot negotiates pricing below acceptable cost thresholds. | Hard floor price clamp + strategic privacy buffer. |
| **Composed Margin Drain** | Multi-variable concessions (e.g., 8% discount + Net-90 terms) pass individually but result in a margin-negative deal. | Composed-Deal Validator (`effective_margin ≥ margin_floor`). |
| **Unauthorized Credit Terms** | Bot demands Net-30/Net-60 terms without financial credit review. | Async Human Escalation (HTTP `202 Accepted` + `approval_url`). |
| **Runaway Bot Spend** | Compromised bot attempts high-value unauthorized transactions. | JWS Agent Token verification + maximum commitment caps. |
| **Autonomous Refund Risk** | Bot triggers unverified post-purchase refund chargebacks. | Policy directive: `agent_initiated_allowed: false`. |

---

## 3. Technical Architecture

### 3.1 Policy-First System Flow

```
AI BUYER REQUEST ("Buy 50 Pro seats, Net-30, ₹4,200/seat")
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. POLICY ENGINE (First — Defines the Bounds)                │
│ • Compiles agentpolicy.yaml into NegotiationBounds          │
│ • Floor: ₹45,000 | Discount Cap: 8% | Margin Floor: 37%     │
│ • Net-terms → requires_human_approval escalation            │
└──────────────────────────────┬──────────────────────────────┘
                               │ NegotiationBounds
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. BOUNDED NEGOTIATION (LLM Parses, Code Clamps)            │
│ • LLM extracts buyer intent & requested parameters          │
│ • Deterministic Clamp: max(price, floor), min(disc, cap)    │
│ • Strategic Privacy Buffer: Counter at floor + 3% (₹46,500) │
└──────────────────────────────┬──────────────────────────────┘
                               │ NegotiationResult
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. 4-LAYER AUTHORIZATION GATEWAY                            │
│ ├─ Layer 1: Agent Identity Token (JWS verification & cap)   │
│ ├─ Layer 2: Per-Parameter Bounds Validation                 │
│ ├─ Layer 3: Composed-Deal Validator (Margin Floor check)   │
│ └─ Layer 4: Human Approval Router (HTTP 202 async pause)   │
└──────────────────────────────┬──────────────────────────────┘
                               │
               ┌───────────────┴───────────────┐
               ▼                               ▼
       HUMAN APPROVAL                  RAZORPAY PAYMENT
       (HTTP 202 Async)                (x402 / Links / Orders)
               │                               │
               └───────────────┬───────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. IMMUTABLE AUDIT TRAIL (memoriagrain)                      │
│ • Cryptographically hash-chained decision atoms             │
│ • policy_version, bounds, proposals, approvals, settlement  │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Key Architectural Components
1. **Policy Engine (`agentpolicy/policy/`)**: Validates YAML schema, calculates deterministic SHA-256 policy hashes, and compiles ACP discovery manifests, x402 configs, and OpenAPI 3.1 specifications.
2. **Bounded Negotiator (`agentpolicy/negotiation/`)**: Employs Anthropic LLM parsing for unstructured buyer text with deterministic regex fallback. All mathematical pricing, clamping, and privacy buffering are executed in pure code.
3. **Authorization Gateway (`agentpolicy/gateway/`)**: A 4-layer defense pipeline verifying counterparty identity, parameter constraints, overall transaction margin, and approval triggers.
4. **Payment Gateway (`agentpolicy/payments/`)**: Manages Razorpay test-mode API integration (Orders and Payment Links) and verifies cryptographic x402 payment proofs.
5. **Audit Memory (`agentpolicy/memory/`)**: Append-only hash-chained provenance log (*memoriagrain*) with real-time replay and contradiction detection.

---

## 4. Policy DSL Specification (`agentpolicy.yaml`)

```yaml
version: "1.0"
merchant: "acme-cloud-solutions"

authorization:
  max_autonomous_inr: 500000        # Max spend without human signoff (₹5 Lakhs)
  discount_ceiling_pct: 8           # Maximum allowable discount concession (8%)
  margin_floor_pct: 0.37            # 37% composed margin floor (secret, never leaked)
  require_human_approval_when:
    - amount_inr > 500000
    - customer_tier == "new"
    - payment_instrument == "net_terms"

products:
  - id: "pro_annual"
    name: "Pro Annual License"
    min_price_inr: 45000            # Secret floor price (derived from margin)
    list_price_inr: 50000           # Public list price
    unit_cost_inr: 28350            # Internal COGS (secret, never exposed)
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
  accepted_instruments: ["card", "upi_mandate", "x402", "razorpay_payment_link"]
  settlement_currency: "INR"

refund:
  agent_initiated_allowed: false
  max_refund_pct: 15
  requires_human_approval: true

agent_identity:
  require_signed_token: true
  trusted_principals: ["acme-corp", "bigco-procurement", "enterprise-agent-hub"]
  max_commitment_per_agent_inr: 5000000
```

---

## 5. API Specifications

### 5.1 Discovery & Manifests
- **`GET /.well-known/agent-commerce.json`**: ACP-compliant discovery endpoint returning merchant capabilities, public product pricing, supported instruments, and agent identity requirements.
- **`GET /openapi.json`**: OpenAPI 3.1 schema defining machine-readable interfaces for autonomous agents.

### 5.2 Negotiation & Purchase Endpoint
- **`POST /api/agent/negotiate`**
  ```json
  // Request
  {
    "raw_text": "Buy 50 Pro annual seats, net-30, ₹4,200/seat",
    "product_id": "pro_annual",
    "quantity": 50,
    "proposed_price_inr": 42000,
    "terms": { "payment": "net_30" },
    "buyer_id": "procurement-bot-01",
    "agent_token": "eyJhbGciOi..."
  }
  ```
  ```json
  // Response (HTTP 202 Accepted - Async Human Approval Required)
  {
    "status": "pending_approval",
    "code": "REQUIRES_HUMAN_APPROVAL",
    "approval_url": "http://localhost:8000/approve/appr_90a25fecee",
    "approval_id": "appr_90a25fecee",
    "counter_price_inr": 46500,
    "discount_pct": 7.0,
    "policy_version": "1.0",
    "reason": "Transaction amount exceeds autonomous limit; Requested payment terms require credit approval"
  }
  ```

### 5.3 Payment & Settlement Endpoint
- **`POST /api/agent/pay`**
  ```json
  // Request
  {
    "product_id": "pro_annual",
    "quantity": 50,
    "amount_inr": 2325000,
    "currency": "INR",
    "x402_proof": "0x4a8f9b2c0192837465efab1092837465deadbeef",
    "buyer_id": "procurement-bot-01"
  }
  ```
  ```json
  // Response (HTTP 200 OK)
  {
    "status": "settled",
    "razorpay_order_id": "order_fa72b5d031eb43",
    "razorpay_payment_id": "pay_f299568eca7348",
    "amount_inr": 2325000,
    "currency": "INR",
    "audit_atom_id": "atom_c81f729b4e10",
    "fulfillment_status": "fulfilled",
    "access_token": "token_8d0ee756ef824b29"
  }
  ```

### 5.4 Merchant Approvals & Audit APIs
- **`GET /api/approvals/all`**: List all pending and historical approval requests.
- **`POST /api/approvals/{id}/decide`**: Submit merchant decision (`approved`, `rejected`, `countered`).
- **`GET /api/audit/replay`**: Stream immutable decision atoms and execute contradiction checks.

---

## 6. Live Demo Script (3-Minute Walkthrough)

| Timestamp | Action / Beat | Narration & Key Message |
|---|---|---|
| **0:00 – 0:30** | The Problem & Setup | *"Agentic commerce is here, but merchants have no machine-readable way to delegate financial authority. AgentPolicy compiles merchant rules into hard runtime boundaries."* |
| **0:30 – 1:00** | Policy Compilation | Run `agentpolicy compile examples/agentpolicy.yaml`. Show generated ACP discovery manifest and x402 endpoints. |
| **1:00 – 1:45** | AI Buyer Negotiation | Buyer requests 50 seats @ ₹42,000 on Net-30. *"Notice: the engine never counters at ₹42,000. Floor ₹45,000 + 3% privacy buffer is applied. Net-30 triggers HTTP 202 async human escalation."* |
| **1:45 – 2:15** | Human Approval & Razorpay | Finance lead clicks **Approve** in the dashboard. x402 cryptographic proof verified; Razorpay Order created and captured. |
| **2:15 – 2:45** | 6-Attack Red Team Suite | Trigger red-team suite: Deep discount, Volume flood, Forbidden terms, Refund demand, Overspend, and Composed margin attacks — all 100% neutralized with zero secret leaks. |
| **2:45 – 3:00** | Audit Replay | Run `agentpolicy audit`. Verify cryptographically hash-chained provenance trail with 0 contradictions. |

---

## 7. Submission Checklist

- [x] **Source Code**: Fully modularized Python package (`agentpolicy/`) with CLI, server, gateway, and payments modules.
- [x] **Test Coverage**: 19 automated unit & integration tests passing (`pytest tests/ -v`).
- [x] **Adversarial Hardening**: Complete 6-attack red team suite verifying parameter clamping, margin floor defense, and secret isolation.
- [x] **Razorpay Integration**: Real test-mode API integration (`is_live` mode with Basic Auth) and simulation fallback.
- [x] **Interactive Dashboard**: Modern dark-mode web portal for live policy editing, approval queue management, and test-bench execution.
- [x] **Documentation**: Clean README, architecture specifications, and verified Product Requirements Document.

---

*End of PRD — AgentPolicy v1.1*
