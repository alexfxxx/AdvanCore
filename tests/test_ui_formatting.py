"""Tests for shared user-facing value formatting."""

from datetime import datetime, timedelta, timezone

from advancore.ui.formatting import format_utc_timestamp


def test_format_utc_timestamp_marks_naive_storage_value_as_utc():
    assert format_utc_timestamp(datetime(2026, 8, 23, 10, 30)) == (
        "23 Aug 2026, 10:30 UTC"
    )


def test_format_utc_timestamp_converts_aware_value_to_utc():
    singapore = timezone(timedelta(hours=8))
    assert format_utc_timestamp(
        datetime(2026, 8, 23, 18, 30, tzinfo=singapore)
    ) == "23 Aug 2026, 10:30 UTC"


def test_format_utc_timestamp_has_safe_missing_fallback():
    assert format_utc_timestamp(None) == "Not available"
