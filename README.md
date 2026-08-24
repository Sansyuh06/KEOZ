# AgentPolicy

> **Merchant-Side Financial Policy Layer for Agentic Commerce**  
> *Track 01: AI Growth & Agentic Commerce — Razorpay Hackathon*

[![Tests](https://img.shields.io/badge/pytest-passing-emerald.svg)](tests/)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://python.org)

---

## 🎯 The Core Insight

Merchants configure commercial rules for humans (dashboards, email approvals, spreadsheets) but have **no standardized machine-readable policy layer** to express what an autonomous agent is authorized to buy, negotiate, pay, or refund.

> It is not "catalog transformation." It is **delegated financial authority.**
>
> AgentPolicy turns merchant rules into executable runtime bounds that govern every autonomous transaction before a single rupee moves.

---

## 🏗️ Architecture

```
AI BUYER REQUEST ("Buy 50 Pro seats, Net-30, ₹4,200/seat")
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. POLICY ENGINE (First — Defines Negotiation Space)         │
│ • Compiles agentpolicy.yaml into deterministic bounds       │
│ • Floor price: ₹45,000 | Discount cap: 8% | Margin: 37%     │
│ • Net-terms → requires_human_approval escalation            │
└──────────────────────────────┬──────────────────────────────┘
                               │ NegotiationBounds
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. BOUNDED NEGOTIATION (LLM Proposes, Code Disposes)        │
│ • Parses buyer intent & proposes counter within bounds      │
│ • Deterministic Clamp: max(price, floor), min(disc, cap)    │
│ • Strategic Privacy Buffer: counter at floor + 3% (₹46,500) │
└──────────────────────────────┬──────────────────────────────┘
                               │ NegotiationResult
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. 4-LAYER AUTHORIZATION GATEWAY                            │
│ ├─ Layer 1: Agent Identity Token (JWS signature & cap)     │
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
│ • Cryptographically hash-chained provenance trail           │
│ • policy_version, bounds, proposals, approvals, orders      │
└─────────────────────────────────────────────────────────────┘
```

---

## 🛡️ The 4 Defense Layers

| Layer | Defense Mechanism | Attack Neutralized | HTTP Response |
|---|---|---|---|
| **1. Agent Identity** | JWS Signature + Whitelisted Principals + Spending Ceiling | Unauthorized bot / runaway spending | `401 Unauthorized` |
| **2. Parameter Bounds** | Floor Price Clamp + Discount Ceiling + Volume Limits | Sub-floor pricing & volume flood | `403 Forbidden` / Clamped Counter |
| **3. Composed Margin** | `(Revenue - COGS - TermsFinancingCost) / Revenue ≥ Floor` | Multi-parameter margin drain (8% + Net-90) | `403 Forbidden` (`MARGIN_FLOOR_VIOLATION`) |
| **4. Human Approval** | Net Terms / High Value (>₹5L) / New Customer Escalation | Unauthorized credit risk | `202 Accepted` + `approval_url` |

---

## 🚀 Quickstart

### 1. Install & Setup

```bash
# Clone the repository
git clone https://github.com/<your-handle>/agentpolicy.git
cd agentpolicy

# Install in development mode
pip install -e .
```

### 2. Run Interactive Demo

Execute the complete end-to-end walkthrough including bounded negotiation, human sign-off, x402 payment, 6-attack red team suite, and audit replay:

```bash
python run_demo.py
```

### 3. Launch Web Merchant Portal

```bash
python -m agentpolicy.cli serve --port 8000
```
Open **[http://localhost:8000](http://localhost:8000)** to view the interactive dashboard.

---

## 📋 Declarative Policy DSL (`agentpolicy.yaml`)

```yaml
version: "1.0"
merchant: "acme-cloud-solutions"

authorization:
  max_autonomous_inr: 500000        # Max spend without human signoff
  discount_ceiling_pct: 8           # Max allowable concession
  margin_floor_pct: 0.37            # 37% composed margin floor (secret)
  require_human_approval_when:
    - amount_inr > 500000
    - customer_tier == "new"
    - payment_instrument == "net_terms"

products:
  - id: "pro_annual"
    name: "Pro Annual License"
    min_price_inr: 45000            # Secret floor price
    list_price_inr: 50000           # Public list price
    unit_cost_inr: 28350            # Cost of goods (secret)
    max_seats_per_transaction: 50
    auto_renew: true

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

## 💻 CLI Commands

```bash
# Initialize new policy YAML
agentpolicy init

# Validate policy semantics & constraints
agentpolicy validate examples/agentpolicy.yaml

# Compile policy into ACP manifest, x402 config, OpenAPI & bounds JSON
agentpolicy compile examples/agentpolicy.yaml -d dist/

# Run the 6-Attack Red-Team Adversarial Suite
agentpolicy test-redteam

# Launch live server
agentpolicy serve --port 8000
```

---

## 🧪 Testing

Run the full automated test suite covering all security layers, margin calculations, and red-team attacks:

```bash
pytest -v
```

```
tests/test_adversarial.py::test_adversarial_suite PASSED                 [ 12%]
tests/test_agent_identity.py::test_agent_identity_token_verification PASSED [ 25%]
tests/test_audit.py::test_audit_logger_hash_chain PASSED                 [ 37%]
tests/test_compiler.py::test_policy_dsl_validation PASSED                [ 50%]
tests/test_compiler.py::test_policy_compiler PASSED                      [ 62%]
tests/test_composed_validator.py::test_composed_deal_margin_floor PASSED [ 75%]
tests/test_gateway.py::test_authorization_gateway_4_layers PASSED        [ 87%]
tests/test_negotiation.py::test_bounds_clamp_and_privacy_buffer PASSED   [100%]
============================== 8 passed in 0.17s ==============================
```

---

## 🏆 Competitive Advantage

| Feature | Consumer AI Buyers | Generic OPA / RBAC | **AgentPolicy** |
|---|---|---|---|
| Focus | "AI bot that buys coffee" | Technical API auth | **Merchant Commercial Authority** |
| Negotiation | Unconstrained LLM | None | **Bounded: LLM proposes, Code disposes** |
| Multi-parameter attack defense | None | None | **Composed Deal Margin Validator** |
| Approval Semantics | Immediate reject | Binary allow/deny | **HTTP 202 Async Human Bridge** |
| Audit Trail | None | Generic syslog | **memoriagrain Hash-Chained Atoms** |

---


