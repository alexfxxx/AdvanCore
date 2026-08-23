"""Tests for safe local readiness reporting."""

from advancore.services.readiness_service import ReadinessService, ReadinessSummary


def test_not_configured_does_not_call_probe():
    calls = []

    def probe():
        calls.append(True)
        return True

    assert ReadinessService(False, probe).get_summary() == ReadinessSummary(False, False)
    assert calls == []


def test_configured_and_available():
    assert ReadinessService(True, lambda: True).get_summary() == ReadinessSummary(
        True, True
    )


def test_configured_but_failed_or_missing_probe_is_unavailable():
    assert ReadinessService(True, lambda: False).get_summary() == ReadinessSummary(
        True, False
    )
    assert ReadinessService(True).get_summary() == ReadinessSummary(True, False)


def test_probe_exception_fails_closed_without_returning_details():
    def probe():
        raise RuntimeError("postgres://secret password SQL traceback")

    summary = ReadinessService(True, probe).get_summary()
    assert summary == ReadinessSummary(True, False)
    assert "secret" not in repr(summary)
    assert "password" not in repr(summary)
