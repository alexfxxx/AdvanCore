"""Read-only Projects and Knowledge endpoints."""

from fastapi import APIRouter, HTTPException, Request, status

from advancore.api.dependencies import ReadModelUnavailable
from advancore.api.schemas import KnowledgeResponse, ProjectResponse


router = APIRouter(prefix="/api", tags=["read models"])


@router.get("/projects", response_model=list[ProjectResponse])
def list_projects(request: Request) -> list[ProjectResponse]:
    try:
        return list(request.app.state.read_gateway.list_projects())
    except ReadModelUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.get("/knowledge", response_model=list[KnowledgeResponse])
def list_knowledge(request: Request) -> list[KnowledgeResponse]:
    try:
        return list(request.app.state.read_gateway.list_knowledge())
    except ReadModelUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
