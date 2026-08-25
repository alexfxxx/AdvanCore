"""Isolated tests for the usable owner-governed Knowledge Hub page."""

from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone

import pytest

from advancore.models import KnowledgeItem
from advancore.pages import knowledge_hub
from advancore.services.knowledge_service import (
    KnowledgeReadOnlyError,
    KnowledgeService,
)


class FakeStreamlit:
    def __init__(
        self, *, submitted=False, title="", content="", selected_id=None,
        submissions=None, inputs=None, confirmed=False, session_state=None,
    ):
        self.submitted = submitted
        self.title = title
        self.content = content
        self.selected_id = selected_id
        self.messages = []
        self.spinner_labels = []
        self.widget_labels = []
        self.submissions = submissions or {}
        self.inputs = inputs or {}
        self.confirmed = confirmed
        self.session_state = session_state if session_state is not None else {}
        self.rerun_calls = 0
        self._form_key = None
        self.selectbox_labels = []
        self.selected_option = None

    def _record(self, kind, value): self.messages.append((kind, str(value)))
    def header(self, value): self._record("header", value)
    def subheader(self, value): self._record("subheader", value)
    def write(self, value): self._record("write", value)
    def info(self, value): self._record("info", value)
    def warning(self, value): self._record("warning", value)
    def error(self, value): self._record("error", value)
    def success(self, value): self._record("success", value)
    @contextmanager
    def form(self, key):
        previous = self._form_key
        self._form_key = key
        try:
            yield
        finally:
            self._form_key = previous
    def text_input(self, label, **kwargs):
        self.widget_labels.append(label)
        if label in self.inputs:
            return self.inputs[label]
        if label == "Title":
            return self.title
        return kwargs.get("value", "")
    def text_area(self, label, **kwargs):
        self.widget_labels.append(label)
        if kwargs.get("disabled"):
            key = kwargs.get("key")
            rendered_value = self.session_state.setdefault(
                key, kwargs.get("value", "")
            )
            self._record("detail_content", rendered_value)
            return rendered_value
        if label in self.inputs:
            return self.inputs[label]
        if label == "Content":
            return self.content
        return kwargs.get("value", "")
    def form_submit_button(self, label, **_kwargs):
        self.widget_labels.append(label)
        if self._form_key in self.submissions:
            return self.submissions[self._form_key]
        return self.submitted if self._form_key == "create_knowledge_draft" else False
    def checkbox(self, label, **_kwargs):
        self.widget_labels.append(label)
        return self.confirmed
    def spinner(self, label):
        self.spinner_labels.append(label)
        return nullcontext()
    def selectbox(self, _label, options, **kwargs):
        formatter = kwargs.get("format_func", str)
        self.selectbox_labels = [formatter(option) for option in options]
        key = kwargs.get("key")
        if self.selected_id is not None:
            selected = self.selected_id
        elif key in self.session_state:
            selected = self.session_state[key]
        else:
            selected = options[kwargs.get("index", 0)]
        self.session_state[key] = selected
        self.selected_option = formatter(selected)
        return selected
    def rerun(self): self.rerun_calls += 1
    def text(self): return "\n".join(message for _, message in self.messages)


class FakeRepository:
    def __init__(self, items=None):
        self.items = list(items or [])
        self.add_calls = 0
        self.save_calls = 0
        self.save_error = None

    def add(self, item):
        self.add_calls += 1
        item.id = max((saved.id for saved in self.items), default=0) + 1
        self.items.append(item)
        return item

    def list(self): return list(self.items)
    def get_by_id(self, item_id):
        return next((item for item in self.items if item.id == item_id), None)
    def get_active_replacement_for(self, source_item_id):
        return next(
            (
                item
                for item in self.items
                if item.replaces_knowledge_item_id == source_item_id
                and item.status != "archived"
            ),
            None,
        )
    def save(self, item):
        self.save_calls += 1
        if self.save_error:
            raise self.save_error
        return item


def _item(item_id, title="Title", content="Content", status="draft"):
    item = KnowledgeItem(title=title, content=content, status=status)
    item.id = item_id
    return item


def _install(monkeypatch, fake_st, service):
    @contextmanager
    def service_scope():
        yield service
    monkeypatch.setattr(knowledge_hub, "st", fake_st)
    monkeypatch.setattr(knowledge_hub, "_knowledge_service", service_scope)


