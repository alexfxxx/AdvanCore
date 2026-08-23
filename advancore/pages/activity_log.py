"""Streamlit read-only viewer for existing activity records."""

from collections.abc import Iterator
from contextlib import contextmanager

import streamlit as st

from advancore.repositories import ActivityLogRepository
from advancore.services.activity_service import ActivityLogService


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

                activity_by_id = {activity.id: activity for activity in activities}
                selected_id = st.selectbox(
                    "Select an activity record",
                    options=list(activity_by_id),
                    format_func=lambda activity_id: (
                        f"{activity_by_id[activity_id].action} (#{activity_id})"
                    ),
                    key="activity_selected_id",
                )
                selected = service.get_activity(selected_id)
                if selected is None:
                    st.warning("The selected activity record could not be found.")
                    return

                st.subheader("Activity details")
                st.write(f"Action: {selected.action}")
                st.write(f"Entity type: {selected.entity_type or 'Not provided'}")
                st.write(f"Entity ID: {selected.entity_id or 'Not provided'}")
                st.write(
                    f"Created: {selected.created_at.isoformat()}"
                    if selected.created_at is not None
                    else "Created: Not available"
                )
                st.text_area(
                    "Details",
                    value=selected.details or "Not provided",
                    height=180,
                    disabled=True,
                    key=f"activity_details_{selected.id}",
                )
    except Exception:
        st.error("Activity records could not be loaded. Please try again.")
