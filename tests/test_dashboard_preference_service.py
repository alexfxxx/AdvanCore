"""Tests for bounded command-center preference persistence."""

import json

import pytest

from advancore.models import SystemSetting
from advancore.services.dashboard_preference_service import (
    AVAILABLE_DASHBOARD_MODULES,
    AVAILABLE_WORKER_CARDS,
    DASHBOARD_SETTING_KEY,
    DEFAULT_DASHBOARD_PREFERENCES,
    DashboardPreferenceError,
    DashboardPreferenceService,
    DashboardPreferences,
)


class FakeRepository:
    def __init__(self, setting=None):
        self.setting = setting
        self.add_calls = 0
        self.save_calls = 0

    def get_by_key(self, key):
        assert key == DASHBOARD_SETTING_KEY
        return self.setting

    def add(self, setting):
        self.add_calls += 1
        setting.id = 1
        self.setting = setting
        return setting

    def save(self, setting):
        self.save_calls += 1
        self.setting = setting
        return setting


def test_missing_preference_loads_safe_defaults():
    assert DashboardPreferenceService(FakeRepository()).load() == (
        DEFAULT_DASHBOARD_PREFERENCES
    )


def test_save_and_reload_allowlisted_preferences():
    repository = FakeRepository()
    service = DashboardPreferenceService(repository)

    saved = service.save(["ai_workforce", "projects"], ["codex"])

    assert saved == DashboardPreferences(("ai_workforce", "projects"), ("codex",))
    assert repository.add_calls == 1
    assert repository.setting.description
    assert json.loads(repository.setting.value) == {
        "version": 1,
        "modules": ["ai_workforce", "projects"],
        "workers": ["codex"],
    }
    assert service.load() == saved

    updated = service.save([], [])
    assert updated == DashboardPreferences((), ())
    assert repository.save_calls == 1


@pytest.mark.parametrize(
    "value",
    [
        None,
        "not json",
        "[]",
        '{"version":2,"modules":[],"workers":[]}',
        '{"version":1,"modules":["unknown"],"workers":[]}',
        '{"version":1,"modules":[],"workers":["unknown-worker"]}',
        '{"version":1,"modules":[],"workers":[],"secret":"x"}',
    ],
)
def test_invalid_stored_value_fails_to_defaults(value):
    setting = SystemSetting(key=DASHBOARD_SETTING_KEY, value=value)
    assert DashboardPreferenceService(FakeRepository(setting)).load() == (
        DEFAULT_DASHBOARD_PREFERENCES
    )


@pytest.mark.parametrize(
    ("modules", "workers"),
    [
        (["unknown"], []),
        ([], ["unknown-worker"]),
        (["projects", "projects"], []),
        ([{"not": "hashable"}], []),
        ("projects", []),
        ([], "codex"),
    ],
)
def test_save_rejects_unknown_duplicate_or_unbounded_values(modules, workers):
    with pytest.raises(DashboardPreferenceError):
        DashboardPreferenceService(FakeRepository()).save(modules, workers)


def test_reset_restores_complete_catalogue():
    service = DashboardPreferenceService(FakeRepository())
    assert service.reset() == DashboardPreferences(
        AVAILABLE_DASHBOARD_MODULES, AVAILABLE_WORKER_CARDS
    )


def test_gemini_candidate_card_is_an_allowlisted_display_choice_only():
    service = DashboardPreferenceService(FakeRepository())
    saved = service.save(["ai_workforce"], ["gemini"])
    assert saved.workers == ("gemini",)
    assert service.load() == saved
