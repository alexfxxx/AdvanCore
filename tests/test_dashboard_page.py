"""Isolated tests for the customizable command-center page."""

from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone

from advancore.pages import dashboard
from advancore.services.dashboard_preference_service import (
    DEFAULT_DASHBOARD_PREFERENCES,
    DashboardPreferences,
)
from advancore.services.dashboard_service import DashboardSummary
from advancore.services.worker_auth_readiness_service import (
    WorkerAuthReadiness,
    WorkerAuthState,
)
from advancore.services.worker_routing_evidence_service import (
    WorkerHandoffNotification,
    WorkerSwitchingStatus,
)
from advancore.services.platform_readiness_service import (
    PlatformReadinessSummary,
    ReadinessItem,
    ReadinessLevel,
)


class FakeStreamlit:
    def __init__(self, selections=None, buttons=None):
        self.messages = []
        self.metrics = []
        self.spinner_labels = []
        self.selections = dict(selections or {})
        self.buttons = dict(buttons or {})
        self.button_labels = []
        self.rerun_calls = 0
        self.session_state = {}

    def _record(self, kind, value):
        self.messages.append((kind, str(value)))

    def header(self, value): self._record("header", value)
    def subheader(self, value): self._record("subheader", value)
    def success(self, value): self._record("success", value)
    def warning(self, value): self._record("warning", value)
    def error(self, value): self._record("error", value)
    def info(self, value): self._record("info", value)
    def caption(self, value): self._record("caption", value)
    def write(self, value): self._record("write", value)
    def metric(self, label, value): self.metrics.append((label, value))
    def spinner(self, label):
        self.spinner_labels.append(label)
        return nullcontext()
    def expander(self, _label): return nullcontext()
    def columns(self, count): return [self for _ in range(count)]
    def multiselect(self, label, _options=None, default=None, **_kwargs):
        return self.selections.get(label, list(default or []))
    def button(self, label, **_kwargs):
        self.button_labels.append(label)
        return self.buttons.get(label, False)
    def rerun(self): self.rerun_calls += 1
    def text(self): return "\n".join(message for _, message in self.messages)


class FakeService:
    def __init__(self, summary=None, error=None):
        self.summary = summary
        self.error = error

    def get_summary(self):
        if self.error:
            raise self.error
        return self.summary


class FakePreferenceService:
    def __init__(self, preferences=DEFAULT_DASHBOARD_PREFERENCES, error=None):
        self.preferences = preferences
        self.error = error
        self.save_calls = []
        self.reset_calls = 0

    def load(self):
        if self.error:
            raise self.error
        return self.preferences

    def save(self, modules, workers):
        if self.error:
            raise self.error
        self.save_calls.append((tuple(modules), tuple(workers)))
        return DashboardPreferences(tuple(modules), tuple(workers))

    def reset(self):
        if self.error:
            raise self.error
        self.reset_calls += 1
        return DEFAULT_DASHBOARD_PREFERENCES


class FakeSwitchingStatusService:
    def __init__(self, status):
        self.status = status

    def get_status(self):
        return self.status


class FakeAuthService:
    def __init__(self, results):
        self.results = results
        self.calls = 0

    def check_all(self):
        self.calls += 1
        return self.results


def _auth_results(state=WorkerAuthState.AUTHENTICATED):
    return tuple(
        WorkerAuthReadiness(
            worker,
            label,
            state,
            "bounded",
            None if state == WorkerAuthState.AUTHENTICATED else f"Log in to {label}",
        )
        for worker, label in (("kimi", "Kimi"), ("gemini", "Gemini"), ("codex", "Codex"))
    )


def _install(
    monkeypatch,
    fake_st,
    service,
    switching_status=None,
    preference_service=None,
    auth_service=None,
):
    preferences = preference_service or FakePreferenceService()

    @contextmanager
    def service_scope():
        yield service

    @contextmanager
    def preference_scope():
        yield preferences

    monkeypatch.setattr(dashboard, "st", fake_st)
    monkeypatch.setattr(dashboard, "_dashboard_service", service_scope)
    monkeypatch.setattr(dashboard, "_dashboard_preference_service", preference_scope)
    monkeypatch.setattr(
        dashboard,
        "_worker_switching_status_service",
        lambda: FakeSwitchingStatusService(
            switching_status or WorkerSwitchingStatus(None, ())
        ),
    )
    monkeypatch.setattr(
        dashboard,
        "_worker_auth_readiness_service",
        lambda: auth_service or FakeAuthService(_auth_results()),
    )
    monkeypatch.setattr(dashboard, "_render_fuel_visual_foundation", lambda *_args: None)
    monkeypatch.setattr(dashboard, "_load_fuel_intelligence", lambda: None)
    monkeypatch.setattr(dashboard, "_render_platform_readiness", lambda: None)
    return preferences


