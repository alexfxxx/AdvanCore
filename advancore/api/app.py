"""FastAPI application factory for the decoupled local AdvanCore console."""

import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from advancore.api.dependencies import (
    ControllerOwnerGoalPreviewer,
    DatabaseReadModelGateway,
    OwnerGoalPreviewer,
    ReadModelGateway,
)
from advancore.api.orchestration_service import GovernedOrchestrationService
from advancore.api.routes import (
    modules,
    operations,
    orchestration,
    owner_goals,
    read_models,
    status,
    voice,
)


LOOPBACK_ORIGINS = (
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://127.0.0.1:5500",
    "http://localhost:5500",
)


def create_app(
    *,
    repo_root: Path | None = None,
    frontend_dir: Path | None = None,
    read_gateway: ReadModelGateway | None = None,
    goal_previewer: OwnerGoalPreviewer | None = None,
    orchestration_service: GovernedOrchestrationService | None = None,
) -> FastAPI:
    resolved_root = (repo_root or Path(__file__).resolve().parents[2]).resolve()
    resolved_frontend = (frontend_dir or resolved_root / "frontend").resolve()
    resolved_orchestration = (
        orchestration_service or GovernedOrchestrationService(resolved_root)
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            shutdown = getattr(resolved_orchestration, "shutdown", None)
            if callable(shutdown):
                shutdown()

    app = FastAPI(
        title="AdvanCore Local API",
        version="0.1.0",
        description=(
            "Loopback-only presentation API. It does not grant controller, "
            "worker, database-write or publication authority."
        ),
        lifespan=lifespan,
    )
    app.state.read_gateway = read_gateway or DatabaseReadModelGateway(resolved_root)
    app.state.goal_previewer = goal_previewer or ControllerOwnerGoalPreviewer(
        resolved_root
    )
    app.state.orchestration_service = resolved_orchestration
    app.state.action_token = secrets.token_urlsafe(32)
    app.state.allowed_origins = frozenset(LOOPBACK_ORIGINS)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(LOOPBACK_ORIGINS),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-AdvanCore-Action-Token"],
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "testserver"],
    )

    app.include_router(status.router)
    app.include_router(modules.router)
    app.include_router(read_models.router)
    app.include_router(operations.router)
    app.include_router(owner_goals.router)
    app.include_router(orchestration.router)
    app.include_router(voice.router)

    app.mount(
        "/assets",
        StaticFiles(directory=resolved_frontend),
        name="frontend-assets",
    )

    @app.get("/", include_in_schema=False, response_class=FileResponse)
    def index() -> FileResponse:
        return FileResponse(
            resolved_frontend / "index.html",
            headers={
                "Content-Security-Policy": (
                    "default-src 'self'; script-src 'self'; style-src 'self'; "
                    "connect-src 'self'; img-src 'self' data:; object-src 'none'; "
                    "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
                )
            },
        )

    return app
