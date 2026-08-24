"""Isolated tests for the Projects Streamlit presentation."""

from contextlib import contextmanager, nullcontext

import pytest

from advancore.models import Project
from advancore.pages import projects as projects_page
from advancore.services.project_service import ProjectService


class FakeStreamlit:
    def __init__(
        self,
        *,
        submitted=False,
        name="",
        description="",
        selected_id=None,
        submissions=None,
        inputs=None,
        confirmed=False,
        session_state=None,
    ):
        self.submitted = submitted
        self.name = name
        self.description = description
        self.selected_id = selected_id
        self.messages: list[tuple[str, str]] = []
        self.spinner_labels: list[str] = []
        self.submissions = submissions or {}
        self.inputs = inputs or {}
        self.confirmed = confirmed
        self.session_state = session_state if session_state is not None else {}
        self.current_form = None
        self.widget_labels: list[str] = []
        self.selectbox_labels: list[str] = []
        self.selected_option = None
        self.rerun_calls = 0

    def _record(self, kind, value):
        self.messages.append((kind, str(value)))

    def header(self, value): self._record("header", value)
    def subheader(self, value): self._record("subheader", value)
    def write(self, value): self._record("write", value)
    def info(self, value): self._record("info", value)
    def warning(self, value): self._record("warning", value)
    def error(self, value): self._record("error", value)
    def success(self, value): self._record("success", value)

    @contextmanager
    def form(self, key):
        previous = self.current_form
        self.current_form = key
        try:
            yield
        finally:
            self.current_form = previous

    def text_input(self, label, **kwargs):
        self.widget_labels.append(label)
        if label == "Name":
            return self.name
        return self.inputs.get(label, kwargs.get("value", ""))

    def text_area(self, label, **kwargs):
        self.widget_labels.append(label)
        if label == "Description (optional)":
            return self.description
        return self.inputs.get(label, kwargs.get("value", ""))

    def checkbox(self, label, **_kwargs):
        self.widget_labels.append(label)
        return self.confirmed

    def form_submit_button(self, label, **_kwargs):
        self.widget_labels.append(label)
        if self.submissions:
            return self.submissions.get(self.current_form, False)
        return self.submitted if self.current_form == "create_project" else False

    def rerun(self):
        self.rerun_calls += 1

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

    def text(self):
        return "\n".join(message for _, message in self.messages)


class FakeRepository:
    def __init__(self, projects=None):
        self.projects = list(projects or [])
        self.add_calls = 0
        self.next_id = max((project.id for project in self.projects), default=0) + 1
        self.save_calls = 0

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
    def save(self, project):
        self.save_calls += 1
        return project


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


def test_valid_creation_clears_form_reruns_and_selects_new_project(monkeypatch):
    repo = FakeRepository()
    state = {
        "project_create_name_0": "  New project  ",
        "project_create_description_0": "  Useful  ",
    }
    fake_st = FakeStreamlit(
        submitted=True,
        name="  New project  ",
        description="  Useful  ",
        session_state=state,
    )
    install_fakes(monkeypatch, fake_st, ProjectService(repo))
    projects_page.render()

    assert repo.add_calls == 1
    assert repo.projects[0].name == "New project"
    assert repo.projects[0].description == "Useful"
    assert repo.projects[0].status == "active"
    assert fake_st.rerun_calls == 1
    assert state[projects_page._PROJECT_FLASH_KEY] == (
        "Project created successfully."
    )
    assert state[projects_page._PROJECT_CREATE_GENERATION_KEY] == 1
    assert state[projects_page._PROJECT_SELECTED_VALUE_KEY] == 1
    assert "project_create_name_0" not in state
    assert "project_create_description_0" not in state
    assert "Name: New project" in fake_st.text()

    refreshed = FakeStreamlit(session_state=state)
    install_fakes(monkeypatch, refreshed, ProjectService(repo))
    projects_page.render()
    assert "Project created successfully." in refreshed.text()
    assert refreshed.selected_option == "New project"
    assert refreshed.rerun_calls == 0


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
        def create_project(self, _name, _description):
            return created

    @contextmanager
    def expiring_scope():
        try:
            yield CreateService()
        finally:
            created.expired = True

    fake_st = FakeStreamlit()
    monkeypatch.setattr(projects_page, "st", fake_st)
    monkeypatch.setattr(projects_page, "_project_service", expiring_scope)

    assert projects_page._create_project("Name", "Description") == 42


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