def _summary():
    return DashboardSummary(4, 2, 1, 1, 5, 3, 2, 9, 4, 3, 2)


def test_dashboard_renders_real_bounded_default_modules(monkeypatch):
    fake_st = FakeStreamlit()
    _install(monkeypatch, fake_st, FakeService(_summary()))
    dashboard.render()

    assert "Loading overview..." in fake_st.spinner_labels
    assert fake_st.metrics == [
        ("Total projects", 4),
        ("Active projects", 2),
        ("Archived projects", 1),
        ("Other project statuses", 1),
        ("Total knowledge items", 5),
        ("Draft knowledge items", 3),
        ("Other knowledge statuses", 2),
        ("Total activity events", 9),
        ("Project activity events", 4),
        ("Knowledge activity events", 3),
        ("Other activity events", 2),
    ]
    assert "Core application shell operational." in fake_st.text()
    assert "Database connected." in fake_st.text()
    assert "Automatic worker status" in fake_st.text()
    assert "No current or selected implementation worker is known" in fake_st.text()
    assert "no placeholder business figures" in fake_st.text()
    assert "Refresh dashboard" in fake_st.button_labels


def test_refresh_control_confirms_fresh_page_run_and_renders_summary(monkeypatch):
    fake_st = FakeStreamlit(buttons={"Refresh dashboard": True})
    _install(monkeypatch, fake_st, FakeService(_summary()))

    dashboard.render()

    assert "Dashboard refreshed with the latest available data." in fake_st.text()
    assert ("Total projects", 4) in fake_st.metrics
    assert "Automatic worker status" in fake_st.text()


def test_hidden_modules_and_workers_are_not_rendered(monkeypatch):
    preferences = DashboardPreferences(("ai_workforce", "projects"), ("codex",))
    fake_st = FakeStreamlit()
    _install(
        monkeypatch,
        fake_st,
        FakeService(_summary()),
        switching_status=WorkerSwitchingStatus("codex", ()),
        preference_service=FakePreferenceService(preferences),
    )

    dashboard.render()

    assert fake_st.metrics == [
        ("Total projects", 4),
        ("Active projects", 2),
        ("Archived projects", 1),
        ("Other project statuses", 1),
    ]
    assert "Most recently selected worker: Codex" in fake_st.text()
    assert "Knowledge overview" not in fake_st.text()
    assert "Activity overview" not in fake_st.text()


def test_no_visible_modules_has_recovery_message_and_skips_data_load(monkeypatch):
    fake_st = FakeStreamlit()
    _install(
        monkeypatch,
        fake_st,
        FakeService(error=AssertionError("must not load")),
        preference_service=FakePreferenceService(DashboardPreferences((), ())),
    )
    dashboard.render()
    assert "No dashboard functions are visible" in fake_st.text()
    assert fake_st.spinner_labels == [
        "Checking AI logins without sending a model request..."
    ]


def test_save_and_reset_controls_use_bounded_preference_service(monkeypatch):
    selections = {
        "Visible dashboard functions": ["projects", "activity"],
        "Visible AI worker cards": ["codex"],
    }
    save_st = FakeStreamlit(
        selections=selections, buttons={"Save dashboard": True}
    )
    preference_service = FakePreferenceService()
    _install(
        monkeypatch,
        save_st,
        FakeService(_summary()),
        preference_service=preference_service,
    )
    dashboard.render()
    assert preference_service.save_calls == [
        (("projects", "activity"), ("codex",))
    ]
    assert save_st.rerun_calls == 1

    reset_st = FakeStreamlit(buttons={"Restore default dashboard": True})
    reset_service = FakePreferenceService()
    _install(
        monkeypatch,
        reset_st,
        FakeService(_summary()),
        preference_service=reset_service,
    )
    dashboard.render()
    assert reset_service.reset_calls == 1
    assert reset_st.rerun_calls == 1


