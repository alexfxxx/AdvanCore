"""Streamlit presentation for basic project registration and viewing."""

from collections.abc import Iterator
from contextlib import contextmanager

import streamlit as st

from advancore.repositories import ProjectRepository
from advancore.services.project_service import (
    DuplicateProjectNameError,
    ProjectAlreadyArchivedError,
    ProjectNotFoundError,
    ProjectReadOnlyError,
    ProjectService,
    ProjectValidationError,
)


_PROJECT_FLASH_KEY = "projects_success_notice"
_PROJECT_SUCCESS_MESSAGES = frozenset(
    {"Project updated successfully.", "Project archived successfully."}
)


@contextmanager
def _project_service() -> Iterator[ProjectService]:
    """Provide a project service inside the established unit of work."""
    # Import lazily so importing the presentation module does not open or
    # configure a database connection. session_scope owns commit/rollback.
    from advancore.services.database import session_scope

    with session_scope() as session:
        yield ProjectService(ProjectRepository(session))


def _create_project(name: str, description: str) -> bool:
    """Create one project and render a presentation-safe outcome."""
    try:
        with _project_service() as service:
            service.create_project(name, description)
    except ProjectValidationError as exc:
        st.error(str(exc))
        return False
    except DuplicateProjectNameError as exc:
        st.error(str(exc))
        return False
    except Exception:
        st.error("Project creation failed. Please try again.")
        return False

    st.success("Project created successfully.")
    return True


def _edit_project(project_id: int, name: str, description: str) -> bool:
    """Edit one project and render a presentation-safe outcome."""
    try:
        with _project_service() as service:
            service.edit_project(project_id, name, description)
    except (ProjectValidationError, DuplicateProjectNameError) as exc:
        st.error(str(exc))
        return False
    except (ProjectNotFoundError, ProjectReadOnlyError) as exc:
        st.warning(str(exc))
        return False
    except Exception:
        st.error("Project update failed. Please try again.")
        return False
    return True


def _archive_project(project_id: int) -> bool:
    """Archive one project and render a presentation-safe outcome."""
    try:
        with _project_service() as service:
            service.archive_project(project_id)
    except (
        ProjectNotFoundError,
        ProjectAlreadyArchivedError,
        ProjectReadOnlyError,
    ) as exc:
        st.warning(str(exc))
        return False
    except Exception:
        st.error("Project archive failed. Please try again.")
        return False
    return True


def _refresh_with_success(
    message: str, *, clear_session_keys: tuple[str, ...] = ()
) -> None:
    """Keep one bounded success notice across the immediate Streamlit rerun."""
    if message not in _PROJECT_SUCCESS_MESSAGES:
        raise ValueError("Unsupported project success notice")
    for key in clear_session_keys:
        st.session_state.pop(key, None)
    st.session_state[_PROJECT_FLASH_KEY] = message
    st.rerun()


def _render_success_notice() -> None:
    """Consume and show one post-rerun success notice."""
    message = st.session_state.pop(_PROJECT_FLASH_KEY, None)
    if message in _PROJECT_SUCCESS_MESSAGES:
        st.success(message)


def _render_projects() -> None:
    """Load and render the deterministic project list and selected detail."""
    try:
        with st.spinner("Loading projects..."):
            with _project_service() as service:
                projects = list(service.list_projects())

                if not projects:
                    st.info("No projects yet. Create the first project above.")
                    return

                st.subheader("Project list")
                project_by_id = {project.id: project for project in projects}
                selected_id = st.selectbox(
                    "Select a project",
                    options=list(project_by_id),
                    format_func=lambda project_id: (
                        f"{project_by_id[project_id].name} (archived)"
                        if project_by_id[project_id].status == "archived"
                        else project_by_id[project_id].name
                    ),
                    key="projects_selected_id",
                )

                selected = service.get_project(selected_id)
                if selected is None:
                    st.warning("The selected project could not be found.")
                    return

                st.subheader("Project details")
                st.write(f"Name: {selected.name}")
                st.write(
                    f"Description: {selected.description}"
                    if selected.description
                    else "Description: Not provided"
                )
                st.write(f"Status: {selected.status}")

                if selected.status == "archived":
                    st.info("Archived project — read-only.")
                    return
                if selected.status != "active":
                    st.warning(
                        "This project has an unsupported status and is read-only."
                    )
                    return

                st.subheader("Edit project")
                with st.form(f"edit_project_{selected.id}"):
                    edited_name = st.text_input(
                        "Project name",
                        value=selected.name,
                        max_chars=200,
                        key=f"project_edit_name_{selected.id}",
                    )
                    edited_description = st.text_area(
                        "Project description (optional)",
                        value=selected.description or "",
                        key=f"project_edit_description_{selected.id}",
                    )
                    edit_submitted = st.form_submit_button(
                        "Save changes", type="primary"
                    )
                if edit_submitted and _edit_project(
                    selected.id, edited_name, edited_description
                ):
                    _refresh_with_success(
                        "Project updated successfully.",
                        clear_session_keys=(
                            f"project_edit_name_{selected.id}",
                            f"project_edit_description_{selected.id}",
                        ),
                    )

                st.subheader("Archive project")
                with st.form(f"archive_project_{selected.id}"):
                    archive_confirmed = st.checkbox(
                        "I confirm that this project should be archived."
                    )
                    archive_submitted = st.form_submit_button("Archive project")
                if archive_submitted:
                    if not archive_confirmed:
                        st.warning("Confirm archiving before submitting.")
                    elif _archive_project(selected.id):
                        _refresh_with_success("Project archived successfully.")
    except Exception:
        st.error("Projects could not be loaded. Please try again.")


def render():
    st.header("Projects")
    st.write("Register a project or select an existing project to view its details.")
    _render_success_notice()

    st.subheader("Create project")
    with st.form("create_project"):
        name = st.text_input("Name", max_chars=200)
        description = st.text_area("Description (optional)")
        submitted = st.form_submit_button("Create project", type="primary")

    if submitted:
        _create_project(name, description)

    _render_projects()