def test_empty_state(monkeypatch):
    fake_st = FakeStreamlit()
    _install(monkeypatch, fake_st, KnowledgeService(FakeRepository()))
    knowledge_hub.render()
    assert "No knowledge drafts yet" in fake_st.text()


def test_successful_create_clears_form_reruns_and_selects_new_item(monkeypatch):
    repo = FakeRepository()
    state = {
        "knowledge_create_title_0": "  New note  ",
        "knowledge_create_content_0": "  Useful content  ",
    }
    fake_st = FakeStreamlit(
        submitted=True,
        title="  New note  ",
        content="  Useful content  ",
        session_state=state,
    )
    _install(monkeypatch, fake_st, KnowledgeService(repo))
    knowledge_hub.render()
    assert repo.add_calls == 1
    assert (repo.items[0].title, repo.items[0].content, repo.items[0].status) == (
        "New note",
        "Useful content",
        "draft",
    )
    assert fake_st.rerun_calls == 1
    assert state[knowledge_hub._KNOWLEDGE_FLASH_KEY] == (
        "Knowledge draft created successfully."
    )
    assert state[knowledge_hub._KNOWLEDGE_SELECTED_VALUE_KEY] == 1
    assert state[knowledge_hub._KNOWLEDGE_CREATE_GENERATION_KEY] == 1
    assert "knowledge_create_title_0" not in state
    assert "knowledge_create_content_0" not in state
    assert "Title: New note" in fake_st.text()
    assert "Useful content" in fake_st.text()

    refreshed = FakeStreamlit(session_state=state)
    _install(monkeypatch, refreshed, KnowledgeService(repo))
    knowledge_hub.render()
    assert "Knowledge draft created successfully." in refreshed.text()
    assert refreshed.selected_option == "New note (draft)"
    assert refreshed.rerun_calls == 0
    assert "knowledge_create_title_1" not in state
    assert "knowledge_create_content_1" not in state


def test_create_captures_identifier_before_database_scope_closes(monkeypatch):
    class ExpiringCreated:
        expired = False

        @property
        def id(self):
            if self.expired:
                raise RuntimeError("detached database object")
            return 42

    created = ExpiringCreated()

    class CreateService:
        def create_draft(self, _title, _content):
            return created

    @contextmanager
    def expiring_scope():
        try:
            yield CreateService()
        finally:
            created.expired = True

    fake_st = FakeStreamlit()
    monkeypatch.setattr(knowledge_hub, "st", fake_st)
    monkeypatch.setattr(knowledge_hub, "_knowledge_service", expiring_scope)

    assert knowledge_hub._create_draft("Title", "Content") == 42


@pytest.mark.parametrize(
    ("title", "content", "expected"),
    [(" ", "Content", "title is required"), ("Title", " ", "content is required")],
)
def test_invalid_create_has_no_false_success(monkeypatch, title, content, expected):
    repo = FakeRepository()
    fake_st = FakeStreamlit(submitted=True, title=title, content=content)
    _install(monkeypatch, fake_st, KnowledgeService(repo))
    knowledge_hub.render()
    assert repo.add_calls == 0
    assert expected in fake_st.text()
    assert not any(kind == "success" for kind, _ in fake_st.messages)


def test_populated_list_and_selected_read_only_detail(monkeypatch):
    repo = FakeRepository([_item(1, "First", "One"), _item(2, "Second", "Two")])
    fake_st = FakeStreamlit(selected_id=2)
    _install(monkeypatch, fake_st, KnowledgeService(repo))
    knowledge_hub.render()
    assert "Loading knowledge..." in fake_st.spinner_labels
    assert "Title: Second" in fake_st.text()
    assert "Status: draft" in fake_st.text()
    assert "Two" in fake_st.text()
    assert "Created: Not available" in fake_st.text()
    assert "Last updated: Not available" in fake_st.text()
    assert "Knowledge title" in fake_st.widget_labels
    assert "Approve as official Knowledge" in fake_st.widget_labels
    assert "Archive knowledge draft" in fake_st.widget_labels


