"""Isolated tests for the read-only Settings readiness page."""

from contextlib import nullcontext

import pytest

from advancore.pages import settings
from advancore.services.readiness_service import ReadinessService


class FakeStreamlit:
    def __init__(self):
        self.messages = []
        self.spinner_labels = []

    def _record(self, kind, value): self.messages.append((kind, str(value)))
    def header(self, value): self._record("header", value)
    def subheader(self, value): self._record("subheader", value)
    def write(self, value): self._record("write", value)
    def warning(self, value): self._record("warning", value)
    def success(self, value): self._record("success", value)
    def error(self, value): self._record("error", value)
    def caption(self, value): self._record("caption", value)
    def spinner(self, label):
        self.spinner_labels.append(label)
        return nullcontext()
    def text(self): return "\n".join(message for _, message in self.messages)


@pytest.mark.parametrize(
    ("service", "expected_kind", "expected_text"),
    [
        (ReadinessService(False), "warning", "Database is not configured"),
        (
            ReadinessService(True, lambda: True),
            "success",
            "configured and available",
        ),
        (
            ReadinessService(True, lambda: False),
            "error",
            "configured but unavailable",
        ),
    ],
)
def test_settings_renders_safe_readiness_states(
    monkeypatch, service, expected_kind, expected_text
):
    fake_st = FakeStreamlit()
    monkeypatch.setattr(settings, "st", fake_st)
    monkeypatch.setattr(settings, "_readiness_service", lambda: service)

    settings.render()

    assert "Name: AdvanCore" in fake_st.text()
    assert "Version: 0.1" in fake_st.text()
    assert "Checking local readiness..." in fake_st.spinner_labels
    assert any(
        kind == expected_kind and expected_text in message
        for kind, message in fake_st.messages
    )


def test_probe_exception_is_safe_and_does_not_leak(monkeypatch):
    def failing_probe():
        raise RuntimeError("postgres://secret password SQL traceback")

    fake_st = FakeStreamlit()
    monkeypatch.setattr(settings, "st", fake_st)
    monkeypatch.setattr(
        settings, "_readiness_service", lambda: ReadinessService(True, failing_probe)
    )
    settings.render()

    assert "configured but unavailable" in fake_st.text()
    for sensitive in ("postgres://", "secret", "password", "SQL", "traceback"):
        assert sensitive not in fake_st.text()
