"""FastAPI Application for KEOZ Merchant Command Center & Gateway."""

from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager
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
from ..registry import MerchantRegistry, registry
from ..storage import init_db
from ..metrics import metrics


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle manager."""
    await init_db()
    await registry.initialize()
    yield


def create_app(
    initial_policy: Optional[MerchantPolicy] = None,
    log_file_path: Optional[Path] = None,
    merchant_registry: Optional[MerchantRegistry] = None
) -> FastAPI:
    app = FastAPI(
        title="KEOZ Merchant Command Center",
        description="The Merchant Command Center for Agentic Commerce (Razorpay & Agent Commerce Protocol)",
        version="1.0.0",
        lifespan=lifespan
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    reg = merchant_registry or registry

    # If initial_policy provided, register as default
    if initial_policy is not None:
        bundle = PolicyCompiler.compile(initial_policy)
        import yaml
        yaml_content = yaml.dump(initial_policy.model_dump())
        reg.register_merchant_sync(initial_policy.merchant, yaml_content, make_default=True)
    else:
        bundle = reg.get_bundle()

    # Initialize Subsystems
    identity_verifier = AgentIdentityVerifier()
    composed_validator = ComposedDealValidator(default_margin_floor=bundle.bounds.margin_floor_pct)
    approval_bridge = ApprovalBridge()

    gateway = AuthorizationGateway(
        identity_verifier=identity_verifier,
        composed_validator=composed_validator,
        approval_bridge=approval_bridge
    )

    audit_logger = AuditLogger(storage_path=log_file_path)
    razorpay_client = RazorpayClient()

    # Record Genesis Atom if audit trail empty
    if len(audit_logger.replay()) == 0:
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
    router = create_router(reg, gateway, audit_logger, razorpay_client)
    app.include_router(router)

    # Mount Static UI
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        @app.get("/")
        async def serve_index():
            return FileResponse(static_dir / "index.html")

    return app


# Default app instance for uvicorn
app = create_app()