def test_selected_detail_uses_readable_utc_lifecycle_times(monkeypatch):
    item = _item(1)
    item.created_at = datetime(2026, 8, 23, 10, 30)
    item.updated_at = datetime(2026, 8, 24, 11, 45)
    fake_st = FakeStreamlit(selected_id=1)
    _install(monkeypatch, fake_st, KnowledgeService(FakeRepository([item])))

    knowledge_hub.render()

    assert "Created: 23 Aug 2026, 10:30 UTC" in fake_st.text()
    assert "Last updated: 24 Aug 2026, 11:45 UTC" in fake_st.text()


def test_missing_selected_record_is_safe(monkeypatch):
    class MissingService(KnowledgeService):
        def get_item(self, item_id): return None
    fake_st = FakeStreamlit()
    _install(monkeypatch, fake_st, MissingService(FakeRepository([_item(1)])))
    knowledge_hub.render()
    assert "selected knowledge item could not be found" in fake_st.text()


@pytest.mark.parametrize("operation", ["create", "load"])
def test_unexpected_failures_are_generic_and_do_not_leak(monkeypatch, operation):
    class FailingService:
        def create_draft(self, *args): raise RuntimeError("password SQL traceback")
        def list_items(self): raise RuntimeError("password SQL traceback")
    fake_st = FakeStreamlit(
        submitted=operation == "create", title="Title", content="Content"
    )
    _install(monkeypatch, fake_st, FailingService())
    knowledge_hub.render()
    expected = (
        "Knowledge draft creation failed"
        if operation == "create"
        else "Knowledge items could not be loaded"
    )
    assert expected in fake_st.text()
    for secret in ("password", "SQL", "traceback"):
        assert secret not in fake_st.text()
    assert not any(kind == "success" for kind, _ in fake_st.messages)


def test_successful_edit_reruns_and_refreshed_screen_shows_saved_values(monkeypatch):
    repo = FakeRepository([_item(1, "Original", "Old")])
    state = {
        "knowledge_edit_title_1": "  Updated  ",
        "knowledge_edit_content_1": "  New content  ",
        knowledge_hub._content_widget_key(1, "Old"): "Old",
    }
    submitted = FakeStreamlit(
        selected_id=1,
        submissions={"edit_knowledge_1": True},
        inputs={
            "Knowledge title": "  Updated  ",
            "Knowledge content": "  New content  ",
        },
        session_state=state,
    )
    _install(monkeypatch, submitted, KnowledgeService(repo))
    knowledge_hub.render()
    assert repo.save_calls == 1
    assert (repo.items[0].title, repo.items[0].content) == (
        "Updated", "New content"
    )
    assert submitted.rerun_calls == 1
    assert state[knowledge_hub._KNOWLEDGE_FLASH_KEY] == (
        "Knowledge draft updated successfully."
    )
    assert "knowledge_edit_title_1" not in state
    assert "knowledge_edit_content_1" not in state

    refreshed = FakeStreamlit(selected_id=1, session_state=state)
    _install(monkeypatch, refreshed, KnowledgeService(repo))
    knowledge_hub.render()
    assert "Knowledge draft updated successfully." in refreshed.text()
    assert "Title: Updated" in refreshed.text()
    assert "New content" in refreshed.text()
    assert refreshed.rerun_calls == 0
    assert knowledge_hub._content_widget_key(1, "Old") not in state
    assert state[knowledge_hub._content_widget_key(1, "New content")] == (
        "New content"
    )


def test_saved_content_identity_replaces_stale_detail_widget(monkeypatch):
    old_key = knowledge_hub._content_widget_key(1, "Old")
    state = {old_key: "Old"}
    fake_st = FakeStreamlit(selected_id=1, session_state=state)
    repo = FakeRepository([_item(1, "Updated", "New content")])
    _install(monkeypatch, fake_st, KnowledgeService(repo))

    knowledge_hub.render()

    new_key = knowledge_hub._content_widget_key(1, "New content")
    assert "New content" in fake_st.text()
    assert old_key not in state
    assert state[new_key] == "New content"


