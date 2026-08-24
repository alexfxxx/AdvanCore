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
from advancore.ui.theme import apply_command_center_theme


st.set_page_config(
    page_title=APP_TITLE,
    layout="wide",
)

apply_command_center_theme(st)

st.title("ADVANCORE")
st.caption(f"Executive Command Center · {APP_TITLE}")

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
