"""Isolated tests for the read-only Activity Log page."""

from contextlib import contextmanager, nullcontext
from datetime import datetime

import pytest

from advancore.models import ActivityLog
from advancore.pages import activity_log
from advancore.services.activity_service import ActivityLogService


class FakeStreamlit:
    def __init__(self, selected_id=None, selected_filters=None):
        self.selected_id = selected_id
        self.selected_filters = dict(selected_filters or {})
        self.messages = []
        self.spinner_labels = []
        self.selectbox_options = {}

    def _record(self, kind, value):
        self.messages.append((kind, str(value)))

    def header(self, value): self._record("header", value)
    def subheader(self, value): self._record("subheader", value)
    def write(self, value): self._record("write", value)
    def info(self, value): self._record("info", value)
    def warning(self, value): self._record("warning", value)
    def error(self, value): self._record("error", value)
    def spinner(self, label):
        self.spinner_labels.append(label)
        return nullcontext()
    def selectbox(self, label, options, **_kwargs):
        self.selectbox_options[label] = list(options)
        if label == "Select an activity record" and self.selected_id is not None:
            return self.selected_id
        return self.selected_filters.get(label, options[0])
    def text_area(self, label, **kwargs):
        self._record(label, kwargs.get("value", ""))
        return kwargs.get("value", "")
    def text(self):
        return "\n".join(message for _, message in self.messages)


class FakeRepository:
    def __init__(self, activities=None):
        self.activities = list(activities or [])

    def list(self): return list(self.activities)
    def get_by_id(self, activity_id):
        return next(
            (activity for activity in self.activities if activity.id == activity_id),
            None,
        )


def _activity(
    activity_id,
    action="project_created",
    *,
    entity_type=None,
    entity_id=None,
    details=None,
    created_at=None,
):
    activity = ActivityLog(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
    )
    activity.id = activity_id
    if created_at is not None:
        activity.created_at = created_at
    return activity


def _install(monkeypatch, fake_st, service):
    @contextmanager
    def service_scope():
        yield service

    monkeypatch.setattr(activity_log, "st", fake_st)
    monkeypatch.setattr(activity_log, "_activity_service", service_scope)


def test_empty_state(monkeypatch):
    fake_st = FakeStreamlit()
    _install(monkeypatch, fake_st, ActivityLogService(FakeRepository()))
    activity_log.render()
    assert "No activity records are available." in fake_st.text()


def test_selected_record_shows_read_only_details_and_fallbacks(monkeypatch):
    records = [
        _activity(2, "archived"),
        _activity(
            1,
            "project_created",
            entity_type="project",
            entity_id="17",
            details="Created project Alpha",
            created_at=datetime(2026, 8, 23, 10, 30),
        ),
    ]
    fake_st = FakeStreamlit(selected_id=1)
    _install(monkeypatch, fake_st, ActivityLogService(FakeRepository(records)))
    activity_log.render()

    rendered = fake_st.text()
    assert "Loading activity..." in fake_st.spinner_labels
    assert "Action: project_created" in rendered
    assert "Entity type: project" in rendered
    assert "Entity ID: 17" in rendered
    assert "Created: 23 Aug 2026, 10:30 UTC" in rendered
    assert "Created project Alpha" in rendered

    fallback_st = FakeStreamlit(selected_id=2)
    _install(monkeypatch, fallback_st, ActivityLogService(FakeRepository(records)))
    activity_log.render()
    assert fallback_st.text().count("Not provided") == 3
    assert "Created: Not available" in fallback_st.text()


def test_missing_selected_record_is_safe(monkeypatch):
    class MissingService:
        def list_activities(self): return [_activity(1)]
        def get_activity(self, _activity_id): return None

    fake_st = FakeStreamlit()
    _install(monkeypatch, fake_st, MissingService())
    activity_log.render()
    assert "selected activity record could not be found" in fake_st.text()


def test_entity_and_action_filters_bound_the_selectable_records(monkeypatch):
    records = [
        _activity(3, "knowledge_archived", entity_type="knowledge"),
        _activity(2, "project_archived", entity_type="project"),
        _activity(1, "project_created", entity_type="project"),
    ]
    fake_st = FakeStreamlit(
        selected_filters={
            "Filter by entity type": "project",
            "Filter by action": "project_archived",
        }
    )
    _install(monkeypatch, fake_st, ActivityLogService(FakeRepository(records)))

    activity_log.render()

    assert fake_st.selectbox_options["Select an activity record"] == [2]
    assert "Action: project_archived" in fake_st.text()


def test_filters_have_clear_empty_state(monkeypatch):
    records = [_activity(1, "knowledge_created", entity_type="knowledge")]
    fake_st = FakeStreamlit(
        selected_filters={"Filter by entity type": "project"}
    )
    _install(monkeypatch, fake_st, ActivityLogService(FakeRepository(records)))

    activity_log.render()

    assert "No activity records match the selected filters." in fake_st.text()
    assert "Select an activity record" not in fake_st.selectbox_options


@pytest.mark.parametrize("operation", ["list", "get"])
def test_unexpected_failures_are_generic_and_do_not_leak(monkeypatch, operation):
    class FailingService:
        def list_activities(self):
            if operation == "list":
                raise RuntimeError("password SQL traceback")
            return [_activity(1)]
        def get_activity(self, _activity_id):
            raise RuntimeError("password SQL traceback")

    fake_st = FakeStreamlit()
    _install(monkeypatch, fake_st, FailingService())
    activity_log.render()
    assert "Activity records could not be loaded. Please try again." in fake_st.text()
    for secret in ("password", "SQL", "traceback"):
        assert secret not in fake_st.text()
