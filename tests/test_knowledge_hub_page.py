"""Isolated tests for the first usable Knowledge Hub page."""

from contextlib import contextmanager, nullcontext

import pytest

from advancore.models import KnowledgeItem
from advancore.pages import knowledge_hub
from advancore.services.knowledge_service import KnowledgeService


class FakeStreamlit:
    def __init__(self, *, submitted=False, title="", content="", selected_id=None):
        self.submitted = submitted
        self.title = title
        self.content = content
        self.selected_id = selected_id
        self.messages = []
        self.spinner_labels = []
        self.widget_labels = []

    def _record(self, kind, value): self.messages.append((kind, str(value)))
    def header(self, value): self._record("header", value)
    def subheader(self, value): self._record("subheader", value)
    def write(self, value): self._record("write", value)
    def info(self, value): self._record("info", value)
    def warning(self, value): self._record("warning", value)
    def error(self, value): self._record("error", value)
    def success(self, value): self._record("success", value)
    def form(self, _key): return nullcontext()
    def text_input(self, label, **_kwargs):
        self.widget_labels.append(label)
        return self.title
    def text_area(self, label, **kwargs):
        self.widget_labels.append(label)
        if kwargs.get("disabled"):
            self._record("detail_content", kwargs.get("value", ""))
            return kwargs.get("value", "")
        return self.content
    def form_submit_button(self, label, **_kwargs):
        self.widget_labels.append(label)
        return self.submitted
    def spinner(self, label):
        self.spinner_labels.append(label)
        return nullcontext()
    def selectbox(self, _label, options, **_kwargs):
        return self.selected_id if self.selected_id is not None else options[0]
    def text(self): return "\n".join(message for _, message in self.messages)


class FakeRepository:
    def __init__(self, items=None):
        self.items = list(items or [])
        self.add_calls = 0

    def add(self, item):
        self.add_calls += 1
        item.id = max((saved.id for saved in self.items), default=0) + 1
        self.items.append(item)
        return item

    def list(self): return list(self.items)
    def get_by_id(self, item_id):
        return next((item for item in self.items if item.id == item_id), None)


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


def test_successful_create_is_visible_in_same_render(monkeypatch):
    repo = FakeRepository()
    fake_st = FakeStreamlit(
        submitted=True, title="  New note  ", content="  Useful content  "
    )
    _install(monkeypatch, fake_st, KnowledgeService(repo))
    knowledge_hub.render()
    assert repo.add_calls == 1
    assert (repo.items[0].title, repo.items[0].content, repo.items[0].status) == (
        "New note",
        "Useful content",
        "draft",
    )
    assert "Knowledge draft created successfully." in fake_st.text()
    assert "Title: New note" in fake_st.text()
    assert "Useful content" in fake_st.text()


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
