"""Isolated tests for the usable Dashboard overview page."""

from contextlib import contextmanager, nullcontext

from advancore.pages import dashboard
from advancore.services.dashboard_service import DashboardSummary


class FakeStreamlit:
    def __init__(self):
        self.messages = []
        self.metrics = []
        self.spinner_labels = []

    def _record(self, kind, value): self.messages.append((kind, str(value)))
    def subheader(self, value): self._record("subheader", value)
    def success(self, value): self._record("success", value)
    def error(self, value): self._record("error", value)
    def caption(self, value): self._record("caption", value)
    def metric(self, label, value): self.metrics.append((label, value))
    def spinner(self, label):
        self.spinner_labels.append(label)
        return nullcontext()
    def text(self): return "\n".join(message for _, message in self.messages)


class FakeService:
    def __init__(self, summary=None, error=None):
        self.summary = summary
        self.error = error

    def get_summary(self):
        if self.error:
            raise self.error
        return self.summary


def _install(monkeypatch, fake_st, service):
    @contextmanager
    def service_scope():
        yield service
    monkeypatch.setattr(dashboard, "st", fake_st)
    monkeypatch.setattr(dashboard, "_dashboard_service", service_scope)


def test_dashboard_renders_all_bounded_metrics(monkeypatch):
    fake_st = FakeStreamlit()
    summary = DashboardSummary(4, 2, 1, 1, 5, 3, 2)
    _install(monkeypatch, fake_st, FakeService(summary))
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
    ]
    assert "Core application shell operational." in fake_st.text()
    assert "Database connected." in fake_st.text()


def test_dashboard_empty_state_renders_zero_metrics(monkeypatch):
    fake_st = FakeStreamlit()
    _install(monkeypatch, fake_st, FakeService(DashboardSummary(0, 0, 0, 0, 0, 0, 0)))
    dashboard.render()
    assert len(fake_st.metrics) == 7
    assert all(value == 0 for _, value in fake_st.metrics)


def test_dashboard_failure_is_generic_and_renders_no_metrics(monkeypatch):
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
    assert "Database connected." not in fake_st.text()