def test_active_project_shows_prepopulated_edit_and_archive_controls(monkeypatch):
    repo = FakeRepository([project(1, "Alpha", "First")])
    fake_st = FakeStreamlit(selected_id=1)
    install_fakes(monkeypatch, fake_st, ProjectService(repo))
    projects_page.render()
    assert "Project name" in fake_st.widget_labels
    assert "Save changes" in fake_st.widget_labels
    assert "Archive project" in fake_st.widget_labels


def test_successful_edit_reruns_once_and_next_render_shows_notice(monkeypatch):
    repo = FakeRepository([project(1, "Alpha", "First")])
    state = {
        "project_edit_name_1": "  Renamed  ",
        "project_edit_description_1": "  ",
    }
    submitted = FakeStreamlit(
        selected_id=1,
        submissions={"edit_project_1": True},
        inputs={"Project name": "  Renamed  ", "Project description (optional)": "  "},
        session_state=state,
    )
    install_fakes(monkeypatch, submitted, ProjectService(repo))
    projects_page.render()
    assert repo.add_calls == 0
    assert repo.save_calls == 1
    assert (repo.projects[0].name, repo.projects[0].description) == ("Renamed", None)
    assert submitted.rerun_calls == 1
    assert state[projects_page._PROJECT_FLASH_KEY] == "Project updated successfully."
    assert "project_edit_name_1" not in state
    assert "project_edit_description_1" not in state

    refreshed = FakeStreamlit(selected_id=1, session_state=state)
    install_fakes(monkeypatch, refreshed, ProjectService(repo))
    projects_page.render()
    assert "Project updated successfully." in refreshed.text()
    assert "Name: Renamed" in refreshed.text()
    assert refreshed.rerun_calls == 0
    assert projects_page._PROJECT_FLASH_KEY not in state


def test_unknown_success_notice_is_consumed_without_rendering(monkeypatch):
    state = {projects_page._PROJECT_FLASH_KEY: "untrusted content"}
    fake_st = FakeStreamlit(session_state=state)
    install_fakes(monkeypatch, fake_st, ProjectService(FakeRepository()))
    projects_page.render()
    assert "untrusted content" not in fake_st.text()
    assert projects_page._PROJECT_FLASH_KEY not in state


@pytest.mark.parametrize(
    ("name", "expected"), [(" ", "required"), ("x" * 201, "200 characters")]
)
def test_edit_validation_has_no_success_or_rerun(monkeypatch, name, expected):
    repo = FakeRepository([project(1, "Alpha")])
    fake_st = FakeStreamlit(
        selected_id=1,
        submissions={"edit_project_1": True},
        inputs={"Project name": name},
    )
    install_fakes(monkeypatch, fake_st, ProjectService(repo))
    projects_page.render()
    assert repo.save_calls == 0
    assert expected in fake_st.text()
    assert fake_st.rerun_calls == 0
    assert projects_page._PROJECT_FLASH_KEY not in fake_st.session_state


def test_edit_duplicate_has_no_success_or_rerun(monkeypatch):
    repo = FakeRepository([project(1, "Alpha"), project(2, "Beta")])
    fake_st = FakeStreamlit(
        selected_id=1,
        submissions={"edit_project_1": True},
        inputs={"Project name": "Beta"},
    )
    install_fakes(monkeypatch, fake_st, ProjectService(repo))
    projects_page.render()
    assert "exact name already exists" in fake_st.text()
    assert repo.save_calls == 0
    assert fake_st.rerun_calls == 0


def test_archive_requires_confirmation_then_reruns_and_refreshes(monkeypatch):
    repo = FakeRepository([project(1, "Alpha")])
    unconfirmed = FakeStreamlit(
        selected_id=1,
        submissions={"archive_project_1": True},
        confirmed=False,
    )
    install_fakes(monkeypatch, unconfirmed, ProjectService(repo))
    projects_page.render()
    assert repo.save_calls == 0
    assert unconfirmed.rerun_calls == 0
    assert "Confirm archiving" in unconfirmed.text()

    state = {}
    confirmed = FakeStreamlit(
        selected_id=1,
        submissions={"archive_project_1": True},
        confirmed=True,
        session_state=state,
    )
    install_fakes(monkeypatch, confirmed, ProjectService(repo))
    projects_page.render()
    assert repo.save_calls == 1
    assert repo.projects[0].status == "archived"
    assert confirmed.rerun_calls == 1

    refreshed = FakeStreamlit(selected_id=1, session_state=state)
    install_fakes(monkeypatch, refreshed, ProjectService(repo))
    projects_page.render()
    assert "Project archived successfully." in refreshed.text()
    assert "Status: archived" in refreshed.text()
    assert "Archived project — read-only." in refreshed.text()
    assert refreshed.selected_option == "Alpha (archived)"
    assert "Project name" not in refreshed.widget_labels
    assert refreshed.rerun_calls == 0


