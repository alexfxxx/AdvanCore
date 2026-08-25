"""Isolated tests for the read-only Settings readiness page."""

from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path

import pytest

from advancore.pages import settings
from advancore.services.local_backup_service import (
    BackupInventory,
    BackupRecord,
    LocalBackupError,
)
from advancore.services.readiness_service import ReadinessService


class FakeStreamlit:
    def __init__(self, buttons=None):
        self.messages = []
        self.spinner_labels = []
        self.buttons = dict(buttons or {})
        self.button_calls = []

    def _record(self, kind, value): self.messages.append((kind, str(value)))
    def header(self, value): self._record("header", value)
    def subheader(self, value): self._record("subheader", value)
    def write(self, value): self._record("write", value)
    def warning(self, value): self._record("warning", value)
    def success(self, value): self._record("success", value)
    def error(self, value): self._record("error", value)
    def info(self, value): self._record("info", value)
    def caption(self, value): self._record("caption", value)
    def columns(self, count): return [self for _ in range(count)]
    def button(self, label, **kwargs):
        self.button_calls.append((label, kwargs))
        if kwargs.get("disabled"):
            return False
        return self.buttons.get(label, False)
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
    monkeypatch.setattr(settings, "_render_local_backups", lambda: None)

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
    monkeypatch.setattr(settings, "_render_local_backups", lambda: None)
    settings.render()

    assert "configured but unavailable" in fake_st.text()
    for sensitive in ("postgres://", "secret", "password", "SQL", "traceback"):
        assert sensitive not in fake_st.text()


def _backup_record(tmp_path):
    return BackupRecord(
        backup_id="advancore-20260826T010203Z-1a2b3c4d",
        created_at=datetime(2026, 8, 26, 1, 2, 3, tzinfo=timezone.utc),
        size_bytes=1536,
        sha256="a" * 64,
        archive_path=Path(tmp_path) / "backup.dump",
        manifest_path=Path(tmp_path) / "backup.json",
    )


class FakeBackupService:
    def __init__(self, record, *, inventory=None, error=None):
        self.record = record
        self.inventory = inventory or BackupInventory((record,), 0, 1536)
        self.error = error
        self.calls = []

    def get_inventory(self):
        self.calls.append("inventory")
        if self.error == "inventory":
            raise LocalBackupError("postgres://secret inventory trace")
        return self.inventory

    def create_backup(self):
        self.calls.append("create")
        if self.error == "create":
            raise LocalBackupError("postgres://secret create trace")
        return self.record

    def verify_latest(self):
        self.calls.append("verify")
        if self.error == "verify":
            raise LocalBackupError("postgres://secret verify trace")
        return self.record


def test_backup_settings_show_inventory_and_create_verified_backup(
    monkeypatch, tmp_path
):
    label = "Create and verify local backup"
    fake_st = FakeStreamlit(buttons={label: True})
    service = FakeBackupService(_backup_record(tmp_path))
    monkeypatch.setattr(settings, "st", fake_st)
    monkeypatch.setattr(settings, "_local_backup_service", lambda: service)

    settings._render_local_backups()

    assert service.calls == ["inventory", "create"]
    assert "Latest valid local backup: 2026-08-26 01:02 UTC" in fake_st.text()
    assert "Local backup storage used: 1.5 KB" in fake_st.text()
    assert "Local backup created and verified" in fake_st.text()
    assert "Creating and verifying local backup..." in fake_st.spinner_labels


def test_backup_settings_verify_latest_and_disable_when_empty(monkeypatch, tmp_path):
    verify_label = "Verify latest local backup"
    fake_st = FakeStreamlit(buttons={verify_label: True})
    service = FakeBackupService(_backup_record(tmp_path))
    monkeypatch.setattr(settings, "st", fake_st)
    monkeypatch.setattr(settings, "_local_backup_service", lambda: service)

    settings._render_local_backups()

    assert service.calls == ["inventory", "verify"]
    assert "Latest local backup verified" in fake_st.text()

    empty_st = FakeStreamlit(buttons={verify_label: True})
    empty_service = FakeBackupService(
        _backup_record(tmp_path),
        inventory=BackupInventory((), 0, 0),
    )
    monkeypatch.setattr(settings, "st", empty_st)
    monkeypatch.setattr(settings, "_local_backup_service", lambda: empty_service)
    settings._render_local_backups()
    assert empty_service.calls == ["inventory"]
    verify_call = next(
        kwargs for label, kwargs in empty_st.button_calls if label == verify_label
    )
    assert verify_call["disabled"] is True


def test_backup_settings_invalid_entries_and_failures_are_secret_safe(
    monkeypatch, tmp_path
):
    label = "Create and verify local backup"
    fake_st = FakeStreamlit(buttons={label: True})
    service = FakeBackupService(
        _backup_record(tmp_path),
        inventory=BackupInventory((_backup_record(tmp_path),), 2, 1536),
        error="create",
    )
    monkeypatch.setattr(settings, "st", fake_st)
    monkeypatch.setattr(settings, "_local_backup_service", lambda: service)

    settings._render_local_backups()

    assert "incomplete or invalid" in fake_st.text()
    assert "No partial backup was kept" in fake_st.text()
    for sensitive in ("postgres://", "secret", "trace"):
        assert sensitive not in fake_st.text()


def test_backup_settings_missing_or_bad_configuration_is_bounded(monkeypatch):
    missing_st = FakeStreamlit()
    monkeypatch.setattr(settings, "st", missing_st)
    monkeypatch.setattr(settings, "_local_backup_service", lambda: None)
    settings._render_local_backups()
    assert "Configure the local database" in missing_st.text()

    bad_st = FakeStreamlit()
    monkeypatch.setattr(settings, "st", bad_st)

    def fail_configuration():
        raise LocalBackupError("postgres://secret configuration trace")

    monkeypatch.setattr(settings, "_local_backup_service", fail_configuration)
    settings._render_local_backups()
    assert "configuration is unavailable" in bad_st.text()
    for sensitive in ("postgres://", "secret", "trace"):
        assert sensitive not in bad_st.text()
