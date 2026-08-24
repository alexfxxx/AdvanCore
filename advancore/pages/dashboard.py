"""Streamlit presentation for the bounded operational overview."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import streamlit as st

from advancore.repositories import (
    ActivityLogRepository,
    KnowledgeItemRepository,
    ProjectRepository,
)
from advancore.services.dashboard_service import DashboardService
from advancore.services.worker_usage_service import UsageState, WorkerUsageService


@contextmanager
def _dashboard_service() -> Iterator[DashboardService]:
    from advancore.services.database import session_scope

    with session_scope() as session:
        yield DashboardService(
            ProjectRepository(session),
            KnowledgeItemRepository(session),
            ActivityLogRepository(session),
        )


def _worker_usage_service() -> WorkerUsageService:
    return WorkerUsageService(Path(__file__).resolve().parents[2])


def _render_worker_usage() -> None:
    summary = _worker_usage_service().get_summary("kimi")
    st.subheader("AI worker budget")
    used = (
        f"{summary.weekly_used_percent:g}%"
        if summary.weekly_used_percent is not None else "Unavailable"
    )
    runtime = (
        f"{summary.runtime_seconds // 60} / {summary.runtime_limit_seconds // 60} min"
        if summary.runtime_seconds is not None else "Unavailable"
    )
    st.metric("Kimi weekly usage", used)
    st.metric("Kimi policy limit", f"{summary.weekly_percent_limit:g}%")
    st.metric("Kimi runtime this week", runtime)

    if summary.state == UsageState.AVAILABLE:
        st.success("Kimi is within the approved weekly budget.")
    elif summary.state == UsageState.PAUSED:
        st.error("Kimi is paused by the weekly usage policy. Use an approved fallback.")
    else:
        st.warning(
            "Kimi usage status is unavailable or stale. Kimi launches are paused "
            "unless the approved local controller probe can refresh the reading; "
            "an approved fallback may be used."
        )
    if summary.checked_at and summary.reset_at:
        checked = summary.checked_at.strftime("%Y-%m-%d %H:%M UTC")
        reset = summary.reset_at.strftime("%Y-%m-%d %H:%M UTC")
        st.caption(f"Last checked: {checked}. Provider reset: {reset}.")
    st.caption(
        "Policy: maximum 20% provider-reported weekly usage and 60 minutes "
        "of local Kimi runtime per provider week."
    )

def render():
    st.subheader("Platform Status")
    st.success("Core application shell operational.")
    _render_worker_usage()
    try:
        with st.spinner("Loading overview..."):
            with _dashboard_service() as service:
                summary = service.get_summary()
    except Exception:
        st.error("Operational overview is unavailable. Please check the database.")
        return

    st.success("Database connected.")
    st.subheader("Projects overview")
    st.metric("Total projects", summary.total_projects)
    st.metric("Active projects", summary.active_projects)
    st.metric("Archived projects", summary.archived_projects)
    st.metric("Other project statuses", summary.other_projects)

    st.subheader("Knowledge overview")
    st.metric("Total knowledge items", summary.total_knowledge)
    st.metric("Draft knowledge items", summary.draft_knowledge)
    st.metric("Other knowledge statuses", summary.other_knowledge)

    st.subheader("Activity overview")
    st.metric("Total activity events", summary.total_activity)
    st.metric("Project activity events", summary.project_activity)
    st.metric("Knowledge activity events", summary.knowledge_activity)
    st.metric("Other activity events", summary.other_activity)
    st.caption("Use the navigation menu to manage Projects or capture Knowledge drafts.")
