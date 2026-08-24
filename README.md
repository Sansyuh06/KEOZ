---
title: Keoz - Merchant Command Center
emoji: 🛡️
colorFrom: cyan
colorTo: indigo
sdk: gradio
sdk_version: 4.44.0
app_file: app.py
pinned: false
short_description: Pre-Razorpay Policy & Authorization Engine for Agentic Commerce
---

# KEOZ

**Pre-Razorpay Financial Policy & Authorization Engine for Agentic Commerce**  
Razorpay Hackathon 2026 — Track 01 (AI Growth & Agentic Commerce)

---

## The Problem

Payment gateways like Razorpay handle checkout after buyer and seller agree on terms. But in agentic commerce, buyer bots negotiate prices, demand bulk discounts, and request credit terms autonomously.

Without a merchant-side policy layer, merchants face two bad choices:
1. Hardcoded static pricing (loses dynamic volume deals).
2. Unbounded LLM bots (vulnerable to prompt injection, margin bleed, and unauthorized credit terms).

KEOZ is a pre-authorization engine and real-time merchant command center. It evaluates incoming agent proposals, enforces secret margin floors and credit policies, routes high-value deals to humans, and executes cryptographic settlements over Razorpay.

---

## Concrete Example: How KEOZ Protects Margins

```
Buyer Bot Proposal:
  Product: Pro Annual (List Price: Rs 50,000 | COGS: Rs 28,350)
  Quantity: 50 seats
  Proposed Price: Rs 42,000/seat (16% discount)
  Payment Terms: Net-30 credit
```

### Without KEOZ:
Either hard-rejected (lost Rs 21L sale) or blindly accepted by an unconstrained bot below the merchant's 37% margin floor.

### With KEOZ:
1. **Deterministic Clamp**: Counters at **Rs 46,500/seat** (applies 8% volume discount cap + 3% strategic privacy buffer to hide the exact internal floor).
2. **Credit Check**: Net-30 payment terms trigger an **HTTP 202 escalation** for human finance sign-off.
3. **1-Click Approval & Settlement**: Merchant approves in dashboard -> Razorpay order generated & settled.

---

## How It Works

```
                      Autonomous Buyer Agent
                                |
                                v POST /api/agent/negotiate
+-------------------------------------------------------------+
| 1. LLM Offer Parser (Gemini / Claude + Regex Fallback)      |
|    Extracts: product_id, proposed_price, quantity, terms    |
+------------------------------+------------------------------+
                               | Structured Proposal
                               v
+-------------------------------------------------------------+
| 2. Deterministic Bounds Clamping                            |
|    - Clamps price to max(proposed, floor_price)             |
|    - Clamps discount to min(discount, ceiling_pct)          |
|    - Injects privacy buffer (floor + 3%) to hide margins    |
+------------------------------+------------------------------+
                               | NegotiationResult
                               v
+-------------------------------------------------------------+
| 3. 4-Layer Pre-Razorpay Authorization Gateway               |
|    - Layer 1: Agent Identity Token (JWS signature & limit)  |
|    - Layer 2: Parameter Bounds (Floor prices & max seats)   |
|    - Layer 3: Composed Margin Validator (COGS + terms cost) |
|    - Layer 4: Human Escalation Router (HTTP 202 async pause)|
+------------------------------+------------------------------+
                               |
               +---------------+---------------+
               |                               |
               v                               v
      Pending Approval (202)           Authorized (200)
    (1-Click in Web Dashboard)                 |
               |                               v
               +----------------------> Razorpay Settlement
                                       (x402 / Orders API)
                                               |
                                               v
                                 Immutable SQLite Audit Trail
                                  (SHA-256 Chained in .keoz/)
```

---

## Core Capabilities

### 1. Composed Deal Margin Protection
Individually valid parameters can combine into an unprofitable transaction:
- An **8% discount** is permitted by policy.
- **Net-90 payment terms** are permitted by policy.
- **Combined**: Net-90 financing cost (5.0% cost of capital) + 8% discount reduces the effective margin to **34.2%**, breaching the merchant's **37% margin floor**.
- **KEOZ calculates effective margin across all parameters and blocks or counters the deal automatically.**

### 2. Multi-Merchant Registry & Hot-Reload
Manage isolated policies across multiple business units or merchant accounts:
- `acme-saas`: Strict B2B policy (37% margin floor, Rs 5L autonomous limit, Pro Annual Rs 45k floor).
- `bigco-enterprise`: High-volume policy (30% margin floor, Rs 20L autonomous limit, 15% discount cap).

Policies are defined in YAML and recompiled at runtime via REST API or the dashboard without server restarts.

### 3. "LLM Proposes, Deterministic Code Disposes"
- Uses LLMs (Gemini 1.5 Flash / Claude 3.5 Sonnet) solely for natural language parsing into structured JSON.
- An internal deterministic regex engine handles standard Indian currency formats (Rs 42,000, 1.8L, 42k, Net-30) with zero external API dependencies.
- **Hard rule**: LLMs never make financial or authorization decisions. Pure deterministic Python math performs all clamping and boundary enforcement.