def test_dashboard_failure_is_generic_and_does_not_leak(monkeypatch):
    fake_st = FakeStreamlit()
    _install(
        monkeypatch,
        fake_st,
        FakeService(error=RuntimeError("postgres://secret password SQL traceback")),
    )
    dashboard.render()
    assert "Operational overview is unavailable" in fake_st.text()
    for secret in ("secret", "password", "SQL", "traceback"):
        assert secret not in fake_st.text()
    assert fake_st.metrics == []


def test_dashboard_removes_usage_details_and_shows_safe_switches(monkeypatch):
    occurred_at = datetime(2026, 8, 26, 13, 0, tzinfo=timezone.utc)
    status = WorkerSwitchingStatus(
        "codex",
        (
            WorkerHandoffNotification(
                "gemini", "codex", "authentication", occurred_at
            ),
            WorkerHandoffNotification(
                "kimi-swarm", "gemini", "limit_or_quota", occurred_at
            ),
        ),
    )
    fake_st = FakeStreamlit()
    _install(
        monkeypatch,
        fake_st,
        FakeService(_summary()),
        switching_status=status,
    )

    dashboard.render()

    rendered = fake_st.text()
    for removed in (
        "AI usage balance",
        "balance",
        "weekly used",
        "last request",
        "token",
        "usage evidence",
    ):
        assert removed.lower() not in rendered.lower()
    assert "Most recently selected worker: Codex" in rendered
    assert "Gemini → Codex: authentication was unavailable" in rendered
    assert "Kimi / Kimi-Swarm → Gemini: a provider limit or quota" in rendered


def test_start_of_day_auth_check_runs_once_per_session_and_requests_login(monkeypatch):
    fake_st = FakeStreamlit()
    auth = FakeAuthService(_auth_results(WorkerAuthState.LOGIN_REQUIRED))
    _install(
        monkeypatch,
        fake_st,
        FakeService(_summary()),
        auth_service=auth,
    )

    dashboard.render()
    dashboard.render()

    assert auth.calls == 1
    assert "Kimi: please log in before planning begins" in fake_st.text()
    assert "Log in to Gemini" in fake_st.text()


def test_dashboard_refresh_rechecks_ai_authentication(monkeypatch):
    fake_st = FakeStreamlit(buttons={"Refresh dashboard": True})
    auth = FakeAuthService(_auth_results())
    _install(
        monkeypatch,
        fake_st,
        FakeService(_summary()),
        auth_service=auth,
    )
    fake_st.session_state[dashboard._AI_AUTH_SESSION_KEY] = _auth_results()

    dashboard.render()

    assert auth.calls == 1
    assert "Kimi: authenticated" in fake_st.text()


def test_preference_load_failure_shows_defaults_without_leak(monkeypatch):
    fake_st = FakeStreamlit()
    _install(
        monkeypatch,
        fake_st,
        FakeService(_summary()),
        preference_service=FakePreferenceService(
            error=RuntimeError("database password traceback")
        ),
    )
    dashboard.render()
    assert "safe default layout" in fake_st.text()
    for secret in ("password", "traceback"):
        assert secret not in fake_st.text()


def test_platform_readiness_renders_bounded_states(monkeypatch):
    fake_st = FakeStreamlit()
    summary = PlatformReadinessSummary(
        ReadinessLevel.ATTENTION,
        (
            ReadinessItem(
                "database", "Local database", ReadinessLevel.READY, "Database is available."
            ),
            ReadinessItem(
                "backup",
                "Local backup",
                ReadinessLevel.ATTENTION,
                "No valid local backup is available.",
            ),
            ReadinessItem(
                "recovery",
                "Recovery proof",
                ReadinessLevel.ATTENTION,
                "No disposable recovery evidence is available.",
            ),
        ),
    )
    monkeypatch.setattr(dashboard, "st", fake_st)
    monkeypatch.setattr(
        dashboard, "_platform_readiness_service", lambda: FakeService(summary)
    )

    dashboard._render_platform_readiness()

    assert "platform protection needs attention" in fake_st.text()
    assert "Local database — Ready" in fake_st.text()
    assert "No valid local backup" in fake_st.text()
