"""Bounded local system-status endpoint."""

from fastapi import APIRouter, Request

from advancore.api.schemas import SystemStatusResponse


router = APIRouter(prefix="/api", tags=["system"])


@router.get("/status", response_model=SystemStatusResponse)
def get_status(request: Request) -> SystemStatusResponse:
    return request.app.state.read_gateway.status()
