"""Streamlit presentation for bounded draft knowledge capture and viewing."""

from collections.abc import Iterator
from contextlib import contextmanager

import streamlit as st

from advancore.repositories import KnowledgeItemRepository
from advancore.services.knowledge_service import (
    KnowledgeService,
    KnowledgeValidationError,
)


@contextmanager
def _knowledge_service() -> Iterator[KnowledgeService]:
    """Provide a KnowledgeService inside the established unit of work."""
    from advancore.services.database import session_scope

    with session_scope() as session:
        yield KnowledgeService(KnowledgeItemRepository(session))


def _create_draft(title: str, content: str) -> bool:
    """Create one draft and render a presentation-safe outcome."""
    try:
        with _knowledge_service() as service:
            service.create_draft(title, content)
    except KnowledgeValidationError as exc:
        st.error(str(exc))
        return False
    except Exception:
        st.error("Knowledge draft creation failed. Please try again.")
        return False
    st.success("Knowledge draft created successfully.")
    return True


def _render_items() -> None:
    """Load and render the deterministic knowledge list and selected detail."""
    try:
        with st.spinner("Loading knowledge..."):
            with _knowledge_service() as service:
                items = list(service.list_items())
                if not items:
                    st.info("No knowledge drafts yet. Create the first draft above.")
                    return

                st.subheader("Knowledge list")
                item_by_id = {item.id: item for item in items}
                selected_id = st.selectbox(
                    "Select a knowledge item",
                    options=list(item_by_id),
                    format_func=lambda item_id: (
                        f"{item_by_id[item_id].title} ({item_by_id[item_id].status})"
                    ),
                    key="knowledge_selected_id",
                )
                selected = service.get_item(selected_id)
                if selected is None:
                    st.warning("The selected knowledge item could not be found.")
                    return

                st.subheader("Knowledge details")
                st.write(f"Title: {selected.title}")
                st.write(f"Status: {selected.status}")
                st.write(
                    f"Created: {selected.created_at.isoformat()}"
                    if selected.created_at is not None
                    else "Created: Not available"
                )
                st.text_area(
                    "Content",
                    value=selected.content,
                    height=240,
                    disabled=True,
                    key=f"knowledge_content_{selected.id}",
                )
    except Exception:
        st.error("Knowledge items could not be loaded. Please try again.")


def render():
    st.header("Knowledge Hub")
    st.write("Capture draft knowledge and review saved items.")

    st.subheader("Create knowledge draft")
    with st.form("create_knowledge_draft"):
        title = st.text_input("Title", max_chars=300)
        content = st.text_area("Content", height=180)
        submitted = st.form_submit_button("Create draft", type="primary")
    if submitted:
        _create_draft(title, content)

    _render_items()
