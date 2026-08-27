"""Bounded request and response contracts for the local AdvanCore API."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from advancore.agent_runner.goal_task import MAX_GOAL_LENGTH


class SystemStatusResponse(BaseModel):
    service: str = "AdvanCore local API"
    state: str
    database_configured: bool
    database_reachable: bool
    controller_available: bool
    governance_mode: str = "fail_closed"
    voice_state: str = "disabled"


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class KnowledgeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int | None
    title: str
    content: str
    status: str
    created_at: datetime
    updated_at: datetime


class OwnerGoalRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=MAX_GOAL_LENGTH)


class OwnerGoalPreviewResponse(BaseModel):
    accepted: bool
    normalized_goal: str
    status: str
    candidate_task_id: str | None
    planner_launched: bool = False
    task_written: bool = False
    execution_requested: bool = False
    publication_performed: bool = False
    next_action: str
    messages: list[str]


class ApiErrorResponse(BaseModel):
    detail: str