def test_archive_requires_confirmation_then_refreshes_read_only_state(monkeypatch):
    repo = FakeRepository([_item(1, "Original", "Old")])
    unconfirmed = FakeStreamlit(
        selected_id=1, submissions={"archive_knowledge_1": True}
    )
    _install(monkeypatch, unconfirmed, KnowledgeService(repo))
    knowledge_hub.render()
    assert repo.save_calls == 0
    assert "Confirm archiving" in unconfirmed.text()

    state = {}
    confirmed = FakeStreamlit(
        selected_id=1,
        submissions={"archive_knowledge_1": True},
        confirmed=True,
        session_state=state,
    )
    _install(monkeypatch, confirmed, KnowledgeService(repo))
    knowledge_hub.render()
    assert repo.items[0].status == "archived"
    assert confirmed.rerun_calls == 1

    refreshed = FakeStreamlit(selected_id=1, session_state=state)
    _install(monkeypatch, refreshed, KnowledgeService(repo))
    knowledge_hub.render()
    assert "Knowledge draft archived successfully." in refreshed.text()
    assert "Archived knowledge draft — read-only." in refreshed.text()
    assert "Original (archived)" in refreshed.selectbox_labels
    assert refreshed.selected_option == "Original (archived)"
    assert "Knowledge title" not in refreshed.widget_labels
    assert "Approve as official Knowledge" not in refreshed.widget_labels


def test_owner_approval_requires_confirmation_then_refreshes_official_state(
    monkeypatch,
):
    approved_at = datetime(2026, 8, 25, 14, 30, tzinfo=timezone.utc)
    untouched = _item(1, "Other draft", "Other content")
    reviewed = _item(7, "Reviewed rule", "Saved content")
    repo = FakeRepository([untouched, reviewed])
    service = KnowledgeService(repo, clock=lambda: approved_at)

    unconfirmed = FakeStreamlit(
        selected_id=7, submissions={"approve_knowledge_7": True}
    )
    _install(monkeypatch, unconfirmed, service)
    knowledge_hub.render()
    assert repo.save_calls == 0
    assert reviewed.status == "draft"
    assert "Confirm approval before submitting." in unconfirmed.text()
    assert "Approval uses the saved title and content" in unconfirmed.text()

    state = {}
    confirmed = FakeStreamlit(
        selected_id=7,
        submissions={"approve_knowledge_7": True},
        inputs={
            "Knowledge title": "Unsaved title",
            "Knowledge content": "Unsaved content",
        },
        confirmed=True,
        session_state=state,
    )
    _install(monkeypatch, confirmed, service)
    knowledge_hub.render()
    assert repo.save_calls == 1
    assert untouched.status == "draft"
    assert reviewed.status == "approved"
    assert (reviewed.title, reviewed.content) == ("Reviewed rule", "Saved content")
    assert reviewed.approved_at == approved_at
    assert reviewed.approved_by == "owner"
    assert confirmed.rerun_calls == 1
    assert state[knowledge_hub._KNOWLEDGE_FLASH_KEY] == (
        "Knowledge approved as official and is now read-only."
    )

    refreshed = FakeStreamlit(selected_id=7, session_state=state)
    _install(monkeypatch, refreshed, service)
    knowledge_hub.render()
    assert "Knowledge approved as official and is now read-only." in refreshed.text()
    assert "Status: approved" in refreshed.text()
    assert "Approved: 25 Aug 2026, 14:30 UTC" in refreshed.text()
    assert "Approved by: Owner" in refreshed.text()
    assert "Official Knowledge — approved and read-only." in refreshed.text()
    assert refreshed.selected_option == "Reviewed rule (approved)"
    assert "Knowledge title" not in refreshed.widget_labels
    assert "Approve as official Knowledge" not in refreshed.widget_labels
    assert "Create correction draft" in refreshed.widget_labels
    assert "Archive approved knowledge" in refreshed.widget_labels


