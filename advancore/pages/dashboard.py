"""Responsive, owner-customizable operational command center."""

from collections.abc import Iterator
from contextlib import contextmanager
import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

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
from advancore.services.ai_usage_dashboard_service import (
    AiUsageCard,
    AiUsageDashboardService,
    BalanceState,
    ProviderUsageObservationStore,
)
from advancore.services.local_backup_service import LocalBackupService
from advancore.services.platform_readiness_service import (
    PlatformReadinessService,
    ReadinessLevel,
)
from advancore.services.readiness_service import ReadinessService
from advancore.services.recovery_evidence_service import RecoveryEvidenceService
from advancore.services.worker_usage_service import WorkerUsageService
from advancore.services.worker_auth_readiness_service import (
    WorkerAuthReadinessService,
    WorkerAuthState,
)
from advancore.ui.custom_components import render_fuel_status_component
from advancore.ui.fuel_trends import ALLOWED_FUEL_WINDOWS, build_fuel_trend_figure


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
    "gemini": "Gemini",
}
_FUEL_WINDOW_LABELS = {
    7: "Latest 7 readings",
    30: "Latest 30 readings",
    None: "All available readings",
}
_FUEL_WINDOW_STATE_KEY = "dashboard_fuel_window"
_AI_AUTH_SESSION_KEY = "dashboard_ai_auth_readiness"


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


def _ai_usage_dashboard_service() -> AiUsageDashboardService:
    root = Path(__file__).resolve().parents[2]
    return AiUsageDashboardService(
        _worker_usage_service(),
        ProviderUsageObservationStore(root),
    )


def _worker_auth_readiness_service() -> WorkerAuthReadinessService:
    return WorkerAuthReadinessService()


def _render_start_of_day_ai_readiness() -> None:
    st.subheader("Start-of-day AI readiness")
    if _AI_AUTH_SESSION_KEY not in st.session_state:
        try:
            with st.spinner("Checking AI logins without sending a model request..."):
                st.session_state[_AI_AUTH_SESSION_KEY] = (
                    _worker_auth_readiness_service().check_all()
                )
        except Exception:
            st.session_state[_AI_AUTH_SESSION_KEY] = ()
    results = st.session_state[_AI_AUTH_SESSION_KEY]
    if not results:
        st.warning("AI login readiness could not be checked safely.")
        return
    for result in results:
        if result.state == WorkerAuthState.AUTHENTICATED:
            st.success(f"{result.label}: authenticated.")
        elif result.state == WorkerAuthState.LOGIN_REQUIRED:
            st.warning(f"{result.label}: please log in before planning begins.")
            if result.login_instruction:
                st.write(result.login_instruction)
        else:
            st.warning(f"{result.label}: readiness could not be confirmed.")
            if result.login_instruction:
                st.write(result.login_instruction)
    st.caption(
        "These checks do not send a model prompt, collect credentials, or change "
        "the Kimi → Gemini → Codex routing order."
    )


def _platform_readiness_service() -> PlatformReadinessService:
    load_dotenv()
    root = Path(__file__).resolve().parents[2]
    database_url = os.getenv("DATABASE_URL", "")
    database_configured = bool(database_url)
    try:
        from advancore.services.database import test_database_connection
    except Exception:
        database_probe = None
    else:
        database_probe = test_database_connection
    readiness = ReadinessService(database_configured, database_probe)
    configured_directory = os.getenv("ADVANCORE_BACKUP_DIR")
    backup_directory = Path(configured_directory) if configured_directory else None

    def inventory():
        if not database_configured:
            raise RuntimeError("unavailable")
        return LocalBackupService(root, database_url, backup_directory).get_inventory()

    evidence = RecoveryEvidenceService(root)
    return PlatformReadinessService(readiness.get_summary, inventory, evidence.load)


def _render_platform_readiness() -> None:
    summary = _platform_readiness_service().get_summary()
    if summary.overall == ReadinessLevel.READY:
        st.success("Local platform protection checks are ready.")
    elif summary.overall == ReadinessLevel.ATTENTION:
        st.warning("Local platform protection needs attention.")
    else:
        st.error("One or more local platform checks are unavailable.")
    with st.expander("Platform readiness details"):
        for item in summary.items:
            state = item.level.value.title()
            st.write(f"{item.label} — {state}: {item.message}")


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


def _percent(value: float | None) -> str:
    return f"{value:g}%" if value is not None else "Unavailable"