def test_selector_label_revision_keeps_project_and_drops_old_widget(monkeypatch):
    changing = project(1, "Changing")
    old_widget_key = projects_page._selection_widget_key([changing])
    state = {
        projects_page._PROJECT_SELECTED_VALUE_KEY: 1,
        old_widget_key: 1,
    }
    changing.status = "archived"
    fake_st = FakeStreamlit(session_state=state)
    install_fakes(
        monkeypatch, fake_st, ProjectService(FakeRepository([changing]))
    )

    projects_page.render()

    new_widget_key = projects_page._selection_widget_key([changing])
    assert fake_st.selected_option == "Changing (archived)"
    assert old_widget_key not in state
    assert state[new_widget_key] == 1
    assert state[projects_page._PROJECT_SELECTED_VALUE_KEY] == 1


def test_archived_project_is_labelled_listed_and_read_only(monkeypatch):
    repo = FakeRepository([project(1, "Historic", status="archived")])
    fake_st = FakeStreamlit(selected_id=1)
    install_fakes(monkeypatch, fake_st, ProjectService(repo))
    projects_page.render()
    assert "Historic (archived)" in fake_st.selectbox_labels
    assert "Status: archived" in fake_st.text()
    assert "Archived project — read-only." in fake_st.text()
    assert "Project name" not in fake_st.widget_labels
    assert "Archive project" not in fake_st.widget_labels


def test_unknown_status_is_read_only(monkeypatch):
    repo = FakeRepository([project(1, "Odd", status="unexpected")])
    fake_st = FakeStreamlit(selected_id=1)
    install_fakes(monkeypatch, fake_st, ProjectService(repo))
    projects_page.render()
    assert "unsupported status" in fake_st.text()
    assert "Project name" not in fake_st.widget_labels
    assert fake_st.rerun_calls == 0


@pytest.mark.parametrize("operation", ["edit", "archive"])
def test_lifecycle_failures_do_not_expose_details_or_rerun(monkeypatch, operation):
    class FailingService:
        def list_projects(self): return [project(1, "Alpha")]
        def get_project(self, project_id): return project(1, "Alpha")
        def edit_project(self, *args): raise RuntimeError("password SQL token traceback")
        def archive_project(self, *args): raise RuntimeError("password SQL token traceback")

    form = f"{operation}_project_1"
    fake_st = FakeStreamlit(
        selected_id=1,
        submissions={form: True},
        confirmed=True,
        inputs={"Project name": "Alpha"},
    )
    install_fakes(monkeypatch, fake_st, FailingService())
    projects_page.render()
    expected = "Project update failed" if operation == "edit" else "Project archive failed"
    assert expected in fake_st.text()
    for secret in ("password", "SQL", "token", "traceback"):
        assert secret not in fake_st.text()
    assert fake_st.rerun_calls == 0
    assert projects_page._PROJECT_FLASH_KEY not in fake_st.session_state


@pytest.mark.parametrize(
    ("operation", "error", "expected"),
    [
        (
            "edit",
            projects_page.ProjectNotFoundError(
                "The selected project could not be found."
            ),
            "could not be found",
        ),
        (
            "edit",
            projects_page.ProjectReadOnlyError(
                "This project is read-only and cannot be edited."
            ),
            "read-only",
        ),
        (
            "archive",
            projects_page.ProjectNotFoundError(
                "The selected project could not be found."
            ),
            "could not be found",
        ),
        (
            "archive",
            projects_page.ProjectAlreadyArchivedError(
                "This project is already archived."
            ),
            "already archived",
        ),
    ],
)
def test_lifecycle_conflicts_render_safe_feedback_without_rerun(
    monkeypatch, operation, error, expected
):
    class ConflictService:
        def edit_project(self, *args): raise error
        def archive_project(self, *args): raise error

    fake_st = FakeStreamlit()
    install_fakes(monkeypatch, fake_st, ConflictService())
    if operation == "edit":
        result = projects_page._edit_project(1, "Name", "")
    else:
        result = projects_page._archive_project(1)
    assert result is False
    assert expected in fake_st.text()
    assert fake_st.rerun_calls == 0
    assert not fake_st.session_state