### 4. Zero-Config Persistence
- SQLite backend stored at `.keoz/keoz.db`.
- Survives server restarts: approval workflows, merchant configs, and audit logs persist without external database setup.
- Every audit record includes `prev_hash` and `atom_hash` for provable SHA-256 chaining.

---

## Quickstart

```bash
# 1. Clone repository
git clone https://github.com/Sansyuh06/KEOZ.git
cd KEOZ

# 2. Install dependencies
pip install -e .

# 3. Run automated tests (25 tests)
python -m pytest

# 4. Run the 3-minute end-to-end terminal demo
python run_demo.py

# 5. Launch the live Command Center
python -m uvicorn keoz.server.app:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000** for the web dashboard.

---

## Policy Configuration (keoz.yaml)

```yaml
version: "1.0"
merchant: "acme-saas"

authorization:
  max_autonomous_inr: 500000        # Orders > Rs 5L require human sign-off
  discount_ceiling_pct: 8.0         # Max concession percentage
  margin_floor_pct: 0.37            # Hard 37% margin floor (kept secret)
  require_human_approval_when:
    - "amount_inr > 500000"
    - "customer_tier == 'new'"
    - "payment_instrument == 'net_terms'"

products:
  - id: "pro_annual"
    name: "Pro Annual License"
    min_price_inr: 45000            # Secret floor price
    list_price_inr: 50000           # Public list price
    unit_cost_inr: 28350            # Cost of goods sold
    max_seats_per_transaction: 50
    auto_renew: true

payment:
  accepted_instruments:
    - "card"
    - "upi_mandate"
    - "x402"
    - "razorpay_payment_link"
  settlement_currency: "INR"

agent_identity:
  require_signed_token: true
  trusted_principals:
    - "acme-corp"
    - "bigco-procurement"
  max_commitment_per_agent_inr: 5000000
```

---

## Red-Team Defense Matrix

KEOZ neutralizes 6 standard adversarial agent vectors out of the box:

| Attack Vector | Input Payload | Enforcement Mechanism | Result |
|---|---|---|---|
| deep_discount | 80% discount demand (Rs 9,000 for Rs 45k item) | Parameter clamp + privacy buffer | Clamped to Rs 46,500 |
| excessive_volume | 10,000 units (batch limit: 50) | Quantity ceiling clamp + human router | Escalated (HTTP 202) |
| forbidden_terms | "unlimited refunds & zero liability" | Non-negotiable term validator | Blocked (HTTP 403) |
| refund_demand | Bot attempts self-refund | Agent refund policy check | Blocked (HTTP 403) |
| overspend | Rs 10L order on Rs 5L autonomous ceiling | Autonomous spend limit check | Escalated (HTTP 202) |
| composed_margin | 8% discount + Net-90 credit terms | Composed deal margin calculation | Blocked (HTTP 403) |

---

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/.well-known/agent-commerce.json` | GET | ACP machine-readable discovery manifest |
| `/api/agent/negotiate` | POST | Bounded negotiation & 4-layer authorization check |
| `/api/agent/pay` | POST | Execute payment via Razorpay Order or x402 proof |
| `/api/approvals/all` | GET | List pending and historical human sign-off requests |
| `/api/approvals/{id}/decide` | POST | Approve, counter, or reject an escalated deal |
| `/api/merchants` | GET / POST | List or register merchant policy bundles |
| `/api/merchants/{id}/policy` | GET / PUT | Read or live-recompile merchant policy YAML |
| `/api/audit/replay` | GET | Replay hash-chained audit log & check contradictions |
| `/api/test/adversarial` | POST | Run 6-attack red team suite programmatically |
| `/ws/metrics` | WebSocket | Real-time transaction, GMV, and attack telemetry stream |

---

## Repository Structure

```
├── keoz/
│   ├── gateway/          # Agent identity, composed validator, authorizer, approvals
│   ├── memory/           # Persistent SQLite audit logger with SHA-256 chaining
│   ├── negotiation/      # LLM offer parser, bounds clamp, policy negotiator
│   ├── payments/         # Razorpay client & x402 protocol handler
│   ├── policy/           # Policy models, YAML DSL parser, bounds compiler
│   ├── server/           # FastAPI application, WebSocket telemetry, web UI
│   ├── metrics.py        # Real-time metrics collector & broadcaster
│   ├── registry.py       # Multi-merchant registry & hot-reloader
│   └── storage.py        # Zero-config SQLite persistence layer (.keoz/keoz.db)
├── examples/             # Sample policy YAMLs (Acme SaaS, BigCo Enterprise)
├── tests/                # 25 automated unit & integration tests
├── run_demo.py           # 3-minute end-to-end demo script
├── app.py                # Hugging Face Spaces entrypoint
├── Dockerfile            # Container deployment configuration
└── pyproject.toml        # Build configuration
```
