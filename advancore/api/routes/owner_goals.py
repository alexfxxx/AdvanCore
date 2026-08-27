"""Governed Owner Goal intake with no execution authority."""

from fastapi import APIRouter, Request, status

from advancore.api.schemas import OwnerGoalPreviewResponse, OwnerGoalRequest


router = APIRouter(prefix="/api", tags=["owner goals"])


@router.post(
    "/owner-goals/preview",
    response_model=OwnerGoalPreviewResponse,
    status_code=status.HTTP_200_OK,
)
def preview_owner_goal(
    payload: OwnerGoalRequest,
    request: Request,
) -> OwnerGoalPreviewResponse:
    return request.app.state.goal_previewer.preview(payload.goal)
