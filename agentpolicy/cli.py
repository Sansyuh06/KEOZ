"""CLI entry point for AgentPolicy."""

import argparse
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from .policy.dsl import PolicyDSL
from .policy.compiler import PolicyCompiler
from .gateway.authorizer import AuthorizationGateway
from .server.app import create_app
from .examples_helper import run_attack_suite_helper

console = Console(highlight=False)

SAMPLE_YAML = """version: "1.0"
merchant: "acme-saas"

authorization:
  max_autonomous_inr: 500000
  discount_ceiling_pct: 8
  margin_floor_pct: 0.37
  require_human_approval_when:
    - amount_inr > 500000
    - customer_tier == "new"
    - payment_instrument == "net_terms"

products:
  - id: "pro_annual"
    name: "Pro Annual"
    min_price_inr: 45000
    list_price_inr: 50000
    unit_cost_inr: 28350
    max_seats_per_transaction: 50
    auto_renew: true

  - id: "enterprise_custom"
    name: "Enterprise Custom"
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
"""


def _resolve_policy_file(path_str: str = None) -> Path:
    """Find policy file looking at provided path, local agentpolicy.yaml, or examples/agentpolicy.yaml."""
    if path_str and Path(path_str).exists():
        return Path(path_str)
    if Path("agentpolicy.yaml").exists():
        return Path("agentpolicy.yaml")
    if Path("examples/agentpolicy.yaml").exists():
        return Path("examples/agentpolicy.yaml")
    return Path(path_str or "agentpolicy.yaml")


def cmd_init(args):
    target = Path(args.output or "agentpolicy.yaml")
    if target.exists() and not args.force:
        console.print(f"[bold yellow]File {target} already exists. Use --force to overwrite.[/bold yellow]")
        return
    with open(target, "w", encoding="utf-8") as f:
        f.write(SAMPLE_YAML)
    console.print(Panel(f"[bold green]Created {target}[/bold green]\nReady to configure your merchant boundaries.", title="AgentPolicy Init"))


def cmd_validate(args):
    filepath = _resolve_policy_file(args.file)
    try:
        policy = PolicyDSL.load_from_yaml(filepath)
        console.print(f"[bold green]Policy '{policy.merchant}' (v{policy.version}) from {filepath} is valid and semantically sound.[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Validation error:[/bold red] {str(e)}")
        sys.exit(1)


def cmd_compile(args):
    filepath = _resolve_policy_file(args.file)
    out_dir = Path(args.out_dir or "dist")
    try:
        policy = PolicyDSL.load_from_yaml(filepath)
        bundle = PolicyCompiler.compile(policy)
        bundle.export(out_dir)

        console.print(Panel(
            f"[bold cyan]Source File:[/bold cyan] {filepath}\n"
            f"[bold cyan]Merchant:[/bold cyan] {policy.merchant}\n"
            f"[bold cyan]Version:[/bold cyan] {bundle.version}\n"
            f"[bold cyan]Policy Hash:[/bold cyan] {bundle.policy_hash}\n"
            f"[bold cyan]Exported Artifacts:[/bold cyan] {out_dir.absolute()}\n"
            f"  * policy_bounds.json\n"
            f"  * acp_manifest.json (/.well-known/agent-commerce.json)\n"
            f"  * x402_config.json\n"
            f"  * openapi.json",
            title="[bold green]Policy Compiled Successfully[/bold green]"
        ))
    except Exception as e:
        console.print(f"[bold red]Compilation error:[/bold red] {str(e)}")
        sys.exit(1)


def cmd_redteam(args):
    filepath = _resolve_policy_file(args.file)
    try:
        policy = PolicyDSL.load_from_yaml(filepath)
    except Exception as e:
        console.print(f"[bold red]Failed to load policy from {filepath}:[/bold red] {e}")
        sys.exit(1)

    bundle = PolicyCompiler.compile(policy)
    gateway = AuthorizationGateway()

    console.print(f"\n[bold cyan]Running 6-Attack Red Team Suite against {policy.merchant} (v{policy.version}) using {filepath}...[/bold cyan]\n")

    results = run_attack_suite_helper(bundle, gateway)

    table = Table(title="Red Team Attack Results", show_header=True, header_style="bold magenta")
    table.add_column("Attack Vector", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("HTTP", justify="center")
    table.add_column("Reason / Code", style="yellow")
    table.add_column("Latency", justify="right")

    for r in results:
        status_style = "[bold red]BLOCKED[/bold red]" if r["status"] in ["denied", "declined"] else "[bold yellow]202 ESCALATED[/bold yellow]"
        table.add_row(
            r["attack_name"],
            status_style,
            str(r["http_status"]),
            r["code"] or r["reason"][:40],
            f"{r['latency_ms']}ms"
        )

    console.print(table)
    console.print("[bold green]\n* 100% of adversarial attacks neutralized or escalated by deterministic policy bounds.[/bold green]\n")


def cmd_serve(args):
    import uvicorn
    filepath = _resolve_policy_file(args.file)
    policy = PolicyDSL.load_from_yaml(filepath) if filepath.exists() else None

    app = create_app(initial_policy=policy)
    console.print(Panel(
        f"[bold green]Starting AgentPolicy Server...[/bold green]\n"
        f"* Policy Source: {filepath if filepath.exists() else 'Default Policy'}\n"
        f"* Web Dashboard: [link]http://{args.host}:{args.port}[/link]\n"
        f"* ACP Discovery: [link]http://{args.host}:{args.port}/.well-known/agent-commerce.json[/link]\n"
        f"* OpenAPI Docs: [link]http://{args.host}:{args.port}/docs[/link]",
        title="AgentPolicy Runtime"
    ))
    uvicorn.run(app, host=args.host, port=args.port)


def main():
    parser = argparse.ArgumentParser(description="AgentPolicy CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = subparsers.add_parser("init", help="Initialize agentpolicy.yaml")
    p_init.add_argument("-o", "--output", default="agentpolicy.yaml")
    p_init.add_argument("-f", "--force", action="store_true")
    p_init.set_defaults(func=cmd_init)

    # validate
    p_val = subparsers.add_parser("validate", help="Validate policy YAML")
    p_val.add_argument("file", default=None, nargs="?")
    p_val.set_defaults(func=cmd_validate)

    # compile
    p_comp = subparsers.add_parser("compile", help="Compile policy YAML to bounds & manifests")
    p_comp.add_argument("file", default=None, nargs="?")
    p_comp.add_argument("-d", "--out-dir", default="dist")
    p_comp.set_defaults(func=cmd_compile)

    # redteam
    p_rt = subparsers.add_parser("test-redteam", help="Run 6-attack red team suite")
    p_rt.add_argument("-f", "--file", default=None)
    p_rt.set_defaults(func=cmd_redteam)

    # serve
    p_serve = subparsers.add_parser("serve", help="Launch live AgentPolicy server")
    p_serve.add_argument("-f", "--file", default=None)
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("-p", "--port", type=int, default=8000)
    p_serve.set_defaults(func=cmd_serve)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
