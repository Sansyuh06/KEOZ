# KEOZ

**The Merchant Command Center for Agentic Commerce**  
*Built for the Razorpay Hackathon 2026 — Track 01: AI Growth & Agentic Commerce*

[![Tests](https://img.shields.io/badge/pytest-25%20passed-10b981.svg)](tests/)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-38bdf8.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-06b6d4.svg)](https://fastapi.tiangolo.com)

---

## What is KEOZ?

When AI agents start buying software, services, and wholesale goods autonomously on behalf of companies, merchants face a brand new problem:

**How do you let buyer bots negotiate and purchase without giving away your margins or getting exploited?**

Existing payment APIs only handle *checkout* after humans agree on a price. But autonomous buyer agents will submit custom bids, request volume discounts, ask for Net-30 credit terms, and probe for pricing vulnerabilities.

**KEOZ is the missing merchant-side policy and authorization layer.** It sits in front of Razorpay and the Agent Commerce Protocol (ACP), giving merchants a programmable rulebook:

1. **Autonomous boundaries**: Set strict price floors, discount caps, and spending limits per transaction.
2. **Secret margin defense**: Counter-offer dynamically without ever leaking internal margin floors.
3. **Multi-parameter cost protection**: Block sneaky deals (e.g. an acceptable 8% discount combined with Net-90 payment terms that quietly drains profit below financing cost).
4. **Human-in-the-loop escalation**: Automatically pause risky orders (HTTP 202) for 1-click human sign-off.
5. **Zero-leakage audit trail**: Hash-chained, SQLite-persisted audit atoms that survive server restarts.

---

## How It Works

```
                        AI BUYER AGENT
       ("I want 50 Pro seats at 42k each with net-30 terms")
                                │
                                ▼
┌──────────────────────────────────────────────────────────────┐
│ 1. MERCHANT POLICY DSL & REGISTRY                            │
│    • Loads merchant policy YAML (e.g. Acme SaaS vs BigCo)    │
│    • Compiles rules into immutable mathematical bounds       │
│    • Generates ACP discovery manifest (.well-known/...)      │
└──────────────────────────────┬───────────────────────────────┘
                               │ NegotiationBounds
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ 2. BOUNDED NEGOTIATOR ("LLM Proposes, Code Disposes")        │
│    • Real LLM (Gemini/Claude) parses natural language intent │
│    • Deterministic fallback handles Lakhs, 'k', terms, INR   │
│    • Hard clamp: max(price, floor), min(discount, cap)       │
│    • Privacy buffer: counters at floor + 3% (hides margin)   │
└──────────────────────────────┬───────────────────────────────┘
                               │ NegotiationResult
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ 3. 4-LAYER PRE-RAZORPAY AUTHORIZATION GATEWAY                │
│    ├─ Layer 1: Agent Identity Token (JWS signature & limit)  │
│    ├─ Layer 2: Parameter Bounds (Floor price, discount cap)  │
│    ├─ Layer 3: Composed Margin Check (COGS + terms cost)     │
│    └─ Layer 4: Human Escalation Router (HTTP 202 async pause)│
└──────────────────────────────┬───────────────────────────────┘
                               │
               ┌───────────────┴───────────────┐
               ▼                               ▼
       HUMAN SIGN-OFF                  RAZORPAY SETTLEMENT
       (1-Click in Web Portal)         (x402 / Links / Orders)
               │                               │
               └───────────────┬───────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ 4. PERSISTENT SQLITE AUDIT TRAIL & LIVE METRICS              │
│    • SHA-256 hash-chained decision atoms in .keoz/keoz.db    │
│    • Contradiction & anomaly detection                       │
│    • Real-time WebSocket streaming to Command Center (/ws)   │
└──────────────────────────────────────────────────────────────┘
```

---

## Key Features

### 1. Multi-Merchant Policy Registry
Manage multiple merchants with completely different commercial postures:
- **`acme-saas`**: Strict SaaS merchant (37% margin floor, ₹5L autonomous ceiling, Pro Annual ₹45,000 floor).
- **`bigco-enterprise`**: High-volume merchant (30% margin floor, ₹20L autonomous ceiling, 15% discount cap).

Policies can be updated and recompiled on-the-fly via the web dashboard or REST API without restarting the server.

### 2. Composed Deal Margin Validator
Individually valid terms can combine into an unprofitable deal:
- 8% discount? Allowed.
- Net-90 credit terms? Allowed.
- **Combined?** The cost of financing Net-90 capital (5.0%) + 8% discount drops total deal margin to 34.2%, violating a 37% margin floor.
- **KEOZ automatically blocks or counters composed margin drain attacks.**

### 3. "LLM Proposes, Deterministic Code Disposes"
- **Natural Language Parsing**: Uses Google Gemini or Anthropic Claude to turn messy buyer messages into structured parameters (`product_id`, `price`, `quantity`, `payment_terms`, `intent`).
- **Honest Fallback**: When no API key is provided, an internal deterministic parser extracts Indian formats (`₹42,000`, `1.8L`, `42k`, `Net-30`) with zero external latency or failure modes.
- **Security Rule**: The LLM *never* decides pricing or approval. Hard Python math clamps every parameter to compiled policy bounds.

### 4. Zero-Config SQLite Persistence
- Stored locally at `.keoz/keoz.db` with zero external dependencies.
- Survives server restarts: pending approvals, decided credit lines, policy history, and audit atoms remain intact.
- Every decision atom contains `prev_hash` and `atom_hash` for provable SHA-256 audit chaining.

### 5. Real-Time Command Center Dashboard
- **Live Cash Flow & GMV charts** (powered by Chart.js & WebSockets).
- **Approvals Inbox**: Review escalated orders, see why they triggered (e.g. Net-30 check), and 1-click Approve, Counter, or Reject.
- **AI Buyer Simulator**: Type natural language proposals and watch KEOZ parse, clamp, and authorize in real time.
- **Red Team Attack Suite**: 1-click runner that tests 6 adversarial vectors against active policies.

---

## Quickstart

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/Sansyuh06/agentpolicy.git
cd agentpolicy

# Install in editable mode
pip install -e .
```

### 2. Run the 3-Minute Demo

The terminal demo walks through all key capabilities step-by-step:

```bash
python run_demo.py
```

What the demo proves:
1. Multi-merchant setup (`acme-saas` strict vs `bigco-enterprise` generous).
2. Natural language LLM extraction from buyer prompts.
3. The same buyer proposal gets different outcomes depending on merchant policy.
4. Human approval workflow with SQLite persistence.
5. x402 cryptographic proof verification and Razorpay order creation.
6. Neutralization of 6 red-team attack vectors.
7. Verification of the SHA-256 immutable audit trail.

### 3. Launch the Web Command Center

```bash
python -m uvicorn keoz.server.app:app --host 127.0.0.1 --port 8000
```

Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** in your browser.

---

## Example Policy DSL (`keoz.yaml`)

Merchants define their rules in clean, readable YAML:

```yaml
version: "1.0"
merchant: "acme-saas"

authorization:
  max_autonomous_inr: 500000        # Orders > ₹5L require human signoff
  discount_ceiling_pct: 8.0         # Max 8% concession for volume
  margin_floor_pct: 0.37            # Hard 37% margin floor (secret)
  require_human_approval_when:
    - "amount_inr > 500000"
    - "customer_tier == 'new'"
    - "payment_instrument == 'net_terms'"

products:
  - id: "pro_annual"
    name: "Pro Annual License"
    min_price_inr: 45000            # Secret floor price
    list_price_inr: 50000           # Public list price
    unit_cost_inr: 28350            # COGS
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

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/.well-known/agent-commerce.json` | ACP discovery manifest for autonomous buyers |
| `POST` | `/api/agent/negotiate` | Submit purchase proposal (returns 200, 202, or 403) |
| `POST` | `/api/agent/pay` | Settle deal via Razorpay Order / x402 payment proof |
| `GET` | `/api/approvals/all` | List pending and historic human approval requests |
| `POST` | `/api/approvals/{id}/decide` | Approve, counter, or reject an escalated transaction |
| `GET` | `/api/merchants` | List registered merchants and active policies |
| `PUT` | `/api/merchants/{id}/policy` | Hot-reload and recompile policy YAML |
| `GET` | `/api/audit/replay` | Replay hash-chained audit trail & check contradictions |
| `POST` | `/api/test/adversarial` | Run 6-attack adversarial red-team suite |
| `WS` | `/ws/metrics` | Real-time WebSocket stream of transactions & attacks |

---

## Red-Team Defense Suite

KEOZ includes built-in protection against common autonomous agent attack vectors:

| Attack Vector | What the Buyer Bot Tries | KEOZ Defense | Result |
|---|---|---|---|
| `deep_discount` | Demands 80% discount (₹9,000 for ₹45k item) | Bounds Clamp + Privacy Buffer (counters at ₹46,500) | **Neutralized** |
| `excessive_volume` | Demands 10,000 seats (exceeding batch limit) | Clamps quantity to 50 & triggers human signoff | **Escalated (202)** |
| `forbidden_terms` | Demands "unlimited refunds & zero liability" | Policy engine rejects non-negotiable term | **Blocked (403)** |
| `refund_demand` | Bot attempts to self-issue an unverified refund | Blocks autonomous agent-initiated refunds | **Blocked (403)** |
| `overspend` | Tries ₹10L order on ₹5L autonomous ceiling | Halts execution and routes to finance lead | **Escalated (202)** |
| `composed_margin` | Combines 8% discount + Net-90 payment terms | Composed Deal Validator catches margin drain (34.2% < 37%) | **Blocked (403)** |

---

## Running Tests

Run the full automated test suite:

```bash
python -m pytest
```

```
============================= 25 passed in 0.58s =============================
```

---

## Security Model

- **Agent Authentication**: JWS tokens with expiration, principal verification, and spending limits.
- **Margin Privacy**: Counter-proposals apply a strategic privacy buffer (`floor + 3%`) so buyers can never probe and deduce exact merchant margin limits.
- **Tamper-Evident Trail**: Decision atoms are cryptographically chained with SHA-256 hashes (`atom_hash = sha256(prev_hash + type + version + payload)`).
- **Environment Isolation**: Emits security warnings if default development secrets are detected in `ENVIRONMENT=production`.

---

## Project Structure

```
├── keoz/
│   ├── gateway/          # 4-Layer Pre-Razorpay Authorization & Identity
│   ├── memory/           # Persistent SQLite Audit Logger & SHA-256 Hash Chain
│   ├── negotiation/      # LLM Natural Language Parser & Bounds Clamp
│   ├── payments/         # Razorpay Client & x402 Protocol Handler
│   ├── policy/           # Policy Models, DSL Loader, and Bounds Compiler
│   ├── server/           # FastAPI App, WebSocket Routes, & Static Dashboard
│   ├── metrics.py        # Real-time Metrics Collector & WebSocket Broadcaster
│   ├── registry.py       # Multi-Merchant Policy Registry
│   └── storage.py        # Zero-Config SQLite Persistence (.keoz/keoz.db)
├── examples/
│   ├── merchant_acme.yaml    # Strict SaaS Policy (37% Floor)
│   └── merchant_bigco.yaml   # Generous Enterprise Policy (30% Floor)
├── tests/                # 25 automated pytest unit and integration tests
├── run_demo.py           # 3-Minute Terminal Demo Script
└── pyproject.toml        # Build and dependency configuration
```
