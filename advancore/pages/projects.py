"""Streamlit presentation for basic project registration and viewing."""

from collections.abc import Iterator
from contextlib import contextmanager

import streamlit as st

from advancore.repositories import ProjectRepository
from advancore.services.project_service import (
    DuplicateProjectNameError,
    ProjectService,
    ProjectValidationError,
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
                    format_func=lambda project_id: project_by_id[project_id].name,
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
    except Exception:
        st.error("Projects could not be loaded. Please try again.")


def render():
    st.header("Projects")
    st.write("Register a project or select an existing project to view its details.")

    st.subheader("Create project")
    with st.form("create_project"):
        name = st.text_input("Name", max_chars=200)
        description = st.text_area("Description (optional)")
        submitted = st.form_submit_button("Create project", type="primary")

    if submitted:
        _create_project(name, description)

    _render_projects()
