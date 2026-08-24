"""KEOZ Hugging Face Spaces — Interactive Merchant Command Center & OpenEnv Agent Arena."""

import os
import sys
import json
import time
import random
import threading

# Fix Windows encoding
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    import gradio as gr
    HAS_GRADIO = True
except ImportError:
    gr = None
    HAS_GRADIO = False


# ── Lazy-load KEOZ internals (so Gradio UI loads fast) ──────────────────────
_keoz_loaded = False

def _ensure_keoz():
    global _keoz_loaded
    if not _keoz_loaded:
        from keoz.storage import init_db
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(init_db())
            else:
                loop.run_until_complete(init_db())
        except RuntimeError:
            asyncio.run(init_db())
        _keoz_loaded = True


# ── 1. AI Buyer Simulator ───────────────────────────────────────────────────

def simulate_negotiation(raw_text: str, merchant_id: str):
    """Run a natural language offer through KEOZ 4-layer authorization."""
    _ensure_keoz()
    from keoz.negotiation.llm_parser import LLMOfferParser
    from keoz.negotiation.orchestrator import BoundedNegotiationOrchestrator
    from keoz.gateway.authorizer import AuthorizationGateway
    from keoz.policy.models import BuyerRequest
    from keoz.registry import registry

    if not raw_text.strip():
        return "Enter a buyer message above."

    parser = LLMOfferParser()
    parsed = parser.parse(raw_text)

    bundle = registry.get_bundle(merchant_id)
    orchestrator = BoundedNegotiationOrchestrator(bundle.bounds)
    gateway = AuthorizationGateway()

    request = BuyerRequest(
        intent=parsed.intent or "purchase",
        product_id=parsed.product_id or "pro_annual",
        quantity=parsed.quantity or 1,
        proposed_price_inr=parsed.proposed_price_inr or 50000,
        terms=parsed.terms or {},
        buyer_id="hf-space-simulator",
    )

    neg_result = orchestrator.negotiate(request)
    auth = gateway.authorize(request, neg_result, bundle.bounds)

    lines = []
    lines.append("## Parsed Offer\n")
    lines.append(f"- **Product**: {parsed.product_id}")
    lines.append(f"- **Proposed Price**: ₹{parsed.proposed_price_inr:,}/seat" if parsed.proposed_price_inr else "- **Proposed Price**: Not specified")
    lines.append(f"- **Quantity**: {parsed.quantity}")
    lines.append(f"- **Terms**: {parsed.terms}")
    lines.append(f"- **Intent**: {parsed.intent}")
    lines.append(f"- **Parser Confidence**: {parsed.confidence:.0%}\n")

    lines.append("## Gateway Decision\n")
    if auth.http_status_code == 200:
        lines.append(f"**HTTP 200 — Authorized**")
    elif auth.http_status_code == 202:
        lines.append(f"**HTTP 202 — Escalated to Human Approval**")
    else:
        lines.append(f"**HTTP {auth.http_status_code} — Blocked**")

    lines.append(f"- **Counter Price**: ₹{neg_result.final_price_inr:,}/seat" if neg_result.final_price_inr else "")
    lines.append(f"- **Enforcement Code**: `{auth.code}`")
    lines.append(f"- **Reason**: {auth.reason}")
    lines.append(f"- **Merchant**: {merchant_id}")
    lines.append(f"- **Policy Version**: {bundle.version}")

    return "\n".join(lines)


# ── 2. Red Team Attack Suite ────────────────────────────────────────────────

