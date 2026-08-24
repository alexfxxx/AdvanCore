"""Shared dependency-free formatting for user-facing values."""

from datetime import datetime, timezone


def format_utc_timestamp(value: datetime | None) -> str:
    """Render one stored timestamp clearly without changing its value."""
    if not isinstance(value, datetime):
        return "Not available"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.strftime("%d %b %Y, %H:%M UTC")
