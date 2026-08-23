"""Safe, read-only application readiness reporting."""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class ReadinessSummary:
    """Non-sensitive readiness facts safe to present in the local UI."""

    database_configured: bool
    database_available: bool


class ReadinessService:
    """Evaluate database readiness without exposing configuration or failures."""

    def __init__(
        self,
        database_configured: bool,
        database_probe: Callable[[], bool] | None = None,
    ):
        self._database_configured = database_configured
        self._database_probe = database_probe

    def get_summary(self) -> ReadinessSummary:
        if not self._database_configured:
            return ReadinessSummary(False, False)

        try:
            available = bool(self._database_probe and self._database_probe())
        except Exception:
            available = False

        return ReadinessSummary(True, available)
