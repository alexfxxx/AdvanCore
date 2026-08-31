"""FastAPI application factory for the primary local AdvanCore app."""

import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Awaitable, Callable

from fastapi import FastAPI, Request, status as fastapi_status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from advancore.api.dependencies import (
    ControllerOwnerGoalPreviewer,
    DatabaseReadModelGateway,
    OwnerGoalPreviewer,
    ReadModelGateway,
)
from advancore.api.editing_gateway import DatabaseEditingGateway, EditingGateway
from advancore.api.orchestration_service import GovernedOrchestrationService
from advancore.api.routes import (
    editing,
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
MAX_LOCAL_EDIT_REQUEST_BYTES = 128 * 1024
LOCAL_EDIT_PATH_PREFIXES = (
    "/api/projects",
    "/api/knowledge",
    "/api/legal-entities",
    "/api/vehicles",
    "/api/drivers",
    "/api/customers",
    "/api/routes",
)


class BoundedLocalEditBodyMiddleware:
    """Buffer at most one bounded local-edit body before FastAPI validation."""

    def __init__(
        self,
        app,
        *,
        max_bytes: int = MAX_LOCAL_EDIT_REQUEST_BYTES,
        path_prefixes: tuple[str, ...] = LOCAL_EDIT_PATH_PREFIXES,
    ):
        self.app = app
        self.max_bytes = max_bytes
        self.path_prefixes = path_prefixes

    async def __call__(self, scope, receive, send) -> None:
        if (
            scope.get("type") != "http"
            or scope.get("method") != "POST"
            or not scope.get("path", "").startswith(self.path_prefixes)
        ):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", ()))
        declared = headers.get(b"content-length")
        if declared is not None:
            try:
                declared_length = int(declared)
            except ValueError:
                declared_length = self.max_bytes + 1
            if declared_length < 0 or declared_length > self.max_bytes:
                await self._too_large(scope, receive, send)
                return

        chunks: list[bytes] = []
        received = 0
        while True:
            message = await receive()
            if message.get("type") != "http.request":
                await self.app(scope, self._single_receive(message), send)
                return
            chunk = message.get("body", b"")
            received += len(chunk)
            if received > self.max_bytes:
                await self._too_large(scope, receive, send)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break

        replay = {
            "type": "http.request",
            "body": b"".join(chunks),
            "more_body": False,
        }
        await self.app(scope, self._single_receive(replay), send)

    @staticmethod
    def _single_receive(message) -> Callable[[], Awaitable[dict]]:
        delivered = False

        async def receive_once() -> dict:
            nonlocal delivered
            if delivered:
                return {"type": "http.disconnect"}
            delivered = True
            return message

        return receive_once

    @staticmethod
    async def _too_large(scope, receive, send) -> None:
        response = JSONResponse(
            status_code=fastapi_status.HTTP_413_CONTENT_TOO_LARGE,
            content={"detail": "Local edit request is too large."},
        )
        await response(scope, receive, send)


def create_app(
    *,
    repo_root: Path | None = None,
    frontend_dir: Path | None = None,
    read_gateway: ReadModelGateway | None = None,
    goal_previewer: OwnerGoalPreviewer | None = None,
    orchestration_service: GovernedOrchestrationService | None = None,
    edit_gateway: EditingGateway | None = None,
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
            "Primary loopback-only presentation API. Confirmed record changes "
            "delegate to existing application services; controller, worker, direct "
            "database and publication authority remain unavailable to the browser."
        ),
        lifespan=lifespan,
    )
    app.state.read_gateway = read_gateway or DatabaseReadModelGateway(resolved_root)
    app.state.goal_previewer = goal_previewer or ControllerOwnerGoalPreviewer(
        resolved_root
    )
    app.state.orchestration_service = resolved_orchestration
    app.state.edit_gateway = edit_gateway or DatabaseEditingGateway()
    app.state.action_token = secrets.token_urlsafe(32)
    app.state.allowed_origins = frozenset(LOOPBACK_ORIGINS)

    @app.exception_handler(RequestValidationError)
    async def bounded_validation_error(
        _request: Request, _exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=fastapi_status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": "Request validation failed."},
        )

    app.add_middleware(
        BoundedLocalEditBodyMiddleware,
        max_bytes=MAX_LOCAL_EDIT_REQUEST_BYTES,
        path_prefixes=LOCAL_EDIT_PATH_PREFIXES,
    )

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
    app.include_router(editing.router)
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
                "Cache-Control": "no-store",
                "Content-Security-Policy": (
                    "default-src 'self'; script-src 'self'; style-src 'self'; "
                    "connect-src 'self'; img-src 'self' data:; object-src 'none'; "
                    "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
                )
            },
        )

    return app
