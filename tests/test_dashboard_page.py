"""Isolated tests for the customizable command-center page."""

from contextlib import contextmanager, nullcontext
from datetime import datetime, timedelta, timezone

from advancore.pages import dashboard
from advancore.services.dashboard_preference_service import (
    DEFAULT_DASHBOARD_PREFERENCES,
    DashboardPreferences,
)
from advancore.services.dashboard_service import DashboardSummary
from advancore.services.worker_usage_service import UsageState, UsageSummary


class FakeStreamlit:
    def __init__(self, selections=None, buttons=None):
        self.messages = []
        self.metrics = []
        self.spinner_labels = []
        self.selections = dict(selections or {})
        self.buttons = dict(buttons or {})
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
    def metric(self, label, value): self.metrics.append((label, value))
    def spinner(self, label):
        self.spinner_labels.append(label)
        return nullcontext()
    def expander(self, _label): return nullcontext()
    def columns(self, count): return [self for _ in range(count)]
    def multiselect(self, label, _options=None, default=None, **_kwargs):
        return self.selections.get(label, list(default or []))
    def button(self, label, **_kwargs): return self.buttons.get(label, False)
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


class FakeUsageService:
    def __init__(self, summary): self.summary = summary
    def get_summary(self, provider): return self.summary


def _usage_summary(state=UsageState.UNAVAILABLE, used=None, runtime=None):
    now = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
    return UsageSummary(
        provider="kimi",
        state=state,
        weekly_used_percent=used,
        weekly_percent_limit=20,
        runtime_seconds=runtime,
        runtime_limit_seconds=3600,
        checked_at=now if used is not None else None,
        reset_at=now + timedelta(days=4) if used is not None else None,
        source="owner-verified" if used is not None else None,
        message="test state",
    )


def _install(
    monkeypatch,
    fake_st,
    service,
    usage_summary=None,
    preference_service=None,
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
        "_worker_usage_service",
        lambda: FakeUsageService(usage_summary or _usage_summary()),
    )
    return preferences


def _summary():
    return DashboardSummary(4, 2, 1, 1, 5, 3, 2, 9, 4, 3, 2)


def test_dashboard_renders_real_bounded_default_modules(monkeypatch):
    fake_st = FakeStreamlit()
    _install(monkeypatch, fake_st, FakeService(_summary()))
    dashboard.render()

    assert "Loading overview..." in fake_st.spinner_labels
    assert fake_st.metrics == [
        ("Kimi role", "Primary worker"),
        ("Kimi weekly usage", "Unavailable"),
        ("Kimi policy limit", "20%"),
        ("Kimi runtime this week", "Unavailable"),
        ("Codex role", "Approved fallback"),
        ("Codex usage", "Not available in AdvanCore"),
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
    assert "no placeholder business figures" in fake_st.text()


def test_hidden_modules_and_workers_are_not_rendered(monkeypatch):
    preferences = DashboardPreferences(("ai_workforce", "projects"), ("codex",))
    fake_st = FakeStreamlit()
    _install(
        monkeypatch,
        fake_st,
        FakeService(_summary()),
        preference_service=FakePreferenceService(preferences),
    )

    dashboard.render()

    assert fake_st.metrics == [
        ("Codex role", "Approved fallback"),
        ("Codex usage", "Not available in AdvanCore"),
        ("Total projects", 4),
        ("Active projects", 2),
        ("Archived projects", 1),
        ("Other project statuses", 1),
    ]
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
    assert not fake_st.spinner_labels


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
    assert fake_st.metrics[:6] == [
        ("Kimi role", "Primary worker"),
        ("Kimi weekly usage", "Unavailable"),
        ("Kimi policy limit", "20%"),
        ("Kimi runtime this week", "Unavailable"),
        ("Codex role", "Approved fallback"),
        ("Codex usage", "Not available in AdvanCore"),
    ]


def test_dashboard_shows_allowed_and_paused_kimi_states(monkeypatch):
    for state, used, expected in (
        (UsageState.AVAILABLE, 10, "within the approved weekly budget"),
        (UsageState.PAUSED, 44, "paused by the weekly usage policy"),
    ):
        fake_st = FakeStreamlit()
        _install(
            monkeypatch,
            fake_st,
            FakeService(_summary()),
            _usage_summary(state, used, 120),
        )
        dashboard.render()
        assert ("Kimi weekly usage", f"{used}%") in fake_st.metrics
        assert ("Kimi runtime this week", "2 / 60 min") in fake_st.metrics
        assert expected in fake_st.text()


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
