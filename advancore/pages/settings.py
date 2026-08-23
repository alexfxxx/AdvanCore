"""Read-only local application readiness page."""

import os

import streamlit as st
from dotenv import load_dotenv

from advancore.config import APP_NAME, APP_VERSION
from advancore.services.readiness_service import ReadinessService


def _readiness_service() -> ReadinessService:
    load_dotenv()
    database_configured = bool(os.getenv("DATABASE_URL"))
    if not database_configured:
        return ReadinessService(False)

    try:
        from advancore.services.database import test_database_connection
    except Exception:
        return ReadinessService(True)

    return ReadinessService(True, test_database_connection)


def render():
    st.header("Settings")
    st.write("Read-only local setup status. No credentials or values are shown.")

    st.subheader("Application")
    st.write(f"Name: {APP_NAME}")
    st.write(f"Version: {APP_VERSION}")

    st.subheader("Database")
    with st.spinner("Checking local readiness..."):
        summary = _readiness_service().get_summary()

    if not summary.database_configured:
        st.warning(
            "Database is not configured. Follow the Local quick start in README.md."
        )
    elif summary.database_available:
        st.success("Database is configured and available.")
    else:
        st.error(
            "Database is configured but unavailable. Check that the local database "
            "is running, then try again."
        )

    st.caption(
        "Configuration remains file- and environment-managed; this page is read-only."
    )
