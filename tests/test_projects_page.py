"""Isolated tests for the Projects Streamlit presentation."""

from contextlib import contextmanager, nullcontext

import pytest

from advancore.models import Project
from advancore.pages import projects as projects_page
from advancore.services.project_service import ProjectService


class FakeStreamlit:
    def __init__(self, *, submitted=False, name="", description="", selected_id=None):
        self.submitted = submitted
        self.name = name
        self.description = description
        self.selected_id = selected_id
        self.messages: list[tuple[str, str]] = []
        self.spinner_labels: list[str] = []

    def _record(self, kind, value):
        self.messages.append((kind, str(value)))

    def header(self, value): self._record("header", value)
    def subheader(self, value): self._record("subheader", value)
    def write(self, value): self._record("write", value)
    def info(self, value): self._record("info", value)
    def warning(self, value): self._record("warning", value)
    def error(self, value): self._record("error", value)
    def success(self, value): self._record("success", value)

    def form(self, _key): return nullcontext()
    def text_input(self, _label, **_kwargs): return self.name
    def text_area(self, _label, **_kwargs): return self.description
    def form_submit_button(self, _label, **_kwargs): return self.submitted

    def spinner(self, label):
        self.spinner_labels.append(label)
        return nullcontext()

    def selectbox(self, _label, options, **_kwargs):
        return self.selected_id if self.selected_id is not None else options[0]

    def text(self):
        return "\n".join(message for _, message in self.messages)


class FakeRepository:
    def __init__(self, projects=None):
        self.projects = list(projects or [])
        self.add_calls = 0
        self.next_id = max((project.id for project in self.projects), default=0) + 1

    def add(self, project):
        self.add_calls += 1
        project.id = self.next_id
        self.next_id += 1
        self.projects.append(project)
        return project

    def list(self): return list(self.projects)
    def get_by_id(self, project_id):
        return next((p for p in self.projects if p.id == project_id), None)
    def get_by_name(self, name):
        return next((p for p in self.projects if p.name == name), None)


def project(project_id, name, description=None, status="active"):
    item = Project(name=name, description=description, status=status)
    item.id = project_id
    return item


def install_fakes(monkeypatch, fake_st, service):
    @contextmanager
    def service_scope():
        yield service

    monkeypatch.setattr(projects_page, "st", fake_st)
    monkeypatch.setattr(projects_page, "_project_service", service_scope)


def test_populated_list_and_selected_project_detail(monkeypatch):
    repo = FakeRepository([project(1, "Alpha", "First"), project(2, "Beta")])
    fake_st = FakeStreamlit(selected_id=2)
    install_fakes(monkeypatch, fake_st, ProjectService(repo))

    projects_page.render()

    assert "Loading projects..." in fake_st.spinner_labels
    assert "Name: Beta" in fake_st.text()
    assert "Description: Not provided" in fake_st.text()
    assert "Status: active" in fake_st.text()


def test_empty_project_state(monkeypatch):
    fake_st = FakeStreamlit()
    install_fakes(monkeypatch, fake_st, ProjectService(FakeRepository()))
    projects_page.render()
    assert "No projects yet" in fake_st.text()


def test_valid_creation_shows_success_and_active_project(monkeypatch):
    repo = FakeRepository()
    fake_st = FakeStreamlit(
        submitted=True, name="  New project  ", description="  Useful  "
    )
    install_fakes(monkeypatch, fake_st, ProjectService(repo))
    projects_page.render()

    assert repo.add_calls == 1
    assert repo.projects[0].name == "New project"
    assert repo.projects[0].description == "Useful"
    assert repo.projects[0].status == "active"
    assert "Project created successfully." in fake_st.text()
    assert "Name: New project" in fake_st.text()


@pytest.mark.parametrize(
    ("name", "expected"), [("   ", "required"), ("x" * 201, "200 characters")]
)
def test_invalid_name_does_not_persist_or_show_success(monkeypatch, name, expected):
    repo = FakeRepository()
    fake_st = FakeStreamlit(submitted=True, name=name)
    install_fakes(monkeypatch, fake_st, ProjectService(repo))
    projects_page.render()

    assert repo.add_calls == 0
    assert expected in fake_st.text()
    assert not any(kind == "success" for kind, _ in fake_st.messages)


def test_duplicate_feedback_has_no_false_success(monkeypatch):
    repo = FakeRepository([project(1, "Existing")])
    fake_st = FakeStreamlit(submitted=True, name="Existing")
    install_fakes(monkeypatch, fake_st, ProjectService(repo))
    projects_page.render()

    assert repo.add_calls == 0
    assert "exact name already exists" in fake_st.text()
    assert not any(kind == "success" for kind, _ in fake_st.messages)


def test_missing_selected_record_shows_safe_warning(monkeypatch):
    class MissingService(ProjectService):
        def get_project(self, project_id): return None

    fake_st = FakeStreamlit()
    service = MissingService(FakeRepository([project(1, "Vanished")]))
    install_fakes(monkeypatch, fake_st, service)
    projects_page.render()
    assert "selected project could not be found" in fake_st.text()


def test_loading_failure_does_not_expose_exception_details(monkeypatch):
    class FailingService:
        def list_projects(self):
            raise RuntimeError("postgres://secret@host internal SQL")

    fake_st = FakeStreamlit()
    install_fakes(monkeypatch, fake_st, FailingService())
    projects_page.render()

    assert "Projects could not be loaded" in fake_st.text()
    assert "secret" not in fake_st.text()
    assert "SQL" not in fake_st.text()


def test_creation_failure_does_not_claim_success_or_leak_details(monkeypatch):
    class FailingService:
        def create_project(self, name, description):
            raise RuntimeError("password=do-not-render")
        def list_projects(self): return []

    fake_st = FakeStreamlit(submitted=True, name="New")
    install_fakes(monkeypatch, fake_st, FailingService())
    projects_page.render()

    assert "Project creation failed" in fake_st.text()
    assert "password" not in fake_st.text()
    assert not any(kind == "success" for kind, _ in fake_st.messages)