def _render_usage_card(card: AiUsageCard) -> None:
    balance = (
        f"{card.remaining_percent:g}% remaining"
        if card.remaining_percent is not None
        else "Unavailable"
    )
    last_request = (
        f"{card.last_run_tokens:,} tokens"
        if card.last_run_tokens is not None
        else "Unavailable"
    )
    metrics = [
        (f"{card.label} role", card.role),
        (f"{card.label} balance", balance),
        (f"{card.label} weekly used", _percent(card.weekly_used_percent)),
        (f"{card.label} last request", last_request),
    ]
    if card.provider == "kimi":
        automation = (
            f"{card.automation_remaining_percent:g}% left to "
            f"{card.automation_limit_percent:g}% cap"
            if card.automation_remaining_percent is not None
            and card.automation_limit_percent is not None
            else "Unavailable"
        )
        runtime = (
            f"{card.runtime_seconds // 60} / {card.runtime_limit_seconds // 60} min"
            if card.runtime_seconds is not None
            and card.runtime_limit_seconds is not None
            else "Unavailable"
        )
        metrics.extend(
            [
                ("Kimi automation budget", automation),
                ("Kimi runtime this week", runtime),
            ]
        )
    else:
        metrics.append(
            (
                f"{card.label} authentication",
                "Verified" if card.authentication_verified else "Not verified",
            )
        )
    _metric_grid(metrics)

    if card.provider == "kimi" and card.automation_remaining_percent == 0:
        st.error("Kimi is paused at the owner-approved automation limit.")
    elif card.balance_state == BalanceState.CURRENT:
        st.success(f"{card.label} has a current provider percentage reading.")
    elif card.balance_state == BalanceState.OBSERVED_ONLY:
        st.info(
            f"{card.label} has measured request usage, but the remaining balance "
            "is not exposed by an approved feed."
        )
    elif card.balance_state == BalanceState.STALE:
        st.warning(f"{card.label} usage evidence is stale; refresh it before long work.")
    else:
        st.warning(f"{card.label} balance is unavailable. AdvanCore will not estimate it.")
    st.caption(f"Routing: {card.routing_status}. {card.message}")
    if card.checked_at:
        checked = card.checked_at.strftime("%Y-%m-%d %H:%M UTC")
        reset = (
            card.reset_at.strftime("%Y-%m-%d %H:%M UTC")
            if card.reset_at
            else "not supplied"
        )
        st.caption(
            f"Evidence checked: {checked}. Reset: {reset}. "
            f"Source: {card.source or 'unavailable'}."
        )


def _render_ai_workforce(workers: tuple[str, ...]) -> None:
    st.subheader("AI usage balance")
    st.caption(
        "Real provider readings only. A measured request is not the remaining quota, "
        "and dashboard visibility never grants worker authority."
    )
    if not workers:
        st.info("No AI worker cards are visible. Add them from Customize command center.")
        return
    visible_providers = {
        "kimi" if worker == "kimi-swarm" else worker for worker in workers
    }
    try:
        cards = _ai_usage_dashboard_service().get_cards()
    except Exception:
        st.error("AI usage evidence is unavailable. No provider balance was inferred.")
        return
    for card in cards:
        if card.provider in visible_providers:
            _render_usage_card(card)
    st.caption(
        "Kimi policy: maximum 20% provider-reported weekly use and 60 minutes "
        "of governed local runtime per provider week."
    )


def _active_fuel_window() -> int | None:
    selected = st.session_state.get(_FUEL_WINDOW_STATE_KEY, 7)
    if selected not in ALLOWED_FUEL_WINDOWS:
        selected = 7
        st.session_state[_FUEL_WINDOW_STATE_KEY] = selected
    return selected


def _render_fuel_visual_foundation() -> None:
    """Render the no-fabrication fuel chart and explicit voice confirmation UI."""
    st.subheader("Fuel trend console")
    st.caption(
        "Visual groundwork only. No operational fuel records are connected, so "
        "AdvanCore will not invent a trend."
    )
    render_fuel_status_component()

    active_window = _active_fuel_window()
    selected_window = st.selectbox(
        "Choose the fuel view",
        options=ALLOWED_FUEL_WINDOWS,
        index=ALLOWED_FUEL_WINDOWS.index(active_window),
        format_func=lambda value: _FUEL_WINDOW_LABELS[value],
        key="dashboard_fuel_window_choice",
    )
    recording = st.audio_input(
        "Record a short confirmation for the selected fuel view",
        key="dashboard_fuel_voice_confirmation",
        help=(
            "The recording stays in this Streamlit session. It is not transcribed, "
            "saved as a business record, or sent to an AI provider."
        ),
    )
    st.caption(
        "Recording alone changes nothing. Use the confirmation button below, or "
        "apply the same view without voice."
    )

    voice_column, manual_column = st.columns(2)
    voice_confirmed = voice_column.button(
        "Confirm selected view with recording",
        key="dashboard_fuel_voice_apply",
        disabled=recording is None,
    )
    manual_confirmed = manual_column.button(
        "Apply selected view without voice",
        key="dashboard_fuel_manual_apply",
    )

    if voice_confirmed and recording is not None:
        active_window = selected_window
        st.session_state[_FUEL_WINDOW_STATE_KEY] = selected_window
        st.success("Fuel view applied after your recorded confirmation.")
    elif manual_confirmed:
        active_window = selected_window
        st.session_state[_FUEL_WINDOW_STATE_KEY] = selected_window
        st.success("Fuel view applied without voice.")

    st.caption(f"Active view: {_FUEL_WINDOW_LABELS[active_window]}.")
    figure = build_fuel_trend_figure((), active_window)
    st.plotly_chart(
        figure,
        width="stretch",
        theme=None,
        key="dashboard_fuel_trend",
        config={
            "displaylogo": False,
            "scrollZoom": False,
            "modeBarButtonsToRemove": ["select2d", "lasso2d"],
        },
    )
    st.info(
        "Fuel data connection is intentionally pending a separate governed task."
    )


def render():
    st.header("Executive Command Center")
    st.caption("Real AdvanCore status only — no placeholder business figures.")
    refresh_requested = st.button(
        "Refresh dashboard",
        key="dashboard_refresh",
        help="Reload the latest available dashboard data and local status.",
    )
    if refresh_requested:
        st.session_state.pop(_AI_AUTH_SESSION_KEY, None)
        st.success("Dashboard refreshed with the latest available data.")
    _render_start_of_day_ai_readiness()
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
        _render_platform_readiness()
        _render_fuel_visual_foundation()

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
