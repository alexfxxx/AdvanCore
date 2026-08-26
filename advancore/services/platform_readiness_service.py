"""Bounded local platform readiness aggregation for operator-facing UI."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from advancore.services.local_backup_service import BackupInventory
from advancore.services.readiness_service import ReadinessSummary
from advancore.services.recovery_evidence_service import RecoveryEvidence


class ReadinessLevel(str, Enum):
    READY = "READY"
    ATTENTION = "ATTENTION"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class ReadinessItem:
    key: str
    label: str
    level: ReadinessLevel
    message: str


@dataclass(frozen=True)
class PlatformReadinessSummary:
    overall: ReadinessLevel
    items: tuple[ReadinessItem, ...]


class PlatformReadinessService:
    """Combine existing facts without exposing errors, paths, or credentials."""

    def __init__(
        self,
        database_summary: Callable[[], ReadinessSummary],
        backup_inventory: Callable[[], BackupInventory],
        recovery_evidence: Callable[[], RecoveryEvidence | None],
    ):
        self._database_summary = database_summary
        self._backup_inventory = backup_inventory
        self._recovery_evidence = recovery_evidence

    def _database_item(self) -> ReadinessItem:
        try:
            summary = self._database_summary()
        except Exception:
            return ReadinessItem(
                "database",
                "Local database",
                ReadinessLevel.UNAVAILABLE,
                "Database status could not be checked.",
            )
        if not summary.database_configured:
            return ReadinessItem(
                "database",
                "Local database",
                ReadinessLevel.UNAVAILABLE,
                "Database is not configured.",
            )
        if not summary.database_available:
            return ReadinessItem(
                "database",
                "Local database",
                ReadinessLevel.UNAVAILABLE,
                "Database is configured but unavailable.",
            )
        return ReadinessItem(
            "database",
            "Local database",
            ReadinessLevel.READY,
            "Database is available.",
        )

    def _protection_items(self) -> tuple[ReadinessItem, ReadinessItem]:
        try:
            inventory = self._backup_inventory()
        except Exception:
            unavailable = ReadinessItem(
                "backup",
                "Local backup",
                ReadinessLevel.UNAVAILABLE,
                "Backup status could not be checked.",
            )
            recovery = ReadinessItem(
                "recovery",
                "Recovery proof",
                ReadinessLevel.UNAVAILABLE,
                "Recovery status depends on a valid backup inventory.",
            )
            return unavailable, recovery

        if not inventory.records:
            backup = ReadinessItem(
                "backup",
                "Local backup",
                ReadinessLevel.ATTENTION,
                "No valid local backup is available.",
            )
        elif inventory.invalid_entries:
            backup = ReadinessItem(
                "backup",
                "Local backup",
                ReadinessLevel.ATTENTION,
                "A valid backup exists, with invalid entries needing attention.",
            )
        else:
            backup = ReadinessItem(
                "backup",
                "Local backup",
                ReadinessLevel.READY,
                "A valid local backup is available.",
            )

        try:
            evidence = self._recovery_evidence()
        except Exception:
            recovery = ReadinessItem(
                "recovery",
                "Recovery proof",
                ReadinessLevel.UNAVAILABLE,
                "Recovery evidence is invalid or unavailable.",
            )
            return backup, recovery
        if evidence is None:
            recovery = ReadinessItem(
                "recovery",
                "Recovery proof",
                ReadinessLevel.ATTENTION,
                "No disposable recovery evidence is available.",
            )
        elif not inventory.records or evidence.backup_id != inventory.records[0].backup_id:
            recovery = ReadinessItem(
                "recovery",
                "Recovery proof",
                ReadinessLevel.ATTENTION,
                "Recovery evidence does not match the latest valid backup.",
            )
        else:
            recovery = ReadinessItem(
                "recovery",
                "Recovery proof",
                ReadinessLevel.READY,
                "Latest backup passed a disposable recovery rehearsal.",
            )
        return backup, recovery

    def get_summary(self) -> PlatformReadinessSummary:
        items = (self._database_item(), *self._protection_items())
        levels = {item.level for item in items}
        if ReadinessLevel.UNAVAILABLE in levels:
            overall = ReadinessLevel.UNAVAILABLE
        elif ReadinessLevel.ATTENTION in levels:
            overall = ReadinessLevel.ATTENTION
        else:
            overall = ReadinessLevel.READY
        return PlatformReadinessSummary(overall=overall, items=items)
