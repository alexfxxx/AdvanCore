import streamlit as st
from advancore.services.database import test_database_connection

def render():
    st.subheader("Platform Status")

    st.success("Core application shell operational.")

    if test_database_connection():
        st.success("Database connected.")
    else:
        st.error("Database not connected.")