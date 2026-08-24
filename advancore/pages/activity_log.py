"""Streamlit read-only viewer for existing activity records."""

from collections.abc import Iterator
from contextlib import contextmanager

import streamlit as st

from advancore.repositories import ActivityLogRepository
from advancore.services.activity_service import ActivityLogService
from advancore.ui.formatting import format_utc_timestamp


_ENTITY_FILTERS = ("all", "project", "knowledge")
_ACTION_FILTERS = (
    "all",
    "project_created",
    "project_updated",
    "project_archived",
    "knowledge_created",
    "knowledge_updated",
    "knowledge_archived",
)


def _filter_activities(activities, entity_filter: str, action_filter: str):
    """Apply exact approved filters without changing the underlying records."""
    return [
        activity
        for activity in activities
        if (entity_filter == "all" or activity.entity_type == entity_filter)
        and (action_filter == "all" or activity.action == action_filter)
    ]


@contextmanager
def _activity_service() -> Iterator[ActivityLogService]:
    from advancore.services.database import session_scope

    with session_scope() as session:
        yield ActivityLogService(ActivityLogRepository(session))


def render():
    st.header("Activity Log")
    st.write("View existing system activity records.")
    try:
        with st.spinner("Loading activity..."):
            with _activity_service() as service:
                activities = list(service.list_activities())
                if not activities:
                    st.info("No activity records are available.")
                    return

                entity_filter = st.selectbox(
                    "Filter by entity type",
                    options=_ENTITY_FILTERS,
                    format_func=lambda value: (
                        "All entities" if value == "all" else value.title()
                    ),
                    key="activity_entity_filter",
                )
                action_filter = st.selectbox(
                    "Filter by action",
                    options=_ACTION_FILTERS,
                    format_func=lambda value: (
                        "All actions" if value == "all" else value.replace("_", " ").title()
                    ),
                    key="activity_action_filter",
                )
                filtered_activities = _filter_activities(
                    activities, entity_filter, action_filter
                )
                if not filtered_activities:
                    st.info("No activity records match the selected filters.")
                    return

                activity_by_id = {activity.id: activity for activity in activities}
                filtered_ids = [activity.id for activity in filtered_activities]
                selected_id = st.selectbox(
                    "Select an activity record",
                    options=filtered_ids,
                    format_func=lambda activity_id: (
                        f"{activity_by_id[activity_id].action} (#{activity_id})"
                    ),
                    key=f"activity_selected_id_{entity_filter}_{action_filter}",
                )
                selected = service.get_activity(selected_id)
                if selected is None:
                    st.warning("The selected activity record could not be found.")
                    return

                st.subheader("Activity details")
                st.write(f"Action: {selected.action}")
                st.write(f"Entity type: {selected.entity_type or 'Not provided'}")
                st.write(f"Entity ID: {selected.entity_id or 'Not provided'}")
                st.write(f"Created: {format_utc_timestamp(selected.created_at)}")
                st.text_area(
                    "Details",
                    value=selected.details or "Not provided",
                    height=180,
                    disabled=True,
                    key=f"activity_details_{selected.id}",
                )
    except Exception:
        st.error("Activity records could not be loaded. Please try again.")