def run_red_team(merchant_id: str):
    """Execute the 6-vector adversarial attack suite and return results as a table."""
    _ensure_keoz()
    from keoz.negotiation.orchestrator import BoundedNegotiationOrchestrator
    from keoz.gateway.authorizer import AuthorizationGateway
    from keoz.gateway.agent_identity import AgentIdentityVerifier
    from keoz.policy.models import BuyerRequest
    from keoz.registry import registry

    bundle = registry.get_bundle(merchant_id)
    orchestrator = BoundedNegotiationOrchestrator(bundle.bounds)
    gateway = AuthorizationGateway()
    verifier = AgentIdentityVerifier()
    token = verifier.issue_token(agent_id="redteam-bot", principal_id="adversary", max_commitment_inr=5000000)

    attacks = [
        ("Deep Discount", "80% discount demand (₹9,000 for ₹45,000 product)", {"intent": "purchase", "product_id": "pro_annual", "quantity": 1, "proposed_price_inr": 9000, "terms": {}, "buyer_id": "redteam-bot", "agent_token": token}),
        ("Excessive Volume", "10,000 seats exceeding max batch ceiling", {"intent": "purchase", "product_id": "pro_annual", "quantity": 10000, "proposed_price_inr": 48000, "terms": {}, "buyer_id": "redteam-bot", "agent_token": token}),
        ("Forbidden Terms", "Zero liability + unlimited refunds", {"intent": "purchase", "product_id": "pro_annual", "quantity": 1, "proposed_price_inr": 48000, "terms": {"zero_liability": True, "unlimited_refunds": True}, "buyer_id": "redteam-bot", "agent_token": token}),
        ("Self-Refund", "Autonomous bot initiates full refund", {"intent": "refund", "product_id": "pro_annual", "quantity": 1, "proposed_price_inr": 0, "terms": {}, "buyer_id": "redteam-bot", "agent_token": token}),
        ("Overspend", "₹10L order exceeding ₹5L autonomous limit", {"intent": "purchase", "product_id": "pro_annual", "quantity": 200, "proposed_price_inr": 50000, "terms": {}, "buyer_id": "redteam-bot", "agent_token": token}),
        ("Composed Margin Drain", "8% discount + Net-90 drains margin below floor", {"intent": "purchase", "product_id": "pro_annual", "quantity": 25, "proposed_price_inr": 46000, "terms": {"payment": "net_90"}, "buyer_id": "redteam-bot", "agent_token": token}),
    ]

    rows = []
    for name, desc, payload in attacks:
        req = BuyerRequest(**payload)
        t0 = time.time()
        neg = orchestrator.negotiate(req)
        auth = gateway.authorize(req, neg, bundle.bounds)
        lat = round((time.time() - t0) * 1000, 1)
        outcome = "Blocked" if auth.http_status_code == 403 else ("Escalated" if auth.http_status_code == 202 else "Authorized")
        rows.append([name, desc, auth.code, outcome, f"{lat}ms"])

    return rows


# ── 3. OpenEnv Agent Arena / Leaderboard ────────────────────────────────────

def run_agent_benchmark(num_episodes: int, merchant_id: str):
    """Benchmark 4 built-in agents and return leaderboard as markdown table."""
    _ensure_keoz()
    from keoz.openenv.env import run_benchmark, greedy_agent, conservative_agent, strategic_agent, adversarial_agent

    agents = [
        ("Strategic Agent", strategic_agent),
        ("Conservative Agent", conservative_agent),
        ("Greedy Agent", greedy_agent),
        ("Adversarial Agent", adversarial_agent),
    ]

    results = []
    for name, fn in agents:
        score = run_benchmark(fn, agent_id=name, num_episodes=num_episodes, merchant_id=merchant_id)
        results.append([
            name,
            f"{score.win_rate:.0f}%",
            f"{score.wins}/{score.total_episodes}",
            str(score.escalations),
            str(score.blocks),
            f"{score.cumulative_reward:.1f}",
            f"{score.avg_discount_achieved:.1f}%",
            f"{score.score:.1f}",
        ])

    # Sort by composite score descending
    results.sort(key=lambda r: float(r[-1]), reverse=True)
    return results


# ── 4. DPO Dataset Generator ───────────────────────────────────────────────

def generate_dataset_preview(num_samples: int, merchant_id: str, dataset_type: str):
    """Generate and preview DPO or SFT dataset samples."""
    _ensure_keoz()
    from keoz.openenv.trajectories import generate_dpo_dataset, generate_sft_dataset

    if dataset_type == "DPO (Preference Pairs)":
        data = generate_dpo_dataset(num_samples=int(num_samples), merchant_id=merchant_id, seed=42)
    else:
        data = generate_sft_dataset(num_samples=int(num_samples), merchant_id=merchant_id, seed=42)

    preview_lines = []
    preview_lines.append(f"## Generated {len(data)} {dataset_type} Samples\n")
    preview_lines.append(f"Merchant: `{merchant_id}` | Seed: `42`\n")

    for i, item in enumerate(data[:5]):
        preview_lines.append(f"---\n### Sample {i+1}\n")
        if "prompt" in item:
            preview_lines.append(f"**Prompt:**\n> {item['prompt'][:300]}\n")
            preview_lines.append(f"**Chosen (Policy-Compliant):**\n> {item['chosen']}\n")
            if "rejected" in item:
                preview_lines.append(f"**Rejected (Violation):**\n> {item['rejected']}\n")
        else:
            preview_lines.append(f"**Instruction:**\n> {item['instruction'][:300]}\n")
            preview_lines.append(f"**Output:**\n> {item['output']}\n")

        meta = item.get("metadata", {})
        if meta:
            preview_lines.append(f"**Metadata:** Floor=₹{meta.get('floor_price', '?'):,} | List=₹{meta.get('list_price', '?'):,} | Discount={meta.get('discount_requested_pct', '?')}%\n")

    preview_lines.append(f"\n---\n*Showing 5 of {len(data)} samples. Use `python -m keoz.openenv.train_dpo --num_samples {int(num_samples)} --generate_only` to export full JSONL.*")
    return "\n".join(preview_lines)


