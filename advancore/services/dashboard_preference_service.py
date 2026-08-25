"""Bounded persistence for the single-owner command-center layout."""

from __future__ import annotations

from dataclasses import dataclass
import json

from advancore.models import SystemSetting
from advancore.repositories import SystemSettingRepository


DASHBOARD_SETTING_KEY = "dashboard.command_center.v1"
DASHBOARD_SETTING_DESCRIPTION = (
    "Owner-selected visible command-center modules and worker cards."
)
AVAILABLE_DASHBOARD_MODULES = (
    "platform",
    "ai_workforce",
    "projects",
    "knowledge",
    "activity",
)
AVAILABLE_WORKER_CARDS = ("kimi-swarm", "codex", "gemini")


class DashboardPreferenceError(ValueError):
    """Raised when a proposed preference exceeds the approved catalogue."""


@dataclass(frozen=True)
class DashboardPreferences:
    modules: tuple[str, ...]
    workers: tuple[str, ...]


DEFAULT_DASHBOARD_PREFERENCES = DashboardPreferences(
    modules=AVAILABLE_DASHBOARD_MODULES,
    workers=AVAILABLE_WORKER_CARDS,
)


def _validated_selection(
    values, available: tuple[str, ...], field_name: str
) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        raise DashboardPreferenceError(f"Dashboard {field_name} are invalid.")
    selected = tuple(values)
    if any(not isinstance(value, str) for value in selected):
        raise DashboardPreferenceError(f"Dashboard {field_name} are invalid.")
    if len(selected) > len(available) or len(set(selected)) != len(selected):
        raise DashboardPreferenceError(f"Dashboard {field_name} are invalid.")
    if any(value not in available for value in selected):
        raise DashboardPreferenceError(f"Dashboard {field_name} are invalid.")
    return selected


class DashboardPreferenceService:
    """Read and save one allowlisted dashboard preference record."""

    def __init__(self, repository: SystemSettingRepository):
        self._repo = repository

    def load(self) -> DashboardPreferences:
        setting = self._repo.get_by_key(DASHBOARD_SETTING_KEY)
        if setting is None or setting.value is None:
            return DEFAULT_DASHBOARD_PREFERENCES
        try:
            payload = json.loads(setting.value)
            if not isinstance(payload, dict) or set(payload) != {
                "version",
                "modules",
                "workers",
            }:
                raise DashboardPreferenceError("Dashboard preference is invalid.")
            if type(payload["version"]) is not int or payload["version"] != 1:
                raise DashboardPreferenceError("Dashboard preference is invalid.")
            return DashboardPreferences(
                modules=_validated_selection(
                    payload["modules"], AVAILABLE_DASHBOARD_MODULES, "modules"
                ),
                workers=_validated_selection(
                    payload["workers"], AVAILABLE_WORKER_CARDS, "worker cards"
                ),
            )
        except (
            json.JSONDecodeError,
            TypeError,
            RecursionError,
            DashboardPreferenceError,
        ):
            return DEFAULT_DASHBOARD_PREFERENCES

    def save(self, modules, workers) -> DashboardPreferences:
        preferences = DashboardPreferences(
            modules=_validated_selection(
                modules, AVAILABLE_DASHBOARD_MODULES, "modules"
            ),
            workers=_validated_selection(
                workers, AVAILABLE_WORKER_CARDS, "worker cards"
            ),
        )
        value = json.dumps(
            {
                "version": 1,
                "modules": list(preferences.modules),
                "workers": list(preferences.workers),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        setting = self._repo.get_by_key(DASHBOARD_SETTING_KEY)
        if setting is None:
            self._repo.add(
                SystemSetting(
                    key=DASHBOARD_SETTING_KEY,
                    value=value,
                    description=DASHBOARD_SETTING_DESCRIPTION,
                )
            )
        else:
            setting.value = value
            setting.description = DASHBOARD_SETTING_DESCRIPTION
            self._repo.save(setting)
        return preferences

    def reset(self) -> DashboardPreferences:
        return self.save(
            DEFAULT_DASHBOARD_PREFERENCES.modules,
            DEFAULT_DASHBOARD_PREFERENCES.workers,
        )