def test_approved_knowledge_can_be_archived_without_losing_approval_evidence(
    monkeypatch,
):
    approved_at = datetime(2026, 8, 25, 14, 30, tzinfo=timezone.utc)
    item = _item(1, "Official rule", "Approved content", status="approved")
    item.approved_at = approved_at
    item.approved_by = "owner"
    repo = FakeRepository([item])
    state = {}
    submitted = FakeStreamlit(
        selected_id=1,
        submissions={"archive_knowledge_1": True},
        confirmed=True,
        session_state=state,
    )
    _install(monkeypatch, submitted, KnowledgeService(repo))

    knowledge_hub.render()

    assert item.status == "archived"
    assert item.approved_at == approved_at
    assert item.approved_by == "owner"
    assert submitted.rerun_calls == 1
    assert state[knowledge_hub._KNOWLEDGE_FLASH_KEY] == (
        "Approved knowledge archived successfully."
    )

    refreshed = FakeStreamlit(selected_id=1, session_state=state)
    _install(monkeypatch, refreshed, KnowledgeService(repo))
    knowledge_hub.render()
    assert "Approved knowledge archived successfully." in refreshed.text()
    assert "Archived approved Knowledge — read-only." in refreshed.text()
    assert "Approved: 25 Aug 2026, 14:30 UTC" in refreshed.text()
    assert "Approved by: Owner" in refreshed.text()
    assert "Approve as official Knowledge" not in refreshed.widget_labels
    assert "Archive approved knowledge" not in refreshed.widget_labels


def test_owner_creates_selected_replacement_draft_without_changing_source(
    monkeypatch,
):
    approved_at = datetime(2026, 8, 25, 14, 30, tzinfo=timezone.utc)
    source = _item(1, "Official rule", "Saved version", status="approved")
    source.approved_at = approved_at
    source.approved_by = "owner"
    repo = FakeRepository([source])
    state = {}
    submitted = FakeStreamlit(
        selected_id=1,
        submissions={"replace_knowledge_1": True},
        confirmed=True,
        session_state=state,
    )
    _install(monkeypatch, submitted, KnowledgeService(repo))

    knowledge_hub.render()

    assert len(repo.items) == 2
    replacement = repo.items[1]
    assert (source.title, source.content, source.status) == (
        "Official rule",
        "Saved version",
        "approved",
    )
    assert (replacement.title, replacement.content, replacement.status) == (
        "Official rule",
        "Saved version",
        "draft",
    )
    assert replacement.replaces_knowledge_item_id == source.id
    assert state[knowledge_hub._KNOWLEDGE_SELECTED_VALUE_KEY] == replacement.id
    assert state[knowledge_hub._KNOWLEDGE_FLASH_KEY] == (
        "Knowledge replacement draft created successfully."
    )
    assert submitted.rerun_calls == 1

    refreshed = FakeStreamlit(selected_id=replacement.id, session_state=state)
    _install(monkeypatch, refreshed, KnowledgeService(repo))
    knowledge_hub.render()
    assert "Knowledge replacement draft created successfully." in refreshed.text()
    assert "Replaces Knowledge item: #1" in refreshed.text()
    assert "Knowledge title" in refreshed.widget_labels
    assert "Approve as official Knowledge" in refreshed.widget_labels


def test_active_replacement_hides_source_mutations_and_superseded_is_history(
    monkeypatch,
):
    approved_at = datetime(2026, 8, 25, 14, 30, tzinfo=timezone.utc)
    replacement_time = datetime(2026, 8, 26, 9, 15, tzinfo=timezone.utc)
    source = _item(1, "Official rule", "Version one", status="approved")
    source.approved_at = approved_at
    source.approved_by = "owner"
    replacement = _item(2, "Official rule", "Version two", status="draft")
    replacement.replaces_knowledge_item_id = source.id
    repo = FakeRepository([source, replacement])

    source_view = FakeStreamlit(selected_id=source.id)
    _install(monkeypatch, source_view, KnowledgeService(repo))
    knowledge_hub.render()
    assert "Active replacement: #2 (draft)" in source_view.text()
    assert "A replacement is already active" in source_view.text()
    assert "Create correction draft" not in source_view.widget_labels
    assert "Archive approved knowledge" not in source_view.widget_labels

    KnowledgeService(repo, clock=lambda: replacement_time).approve_draft(
        replacement.id
    )
    superseded_view = FakeStreamlit(selected_id=source.id)
    _install(monkeypatch, superseded_view, KnowledgeService(repo))
    knowledge_hub.render()
    assert "Status: superseded" in superseded_view.text()
    assert "Active replacement: #2 (approved)" in superseded_view.text()
    assert "Superseded Knowledge — preserved as read-only history." in (
        superseded_view.text()
    )
    assert "Knowledge title" not in superseded_view.widget_labels
    assert "Approve as official Knowledge" not in superseded_view.widget_labels
    assert "Create correction draft" not in superseded_view.widget_labels
    assert "Archive approved knowledge" not in superseded_view.widget_labels


