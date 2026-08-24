"""Responsive, owner-customizable operational command center."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import streamlit as st

from advancore.repositories import (
    ActivityLogRepository,
    KnowledgeItemRepository,
    ProjectRepository,
    SystemSettingRepository,
)
from advancore.services.dashboard_preference_service import (
    AVAILABLE_DASHBOARD_MODULES,
    AVAILABLE_WORKER_CARDS,
    DEFAULT_DASHBOARD_PREFERENCES,
    DashboardPreferenceService,
    DashboardPreferences,
)
from advancore.services.dashboard_service import DashboardService
from advancore.services.worker_usage_service import UsageState, WorkerUsageService


_MODULE_LABELS = {
    "platform": "Platform status",
    "ai_workforce": "AI workforce",
    "projects": "Projects overview",
    "knowledge": "Knowledge overview",
    "activity": "Activity overview",
}
_WORKER_LABELS = {
    "kimi-swarm": "Kimi / Kimi-Swarm",
    "codex": "Codex",
}


@contextmanager
def _dashboard_service() -> Iterator[DashboardService]:
    from advancore.services.database import session_scope

    with session_scope() as session:
        yield DashboardService(
            ProjectRepository(session),
            KnowledgeItemRepository(session),
            ActivityLogRepository(session),
        )


@contextmanager
def _dashboard_preference_service() -> Iterator[DashboardPreferenceService]:
    from advancore.services.database import session_scope

    with session_scope() as session:
        yield DashboardPreferenceService(SystemSettingRepository(session))


def _worker_usage_service() -> WorkerUsageService:
    return WorkerUsageService(Path(__file__).resolve().parents[2])


def _metric_grid(metrics: list[tuple[str, object]]) -> None:
    """Render metrics in a responsive row without embedding dynamic HTML."""
    if not metrics:
        return
    columns = st.columns(min(4, len(metrics)))
    for index, (label, value) in enumerate(metrics):
        columns[index % len(columns)].metric(label, value)


def _load_preferences() -> DashboardPreferences:
    try:
        with _dashboard_preference_service() as service:
            return service.load()
    except Exception:
        st.warning(
            "Saved dashboard choices are unavailable. The safe default layout is shown."
        )
        return DEFAULT_DASHBOARD_PREFERENCES


def _save_preferences(modules, workers, *, reset: bool = False) -> bool:
    try:
        with _dashboard_preference_service() as service:
            if reset:
                service.reset()
            else:
                service.save(modules, workers)
    except Exception:
        st.error("Dashboard choices could not be saved. Please try again.")
        return False
    return True


def _render_customizer(preferences: DashboardPreferences) -> None:
    with st.expander("Customize command center"):
        st.caption(
            "Add or remove dashboard functions. These display choices never change "
            "AI worker approval, credentials, or controller authority."
        )
        modules = st.multiselect(
            "Visible dashboard functions",
            options=AVAILABLE_DASHBOARD_MODULES,
            default=list(preferences.modules),
            format_func=lambda value: _MODULE_LABELS[value],
            key="dashboard_visible_modules",
        )
        workers = st.multiselect(
            "Visible AI worker cards",
            options=AVAILABLE_WORKER_CARDS,
            default=list(preferences.workers),
            format_func=lambda value: _WORKER_LABELS[value],
            key="dashboard_visible_workers",
        )
        save_column, reset_column = st.columns(2)
        if save_column.button("Save dashboard", key="dashboard_save"):
            if _save_preferences(modules, workers):
                st.session_state.pop("dashboard_visible_modules", None)
                st.session_state.pop("dashboard_visible_workers", None)
                st.success("Dashboard choices saved.")
                st.rerun()
        if reset_column.button("Restore default dashboard", key="dashboard_reset"):
            if _save_preferences((), (), reset=True):
                st.session_state.pop("dashboard_visible_modules", None)
                st.session_state.pop("dashboard_visible_workers", None)
                st.success("Default dashboard restored.")
                st.rerun()


def _render_kimi_usage() -> None:
    summary = _worker_usage_service().get_summary("kimi")
    used = (
        f"{summary.weekly_used_percent:g}%"
        if summary.weekly_used_percent is not None
        else "Unavailable"
    )
    runtime = (
        f"{summary.runtime_seconds // 60} / {summary.runtime_limit_seconds // 60} min"
        if summary.runtime_seconds is not None
        else "Unavailable"
    )
    _metric_grid(
        [
            ("Kimi role", "Primary worker"),
            ("Kimi weekly usage", used),
            ("Kimi policy limit", f"{summary.weekly_percent_limit:g}%"),
            ("Kimi runtime this week", runtime),
        ]
    )

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


def _render_ai_workforce(workers: tuple[str, ...]) -> None:
    st.subheader("AI workforce")
    st.caption(
        "agent_runner controls execution. Dashboard visibility does not grant authority."
    )
    if not workers:
        st.info("No AI worker cards are visible. Add them from Customize command center.")
        return
    if "kimi-swarm" in workers:
        _render_kimi_usage()
    if "codex" in workers:
        _metric_grid(
            [
                ("Codex role", "Approved fallback"),
                ("Codex usage", "Not available in AdvanCore"),
            ]
        )
        st.caption(
            "Codex can be selected only through the existing governed fallback path; "
            "no quota is inferred from chat history."
        )


def render():
    st.header("Executive Command Center")
    st.caption("Real AdvanCore status only — no placeholder business figures.")
    if st.button(
        "Refresh dashboard",
        key="dashboard_refresh",
        help="Reload the latest available dashboard data and local status.",
    ):
        st.success("Dashboard refreshed with the latest available data.")
    preferences = _load_preferences()
    _render_customizer(preferences)
    visible = set(preferences.modules)

    if not visible:
        st.info(
            "No dashboard functions are visible. Use Customize command center to add one."
        )
        return

    if "platform" in visible:
        st.subheader("Platform status")
        st.success("Core application shell operational.")

    if "ai_workforce" in visible:
        _render_ai_workforce(preferences.workers)

    summary_modules = {"platform", "projects", "knowledge", "activity"}
    if not visible.intersection(summary_modules):
        return
    try:
        with st.spinner("Loading overview..."):
            with _dashboard_service() as service:
                summary = service.get_summary()
    except Exception:
        st.error("Operational overview is unavailable. Please check the database.")
        return

    if "platform" in visible:
        st.success("Database connected.")
    if "projects" in visible:
        st.subheader("Projects overview")
        _metric_grid(
            [
                ("Total projects", summary.total_projects),
                ("Active projects", summary.active_projects),
                ("Archived projects", summary.archived_projects),
                ("Other project statuses", summary.other_projects),
            ]
        )
    if "knowledge" in visible:
        st.subheader("Knowledge overview")
        _metric_grid(
            [
                ("Total knowledge items", summary.total_knowledge),
                ("Draft knowledge items", summary.draft_knowledge),
                ("Other knowledge statuses", summary.other_knowledge),
            ]
        )
    if "activity" in visible:
        st.subheader("Activity overview")
        _metric_grid(
            [
                ("Total activity events", summary.total_activity),
                ("Project activity events", summary.project_activity),
                ("Knowledge activity events", summary.knowledge_activity),
                ("Other activity events", summary.other_activity),
            ]
        )
    st.caption("Use the navigation menu to manage Projects or capture Knowledge drafts.")
