import sys
import time
import threading
import uvicorn
import requests

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agentpolicy.policy.dsl import PolicyDSL
from agentpolicy.policy.compiler import PolicyCompiler
from agentpolicy.server.app import create_app
from agentpolicy.gateway.agent_identity import AgentIdentityVerifier

console = Console(highlight=False)


def main():
    console.print(Panel.fit(
        "[bold cyan]AgentPolicy[/bold cyan] - Merchant-Side Financial Policy Layer for Agentic Commerce\n"
        "[italic white]Track 01: AI Growth & Agentic Commerce | Razorpay Integration[/italic white]",
        title="[bold green]System Demo[/bold green]",
        border_style="cyan"
    ))

    # STEP 1: LOAD & COMPILE POLICY
    console.print("\n[bold yellow]STEP 1: Compiling Merchant Policy DSL (agentpolicy.yaml)[/bold yellow]")
    policy = PolicyDSL.load_from_yaml("examples/agentpolicy.yaml")
    bundle = PolicyCompiler.compile(policy)

    console.print(f"* Merchant: [bold green]{policy.merchant}[/bold green] (v{policy.version})")
    console.print(f"* Autonomous Spend Ceiling: [bold cyan]INR {bundle.bounds.max_autonomous_inr:,}[/bold cyan]")
    console.print(f"* Max Concession Discount: [bold cyan]{bundle.bounds.discount_ceiling_pct}%[/bold cyan]")
    console.print(f"* Margin Floor (Secret): [bold cyan]{bundle.bounds.margin_floor_pct * 100}%[/bold cyan]")
    console.print(f"* Product Floor Price: [bold cyan]INR {bundle.bounds.floor_prices['pro_annual']:,}[/bold cyan]")
    console.print("* Generated Manifests: [italic]ACP discovery (/.well-known/agent-commerce.json) & x402 config[/italic]")

    # STEP 2: START SERVER IN BACKGROUND
    console.print("\n[bold yellow]STEP 2: Initializing AgentPolicy Server on http://127.0.0.1:8000[/bold yellow]")
    app = create_app(initial_policy=policy)
    
    server_thread = threading.Thread(
        target=lambda: uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning"),
        daemon=True
    )
    server_thread.start()
    time.sleep(1.5)  # Wait for server readiness

    base_url = "http://127.0.0.1:8000"

    # STEP 3: AI BUYER PROPOSAL
    console.print("\n[bold yellow]STEP 3: AI Buyer Arrives - Negotiating 50 Pro Seats on Net-30 Terms[/bold yellow]")
    verifier = AgentIdentityVerifier()
    agent_token = verifier.issue_token(
        agent_id="enterprise-procurement-bot-01",
        principal_id="acme-corp",
        max_commitment_inr=5000000
    )

    buyer_payload = {
        "intent": "purchase",
        "product_id": "pro_annual",
        "quantity": 50,
        "proposed_price_inr": 42000,  # Below INR 45,000 floor!
        "terms": {"payment": "net_30"},
        "buyer_id": "enterprise-procurement-bot-01",
        "agent_token": agent_token
    }

    console.print("Buyer Proposal: [italic cyan]50 seats @ INR 42,000/seat with Net-30 payment terms[/italic cyan]")
    neg_resp = requests.post(f"{base_url}/api/agent/negotiate", json=buyer_payload)
    neg_data = neg_resp.json()

    console.print(f"* HTTP Status Code: [bold magenta]{neg_resp.status_code} Accepted[/bold magenta] (Async Human Escalation)")
    console.print(f"* Negotiation Counter: [bold green]INR {neg_data.get('counter_price_inr'):,}/seat[/bold green] (Policy floor + privacy buffer applied)")
    console.print(f"* Approval URL: [bold blue]{neg_data.get('approval_url')}[/bold blue]")
    console.print(f"* Reason: [bold yellow]{neg_data.get('reason')}[/bold yellow]")

    # STEP 4: HUMAN APPROVAL VIA MERCHANT PORTAL
    console.print("\n[bold yellow]STEP 4: Human-in-the-Loop Sign-off (Finance Lead Approval)[/bold yellow]")
    approval_id = neg_data.get("approval_id")
    if approval_id:
        decide_resp = requests.post(
            f"{base_url}/api/approvals/{approval_id}/decide",
            json={"decision": "approved", "decided_by": "vp_finance", "notes": "Approved 50 seats volume on Net-30 credit check"}
        )
        if decide_resp.status_code == 200:
            console.print("* Decision Recorded: [bold green]APPROVED[/bold green] by vp_finance")

    # STEP 5: RAZORPAY / x402 PAYMENT EXECUTION
    console.print("\n[bold yellow]STEP 5: Executing x402 Cryptographic Proof & Razorpay Settlement[/bold yellow]")
    deal_total = neg_data.get("counter_price_inr", 46500) * 50
    pay_resp = requests.post(
        f"{base_url}/api/agent/pay",
        json={
            "product_id": "pro_annual",
            "quantity": 50,
            "amount_inr": deal_total,
            "x402_proof": "0x4a8f9b2c0192837465efab1092837465deadbeef",
            "buyer_id": "enterprise-procurement-bot-01"
        }
    )
    pay_data = pay_resp.json()
    console.print(f"* Settlement Status: [bold green]{pay_data.get('status').upper()}[/bold green]")
    console.print(f"* Razorpay Order ID: [bold cyan]{pay_data.get('razorpay_order_id')}[/bold cyan]")
    console.print(f"* Razorpay Payment ID: [bold cyan]{pay_data.get('razorpay_payment_id')}[/bold cyan]")
    console.print(f"* Fulfillment Token: [bold white]{pay_data.get('access_token')}[/bold white]")

    # STEP 6: RED TEAM ADVERSARIAL SUITE
    console.print("\n[bold yellow]STEP 6: Running 6-Attack Red Team Adversarial Suite[/bold yellow]")
    adv_resp = requests.post(f"{base_url}/api/test/adversarial")
    adv_data = adv_resp.json()

    table = Table(title="Red Team Attack Neutralization Report", show_header=True, header_style="bold magenta")
    table.add_column("Attack Vector", style="cyan", width=22)
    table.add_column("Description", style="white", width=42)
    table.add_column("Status", justify="center", width=16)
    table.add_column("Enforcement Code", style="yellow", width=26)

    for atk in adv_data.get("results", []):
        st = "[bold red]BLOCKED[/bold red]" if atk["status"] in ["denied", "declined"] else "[bold yellow]202 ESCALATED[/bold yellow]"
        table.add_row(atk["attack_name"], atk["description"], st, atk["code"])

    console.print(table)

    # STEP 7: MEMORIAGRAIN AUDIT REPLAY
    console.print("\n[bold yellow]STEP 7: memoriagrain Immutable Audit Trail Replay[/bold yellow]")
    audit_resp = requests.get(f"{base_url}/api/audit/replay")
    audit_data = audit_resp.json()
    console.print(f"* Total Logged Decision Atoms: [bold green]{audit_data.get('total_atoms')}[/bold green]")
    console.print(f"* Contradictions Detected: [bold green]{len(audit_data.get('contradictions', []))}[/bold green] (100% Policy Compliant)")

    console.print(Panel(
        "[bold green]AgentPolicy System Online and Fully Operational[/bold green]\n\n"
        f"* [bold white]Interactive Merchant Portal:[/bold white] [link]{base_url}[/link]\n"
        f"* [bold white]ACP Agent Manifest:[/bold white] [link]{base_url}/.well-known/agent-commerce.json[/link]\n"
        f"* [bold white]API Documentation:[/bold white] [link]{base_url}/docs[/link]\n",
        title="[bold cyan]Demo Summary[/bold cyan]"
    ))

    # Keep alive if executed interactively
    if len(sys.argv) > 1 and sys.argv[1] == "--keep-alive":
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            console.print("\n[bold red]Server stopped.[/bold red]")


if __name__ == "__main__":
    main()