def test_replacement_creation_requires_confirmation(monkeypatch):
    source = _item(1, status="approved")
    source.approved_at = datetime(2026, 8, 25, tzinfo=timezone.utc)
    source.approved_by = "owner"
    repo = FakeRepository([source])
    fake_st = FakeStreamlit(
        selected_id=1, submissions={"replace_knowledge_1": True}
    )
    _install(monkeypatch, fake_st, KnowledgeService(repo))

    knowledge_hub.render()

    assert len(repo.items) == 1
    assert "Confirm replacement draft creation" in fake_st.text()
    assert fake_st.rerun_calls == 0


def test_known_approval_failure_is_readable_and_does_not_rerun(monkeypatch):
    class RejectedApprovalService:
        def approve_draft(self, _item_id):
            raise KnowledgeReadOnlyError("This item is no longer a draft.")

    fake_st = FakeStreamlit()
    _install(monkeypatch, fake_st, RejectedApprovalService())

    assert knowledge_hub._approve_draft(1) is False
    assert "This item is no longer a draft." in fake_st.text()
    assert fake_st.rerun_calls == 0


def test_selector_label_revision_keeps_selected_item_and_drops_old_widget(monkeypatch):
    draft = _item(1, "Changing", "Content")
    old_widget_key = knowledge_hub._selection_widget_key([draft])
    state = {
        knowledge_hub._KNOWLEDGE_SELECTED_VALUE_KEY: 1,
        old_widget_key: 1,
    }
    draft.status = "archived"
    fake_st = FakeStreamlit(session_state=state)
    _install(monkeypatch, fake_st, KnowledgeService(FakeRepository([draft])))

    knowledge_hub.render()

    new_widget_key = knowledge_hub._selection_widget_key([draft])
    assert fake_st.selected_option == "Changing (archived)"
    assert old_widget_key not in state
    assert state[new_widget_key] == 1
    assert state[knowledge_hub._KNOWLEDGE_SELECTED_VALUE_KEY] == 1


def test_unknown_status_and_unknown_flash_are_never_treated_as_trusted(monkeypatch):
    state = {knowledge_hub._KNOWLEDGE_FLASH_KEY: "untrusted content"}
    fake_st = FakeStreamlit(selected_id=1, session_state=state)
    repo = FakeRepository([_item(1, status="unexpected")])
    _install(monkeypatch, fake_st, KnowledgeService(repo))
    knowledge_hub.render()
    assert "unsupported status" in fake_st.text()
    assert "untrusted content" not in fake_st.text()
    assert "Knowledge title" not in fake_st.widget_labels
    assert "Approve as official Knowledge" not in fake_st.widget_labels


@pytest.mark.parametrize("operation", ["edit", "approve", "replace", "archive"])
def test_lifecycle_failures_are_generic_and_do_not_rerun(monkeypatch, operation):
    class FailingService:
        def _selected(self):
            return _item(1, status="approved" if operation == "replace" else "draft")
        def list_items(self): return [self._selected()]
        def get_item(self, _item_id): return self._selected()
        def edit_draft(self, *_args):
            raise RuntimeError("password SQL token traceback")
        def approve_draft(self, *_args):
            raise RuntimeError("password SQL token traceback")
        def create_replacement_draft(self, *_args):
            raise RuntimeError("password SQL token traceback")
        def archive_draft(self, *_args):
            raise RuntimeError("password SQL token traceback")

    fake_st = FakeStreamlit(
        selected_id=1,
        submissions={f"{operation}_knowledge_1": True},
        inputs={"Knowledge title": "Title", "Knowledge content": "Content"},
        confirmed=True,
    )
    _install(monkeypatch, fake_st, FailingService())
    knowledge_hub.render()
    expected = (
        "Knowledge draft update failed"
        if operation == "edit"
        else (
            "Knowledge approval failed"
            if operation == "approve"
            else (
                "Knowledge replacement creation failed"
                if operation == "replace"
                else "Knowledge draft archive failed"
            )
        )
    )
    assert expected in fake_st.text()
    for secret in ("password", "SQL", "token", "traceback"):
        assert secret not in fake_st.text()
    assert fake_st.rerun_calls == 0
    assert knowledge_hub._KNOWLEDGE_FLASH_KEY not in fake_st.session_state
