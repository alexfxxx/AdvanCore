"""Streamlit presentation for the bounded operational overview."""

from collections.abc import Iterator
from contextlib import contextmanager

import streamlit as st

from advancore.repositories import KnowledgeItemRepository, ProjectRepository
from advancore.services.dashboard_service import DashboardService


@contextmanager
def _dashboard_service() -> Iterator[DashboardService]:
    from advancore.services.database import session_scope

    with session_scope() as session:
        yield DashboardService(
            ProjectRepository(session), KnowledgeItemRepository(session)
        )

def render():
    st.subheader("Platform Status")
    st.success("Core application shell operational.")
    try:
        with st.spinner("Loading overview..."):
            with _dashboard_service() as service:
                summary = service.get_summary()
    except Exception:
        st.error("Operational overview is unavailable. Please check the database.")
        return

    st.success("Database connected.")
    st.subheader("Projects overview")
    st.metric("Total projects", summary.total_projects)
    st.metric("Active projects", summary.active_projects)
    st.metric("Archived projects", summary.archived_projects)
    st.metric("Other project statuses", summary.other_projects)

    st.subheader("Knowledge overview")
    st.metric("Total knowledge items", summary.total_knowledge)
    st.metric("Draft knowledge items", summary.draft_knowledge)
    st.metric("Other knowledge statuses", summary.other_knowledge)
    st.caption("Use the navigation menu to manage Projects or capture Knowledge drafts.")