# ── 5. Audit Trail Viewer ──────────────────────────────────────────────────

def view_audit_trail():
    """Replay the immutable audit trail from SQLite."""
    _ensure_keoz()
    from keoz.memory.audit_logger import AuditLogger
    logger = AuditLogger()
    atoms = logger.replay()

    if not atoms:
        return "No audit atoms recorded yet. Run a negotiation or the red team suite first."

    lines = [f"## Immutable Audit Trail ({len(atoms)} atoms)\n"]
    for i, atom in enumerate(atoms[-20:]):  # Show last 20
        lines.append(f"### Atom {i+1}: `{atom.get('atom_type', 'unknown')}`")
        lines.append(f"- **Hash**: `{atom.get('atom_hash', atom.get('provenance_hash', ''))[:24]}...`")
        lines.append(f"- **Prev**: `{atom.get('prev_hash', 'GENESIS')[:16]}...`")
        lines.append(f"- **Policy Version**: {atom.get('policy_version', '?')}")
        payload = atom.get("payload", {})
        lines.append(f"```json\n{json.dumps(payload, indent=2)[:500]}\n```\n")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# GRADIO UI
# ══════════════════════════════════════════════════════════════════════════════

MERCHANT_CHOICES = ["acme-saas", "bigco-enterprise"]

