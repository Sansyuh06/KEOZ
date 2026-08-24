---
title: Keoz
emoji: 🛡️
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: 4.44.0
app_file: app.py
pinned: false
short_description: Merchant Command Center for Agentic Commerce
---

# KEOZ

A merchant-side financial policy and authorization gateway for agentic commerce. Built for the Razorpay Hackathon (Track 01: AI Growth & Agentic Commerce).

---

## What is this?

When autonomous AI buyer agents negotiate and purchase products on behalf of companies, who protects the merchant?

If you hook an LLM directly to payment webhooks, buyer bots can easily trick it into giving 80% discounts or agreeing to net-90 payment terms that destroy your profit margin.

KEOZ sits right in front of Razorpay. It gives merchants a simple YAML policy to set:
- Secret margin floors (e.g. minimum 37% margin, never revealed to the buyer bot)
- Maximum discount caps
- Autonomous spending limits (e.g. auto-approve up to Rs 5,00,000; anything higher needs a human)
- Credit term restrictions (e.g. net-30 terms require finance team approval)
- An immutable SQLite audit log of every decision

---

## An Example

Say an AI buyer bot sends this request:
> "I want 50 Pro Annual licenses at Rs 42,000 each with Net-30 payment terms."

Here is how KEOZ handles it:
1. **Parses the offer**: Extracts the product (`pro_annual`), quantity (`50`), price (`Rs 42,000`), and terms (`net_30`).
2. **Clamps to policy bounds**: The buyer asked for a 16% discount, but the merchant's policy caps discounts at 8% with a secret floor of Rs 45,000. KEOZ automatically counters at **Rs 46,500** (adding a 3% privacy buffer so the bot can't guess the exact floor).
3. **Catches margin drain**: Combines the discount with the financing cost of Net-30 terms. If total deal margin falls below 37%, it blocks or counters.
4. **Escalates to human**: Because the buyer requested credit terms (Net-30), KEOZ pauses the deal (HTTP 202) and sends it to the merchant dashboard.
5. **Settles via Razorpay**: Once the finance lead clicks "Approve" in the dashboard, KEOZ creates the Razorpay order and finalizes payment.

---

## How It Works

1. **Buyer proposes**: An AI bot sends a purchase offer via REST API (`/api/agent/negotiate`).
2. **LLM parses, code enforces**: Gemini/Claude (or built-in regex fallback) parses messy human/bot language into clean JSON. Python code (not the LLM) does the mathematical clamping to ensure bounds are never violated.
3. **4-layer check**:
   - Layer 1: Verify buyer bot JWT identity and spending limit.
   - Layer 2: Check price floors and batch seat limits.
   - Layer 3: Calculate composed deal margin (unit cost + payment financing cost).
   - Layer 4: Route high-value or credit orders to human approval inbox.
4. **Payment & Audit**: Settles on Razorpay and records a SHA-256 hash-chained atom into local SQLite (`.keoz/keoz.db`).

---

## Quickstart

### 1. Install

```bash
git clone https://github.com/Sansyuh06/KEOZ.git
cd KEOZ
pip install -e .
```

### 2. Run Tests

```bash
python -m pytest
```

### 3. Run the 3-Minute Terminal Demo

```bash
python run_demo.py
```

This runs a full demo showing multi-merchant policies, LLM parsing, adversarial attack neutralization, human approval, and Razorpay settlement.

### 4. Start the Web Dashboard

```bash
python -m uvicorn keoz.server.app:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` in your browser.

---

## Merchant Policy Example (`keoz.yaml`)

```yaml
version: "1.0"
merchant: "acme-saas"

authorization:
  max_autonomous_inr: 500000        # Orders over Rs 5L need human sign-off
  discount_ceiling_pct: 8.0         # Max 8% discount
  margin_floor_pct: 0.37            # Hard 37% margin floor (secret)
  require_human_approval_when:
    - "amount_inr > 500000"
    - "payment_instrument == 'net_terms'"

products:
  - id: "pro_annual"
    name: "Pro Annual License"
    min_price_inr: 45000            # Floor price
    list_price_inr: 50000           # List price
    unit_cost_inr: 28350            # COGS
    max_seats_per_transaction: 50

payment:
  accepted_instruments:
    - "card"
    - "upi_mandate"
    - "x402"
    - "razorpay_payment_link"
```

---

## Attacks Blocked Out of the Box

- **Deep Discount Attack**: Buyer demands an 80% discount (Rs 9,000 instead of Rs 45,000) -> Clamped to Rs 46,500.
- **Excessive Volume Attack**: Buyer demands 10,000 seats exceeding max limit -> Clamped to 50 & escalated to human.
- **Forbidden Terms Attack**: Buyer demands "zero liability & unlimited refunds" -> Blocked (HTTP 403).
- **Self-Refund Attack**: Bot tries to initiate its own refund -> Blocked (HTTP 403).
- **Overspend Attack**: Buyer tries a Rs 10L order on a Rs 5L autonomous limit -> Escalated to human (HTTP 202).
- **Composed Margin Drain**: Buyer combines an 8% discount with Net-90 terms, which drops profit below financing cost -> Blocked (HTTP 403).

---

## API Endpoints

- `GET /.well-known/agent-commerce.json` - Machine discovery manifest (ACP standard)
- `POST /api/agent/negotiate` - Negotiate and authorize purchase
- `POST /api/agent/pay` - Settle deal via Razorpay Order / x402
- `GET /api/approvals/all` - List human approval requests
- `POST /api/approvals/{id}/decide` - Approve or reject a deal
- `GET /api/merchants` - List registered merchants
- `PUT /api/merchants/{id}/policy` - Hot-reload policy YAML
- `GET /api/audit/replay` - Replay hash-chained SQLite audit trail
- `POST /api/test/adversarial` - Run red-team attack suite
- `WS /ws/metrics` - Live WebSocket stream for the dashboard

---

## Project Layout

- `keoz/gateway/` - 4-layer authorization, identity verification, and human approval queue
- `keoz/negotiation/` - LLM parser and deterministic bounds clamp
- `keoz/payments/` - Razorpay integration and x402 protocol handler
- `keoz/memory/` - SQLite audit logger with SHA-256 hash chaining
- `keoz/policy/` - YAML policy loader and bounds compiler
- `keoz/server/` - FastAPI backend, WebSockets, and dashboard UI
- `keoz/storage.py` - SQLite persistence layer (`.keoz/keoz.db`)
- `keoz/registry.py` - Multi-merchant policy registry
- `run_demo.py` - 3-minute terminal demo
- `tests/` - 25 automated pytest tests
