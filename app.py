import streamlit as st

from advancore.config import APP_TITLE
from advancore.pages import (
    dashboard,
    knowledge_hub,
    projects,
    ai_center,
    activity_log,
    settings,
)


st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🧠",
    layout="wide",
)

st.title(APP_TITLE)
st.caption("Business Intelligence and Operations Platform")

page = st.sidebar.radio(
    "Navigation",
    [
        "Dashboard",
        "Knowledge Hub",
        "Projects",
        "AI Center",
        "Activity Log",
        "Settings",
    ],
)

if page == "Dashboard":
    dashboard.render()

elif page == "Knowledge Hub":
    knowledge_hub.render()

elif page == "Projects":
    projects.render()

elif page == "AI Center":
    ai_center.render()

elif page == "Activity Log":
    activity_log.render()

elif page == "Settings":
    settings.render()