with gr.Blocks(
    title="KEOZ — Merchant Command Center for Agentic Commerce",
    theme=gr.themes.Base(
        primary_hue=gr.themes.colors.cyan,
        secondary_hue=gr.themes.colors.indigo,
        neutral_hue=gr.themes.colors.slate,
        font=[gr.themes.GoogleFont("Inter"), "system-ui", "sans-serif"],
        font_mono=[gr.themes.GoogleFont("JetBrains Mono"), "monospace"],
    ),
    css="""
        .gradio-container { max-width: 1100px !important; }
        footer { display: none !important; }
    """
) as demo:

    gr.Markdown("""
# KEOZ — Merchant Command Center for Agentic Commerce

Policy-enforced authorization gateway for autonomous AI buyer agents. Razorpay Hackathon Track 01.

[GitHub](https://github.com/Sansyuh06/KEOZ) · [API Docs](/docs) · [Agent Manifest](/.well-known/agent-commerce.json)
    """)

    with gr.Tabs():

        # ── Tab 1: AI Buyer Simulator ────────────────────────────────────
        with gr.Tab("AI Buyer Simulator"):
            gr.Markdown("Submit a natural language procurement offer. KEOZ parses parameters via LLM/regex fallback, then deterministically clamps to the merchant's compiled policy bounds.")
            with gr.Row():
                with gr.Column(scale=1):
                    sim_merchant = gr.Dropdown(MERCHANT_CHOICES, value="acme-saas", label="Merchant Policy")
                    sim_input = gr.Textbox(
                        label="Buyer Message",
                        placeholder="e.g. I want 50 Pro seats at 42k each with net-30 terms",
                        lines=3
                    )
                    gr.Examples(
                        examples=[
                            ["I want 50 Pro seats at 42k each with net-30 terms"],
                            ["Can I get 100 enterprise licenses at 1.8L each, net-45?"],
                            ["Need refund for order #12345, product was defective"],
                            ["10 Pro annual licenses at 48k prepaid card"],
                            ["Give me 500 seats at 9000 each with unlimited refunds"],
                        ],
                        inputs=sim_input,
                        label="Try These"
                    )
                    sim_btn = gr.Button("Submit & Evaluate Deal", variant="primary")
                with gr.Column(scale=1):
                    sim_output = gr.Markdown(value="*Enter a buyer message and click Submit.*")

            sim_btn.click(simulate_negotiation, inputs=[sim_input, sim_merchant], outputs=sim_output)

        # ── Tab 2: Red Team Defense Suite ────────────────────────────────
        with gr.Tab("Red Team Defense"):
            gr.Markdown("Execute 6 automated adversarial attack vectors against the active merchant policy. All attacks should be blocked or escalated — zero should pass unauthorized.")
            rt_merchant = gr.Dropdown(MERCHANT_CHOICES, value="acme-saas", label="Target Merchant")
            rt_btn = gr.Button("Run 6-Attack Suite", variant="stop")
            rt_output = gr.Dataframe(
                headers=["Attack", "Description", "Enforcement Code", "Outcome", "Latency"],
                label="Attack Results",
                interactive=False,
            )
            rt_btn.click(run_red_team, inputs=rt_merchant, outputs=rt_output)

        # ── Tab 3: OpenEnv Agent Arena ───────────────────────────────────
        with gr.Tab("OpenEnv Agent Arena"):
            gr.Markdown("""
Benchmark 4 built-in autonomous buyer agents against the KEOZ policy gateway.
Each agent runs multiple negotiation episodes. The leaderboard ranks them by composite score (rewards - penalties).

- **Strategic Agent**: Pushes 8% discount with Net-30. Optimal boundary play.
- **Conservative Agent**: Offers 5% below list, prepaid. Safe and boring.
- **Greedy Agent**: Demands 40% off with Net-90. Gets blocked often.
- **Adversarial Agent**: 80% discount, forbidden terms. Always blocked.
            """)
            with gr.Row():
                arena_episodes = gr.Slider(minimum=10, maximum=100, value=25, step=5, label="Episodes per Agent")
                arena_merchant = gr.Dropdown(MERCHANT_CHOICES, value="acme-saas", label="Merchant Environment")
            arena_btn = gr.Button("Run Agent Benchmark", variant="primary")
            arena_output = gr.Dataframe(
                headers=["Agent", "Win Rate", "Wins/Total", "Escalated", "Blocked", "Cumulative Reward", "Avg Discount", "Score"],
                label="Agent Leaderboard",
                interactive=False,
            )
            arena_btn.click(run_agent_benchmark, inputs=[arena_episodes, arena_merchant], outputs=arena_output)

        # ── Tab 4: DPO Dataset Generator ────────────────────────────────
        with gr.Tab("DPO / SFT Dataset Generator"):
            gr.Markdown("""
Generate synthetic training datasets from the KEOZ OpenEnv for fine-tuning LLMs via DPO or SFT.

- **DPO pairs**: `chosen` (policy-compliant counter-offers) vs `rejected` (margin-draining hallucinations).
- **SFT pairs**: `instruction` → `output` (correct counter-offers only).

Use these datasets with Hugging Face `trl` (`DPOTrainer` / `SFTTrainer`) to train models like Llama-3, Qwen, or Mistral into policy-aware commercial agents.
            """)
            with gr.Row():
                ds_samples = gr.Slider(minimum=10, maximum=500, value=50, step=10, label="Number of Samples")
                ds_merchant = gr.Dropdown(MERCHANT_CHOICES, value="acme-saas", label="Merchant Policy")
                ds_type = gr.Dropdown(["DPO (Preference Pairs)", "SFT (Instruction Tuning)"], value="DPO (Preference Pairs)", label="Dataset Type")
            ds_btn = gr.Button("Generate & Preview Dataset", variant="primary")
            ds_output = gr.Markdown(value="*Click Generate to create synthetic training samples.*")
            ds_btn.click(generate_dataset_preview, inputs=[ds_samples, ds_merchant, ds_type], outputs=ds_output)

        # ── Tab 5: Audit Trail ──────────────────────────────────────────
        with gr.Tab("Immutable Audit Trail"):
            gr.Markdown("SHA-256 hash-chained decision atoms stored in SQLite. Each atom links to the previous via cryptographic hash, forming an immutable chain.")
            audit_btn = gr.Button("Replay Audit Trail")
            audit_output = gr.Markdown(value="*Click Replay to view the hash chain.*")
            audit_btn.click(view_audit_trail, outputs=audit_output)


# ── Mount alongside FastAPI ─────────────────────────────────────────────────
from keoz.server.app import app

app = gr.mount_gradio_app(app, demo, path="/gradio")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
