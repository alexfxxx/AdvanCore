"""Controller-mediated orchestration launch, action and progress routes."""

from __future__ import annotations

import asyncio
import ipaddress
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse

from advancore.api.orchestration_service import (
    OrchestrationJobBusy,
    OrchestrationJobNotFound,
    OrchestrationRunNotFound,
)
from advancore.api.schemas import (
    LocalActionSessionResponse,
    OrchestrationActionRequest,
    OrchestrationJobResponse,
    OrchestrationLaunchRequest,
    OrchestrationPreviewResponse,
    OrchestrationResumeRequest,
    OrchestrationRunResponse,
    OwnerGoalRequest,
)


router = APIRouter(prefix="/api", tags=["orchestration"])
_RUN_ID_PATTERN = re.compile(r"^ORCH-[A-Za-z0-9_-]{1,120}$")


def require_run_id(run_id: str) -> str:
    if not _RUN_ID_PATTERN.fullmatch(run_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Orchestration run identifier is invalid.",
        )
    return run_id


def require_loopback_peer(request: Request) -> None:
    client = request.client
    try:
        address = ipaddress.ip_address(client.host if client is not None else "")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local controller access requires a verified loopback peer.",
        ) from exc
    if not address.is_loopback:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local controller access requires a verified loopback peer.",
        )


def require_local_action(request: Request) -> None:
    require_loopback_peer(request)
    origin = request.headers.get("origin")
    if origin not in request.app.state.allowed_origins:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Mutating orchestration requests require an approved loopback Origin.",
        )
    supplied = request.headers.get("x-advancore-action-token", "")
    if not secrets.compare_digest(supplied, request.app.state.action_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local action token is missing or invalid.",
        )


def require_confirmation(confirmed: bool) -> None:
    if confirmed is not True:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Explicit owner confirmation is required.",
        )


def _job_error(exc: RuntimeError) -> HTTPException:
    if isinstance(exc, OrchestrationJobBusy):
        return HTTPException(status.HTTP_409_CONFLICT, detail=str(exc))
    return HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get(
    "/session",
    response_model=LocalActionSessionResponse,
    dependencies=[Depends(require_loopback_peer)],
)
def local_session(request: Request, response: Response) -> LocalActionSessionResponse:
    response.headers["Cache-Control"] = "no-store"
    return LocalActionSessionResponse(action_token=request.app.state.action_token)


@router.post(
    "/orchestrations/preview",
    response_model=OrchestrationPreviewResponse,
)
def preview_orchestration(
    payload: OwnerGoalRequest, request: Request
) -> OrchestrationPreviewResponse:
    return request.app.state.orchestration_service.preview(payload.goal)


@router.post(
    "/orchestrations",
    response_model=OrchestrationJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_local_action)],
)
def start_orchestration(
    payload: OrchestrationLaunchRequest, request: Request
) -> OrchestrationJobResponse:
    require_confirmation(payload.confirmed)
    try:
        return request.app.state.orchestration_service.start(payload.goal)
    except OrchestrationJobBusy as exc:
        raise _job_error(exc) from exc


@router.post(
    "/orchestrations/{run_id}/resume",
    response_model=OrchestrationJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_local_action)],
)
def resume_orchestration(
    run_id: str,
    payload: OrchestrationResumeRequest,
    request: Request,
) -> OrchestrationJobResponse:
    require_confirmation(payload.confirmed)
    require_run_id(run_id)
    try:
        return request.app.state.orchestration_service.resume(run_id)
    except OrchestrationJobBusy as exc:
        raise _job_error(exc) from exc


@router.post(
    "/orchestrations/{run_id}/actions",
    response_model=OrchestrationJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_local_action)],
)
def submit_owner_action(
    run_id: str,
    payload: OrchestrationActionRequest,
    request: Request,
) -> OrchestrationJobResponse:
    require_confirmation(payload.confirmed)
    require_run_id(run_id)
    try:
        return request.app.state.orchestration_service.owner_action(
            run_id, payload.action, payload.owner_note
        )
    except (OrchestrationJobBusy, ValueError) as exc:
        if isinstance(exc, ValueError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Owner action is invalid.",
            ) from exc
        raise _job_error(exc) from exc


@router.get(
    "/orchestration-jobs/current",
    response_model=OrchestrationJobResponse,
)
def get_current_job(request: Request) -> OrchestrationJobResponse:
    try:
        return request.app.state.orchestration_service.get_current_job()
    except OrchestrationJobNotFound as exc:
        raise _job_error(exc) from exc


@router.get(
    "/orchestration-jobs/{job_id}",
    response_model=OrchestrationJobResponse,
)
def get_job(job_id: str, request: Request) -> OrchestrationJobResponse:
    try:
        return request.app.state.orchestration_service.get_job(job_id)
    except OrchestrationJobNotFound as exc:
        raise _job_error(exc) from exc


@router.get(
    "/orchestrations/{run_id}",
    response_model=OrchestrationRunResponse,
)
def get_run(run_id: str, request: Request) -> OrchestrationRunResponse:
    require_run_id(run_id)
    try:
        return request.app.state.orchestration_service.get_run(run_id)
    except OrchestrationRunNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/orchestration-jobs/{job_id}/events")
async def stream_job(job_id: str, request: Request) -> StreamingResponse:
    try:
        request.app.state.orchestration_service.get_job(job_id)
    except OrchestrationJobNotFound as exc:
        raise _job_error(exc) from exc

    async def events():
        previous = None
        keepalive = 0
        while not await request.is_disconnected():
            try:
                snapshot = request.app.state.orchestration_service.get_job(job_id)
            except OrchestrationJobNotFound:
                return
            payload = snapshot.model_dump_json()
            if payload != previous:
                yield f"event: progress\ndata: {payload}\n\n"
                previous = payload
                keepalive = 0
            else:
                keepalive += 1
                if keepalive >= 20:
                    yield ": keepalive\n\n"
                    keepalive = 0
            if snapshot.terminal:
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
