"""FastAPI Application for AgentPolicy Merchant Gateway & Portal."""

from pathlib import Path
from typing import Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .routes import create_router
from ..policy.models import MerchantPolicy, ProductConfig
from ..policy.compiler import PolicyCompiler
from ..gateway.authorizer import AuthorizationGateway
from ..gateway.agent_identity import AgentIdentityVerifier
from ..gateway.composed_validator import ComposedDealValidator
from ..gateway.approvals import ApprovalBridge
from ..memory.audit_logger import AuditLogger
from ..payments.razorpay_client import RazorpayClient


def create_app(
    initial_policy: Optional[MerchantPolicy] = None,
    log_file_path: Optional[Path] = None
) -> FastAPI:
    app = FastAPI(
        title="AgentPolicy Merchant Gateway",
        description="Machine-readable financial policy engine and authorization layer for agentic commerce",
        version="1.0.0"
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize default policy if none provided
    if initial_policy is None:
        initial_policy = MerchantPolicy(
            version="1.0",
            merchant="acme-cloud-solutions",
            products=[
                ProductConfig(
                    id="pro_annual",
                    name="Pro Annual License",
                    min_price_inr=45000,
                    list_price_inr=50000,
                    unit_cost_inr=28350,
                    max_seats_per_transaction=50,
                    auto_renew=True
                ),
                ProductConfig(
                    id="enterprise_custom",
                    name="Enterprise Suite",
                    min_price_inr=150000,
                    list_price_inr=200000,
                    unit_cost_inr=90000,
                    max_seats_per_transaction=500,
                    requires_human_approval=True
                )
            ]
        )

    # Compile Initial Bundle
    bundle = PolicyCompiler.compile(initial_policy)
    bundle_ref = {"bundle": bundle}

    # Initialize Subsystems
    identity_verifier = AgentIdentityVerifier()
    composed_validator = ComposedDealValidator(default_margin_floor=initial_policy.authorization.margin_floor_pct)
    approval_bridge = ApprovalBridge()

    gateway = AuthorizationGateway(
        identity_verifier=identity_verifier,
        composed_validator=composed_validator,
        approval_bridge=approval_bridge
    )

    audit_logger = AuditLogger(storage_path=log_file_path)
    razorpay_client = RazorpayClient()

    # Record Genesis Atom
    audit_logger.record(
        atom_type="bounds_compiled",
        policy_version=bundle.version,
        policy_hash=bundle.policy_hash,
        payload={
            "merchant": bundle.policy.merchant,
            "max_autonomous_inr": bundle.bounds.max_autonomous_inr,
            "discount_ceiling_pct": bundle.bounds.discount_ceiling_pct,
            "margin_floor_pct": bundle.bounds.margin_floor_pct,
            "floor_prices": bundle.bounds.floor_prices
        }
    )

    # Mount API Routes
    router = create_router(bundle_ref, gateway, audit_logger, razorpay_client)
    app.include_router(router)

    # Static UI
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        @app.get("/")
        async def serve_index():
            return FileResponse(static_dir / "index.html")

    return app
