import streamlit as st

from advancore.config import APP_TITLE
from advancore.pages import (
    dashboard,
    knowledge_hub,
    projects,
    ai_center,
    activity_log,
    settings,
    operations,
)
from advancore.ui.theme import apply_command_center_theme
from advancore.module_registry import streamlit_navigation


st.set_page_config(
    page_title=APP_TITLE,
    layout="wide",
)

apply_command_center_theme(st)

st.title("ADVANCORE")
st.caption(f"Executive Command Center · {APP_TITLE}")

_PAGE_RENDERERS = {
    "dashboard": dashboard.render,
    "knowledge_hub": knowledge_hub.render,
    "projects": projects.render,
    "transport_operations": operations.render,
    "ai_center": ai_center.render,
    "activity_log": activity_log.render,
    "settings": settings.render,
}
_NAVIGATION = streamlit_navigation()
_PAGE_BY_LABEL = {label: module_id for module_id, label in _NAVIGATION}
page = st.sidebar.radio("Navigation", [label for _module_id, label in _NAVIGATION])

_PAGE_RENDERERS[_PAGE_BY_LABEL[page]]()
