"""Bounded request and response contracts for the local AdvanCore API."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool

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


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OwnerGoalRequest(StrictRequest):
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


class LocalActionSessionResponse(BaseModel):
    action_token: str
    lifetime: str = "process"


class OrchestrationLaunchRequest(StrictRequest):
    goal: str = Field(min_length=1, max_length=MAX_GOAL_LENGTH)
    confirmed: StrictBool


class OrchestrationResumeRequest(StrictRequest):
    confirmed: StrictBool


class OrchestrationActionRequest(StrictRequest):
    action: Literal[
        "APPROVE_TASK",
        "BLOCK_TASK",
        "APPROVE_IMPLEMENTATION",
        "REWORK_IMPLEMENTATION",
        "BLOCK_IMPLEMENTATION",
    ]
    confirmed: StrictBool
    owner_note: str | None = Field(default=None, max_length=400)


class OrchestrationPreviewResponse(BaseModel):
    run_id: str
    task_id: str | None
    phase: str
    status: str
    owner_decision_required: bool
    next_action: str
    planner_launched: bool = False
    worker_launched: bool = False
    mutations_performed: list[str]


class OrchestrationJobResponse(BaseModel):
    job_id: str
    operation: str
    state: str
    terminal: bool
    run_id: str | None
    task_id: str | None
    phase: str | None
    status: str | None
    owner_decision_required: bool
    message: str
    next_action: str | None
    events_url: str
    updated_at: datetime


class OrchestrationRunResponse(BaseModel):
    run_id: str
    task_id: str | None
    phase: str
    status: str
    branch: str | None
    completed_phases: list[str]
    owner_decision_count: int
    push_verified: bool
    updated_at: datetime
    messages: list[str]
