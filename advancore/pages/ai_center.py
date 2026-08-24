from pathlib import Path

import streamlit as st

from advancore.agent_runner.orchestration_inbox import build_orchestration_inbox


def render(repo_root: Path | None = None):
    st.header("AI Center")
    st.caption("Automation runs independently and pauses only when attention is required.")
    root = (repo_root or Path.cwd()).resolve()
    try:
        inbox = build_orchestration_inbox(root)
    except Exception:
        st.warning("Automation status is unavailable. Local controller inspection is required.")
        return

    st.subheader("Needs your attention")
    if not inbox.entries:
        st.success("No owner decisions or automation investigations are waiting.")
        return

    decision_count = sum(entry.owner_decision_required for entry in inbox.entries)
    st.metric("Waiting items", len(inbox.entries))
    st.metric("Owner decisions", decision_count)
    for entry in inbox.entries:
        label = entry.task_title or entry.task_id or "Automation run"
        with st.expander(label):
            st.write(f"Status: {entry.status}")
            st.write(entry.reason)
            if entry.owner_decision_required:
                st.warning("Your decision is required before this work can continue.")
            else:
                st.info("The local controller must investigate this item.")
