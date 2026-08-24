"""Streamlit presentation for bounded draft knowledge capture and viewing."""

from collections.abc import Iterator
from contextlib import contextmanager

import streamlit as st

from advancore.repositories import KnowledgeItemRepository
from advancore.services.knowledge_service import (
    KnowledgeAlreadyArchivedError,
    KnowledgeNotFoundError,
    KnowledgeReadOnlyError,
    KnowledgeService,
    KnowledgeValidationError,
)


_KNOWLEDGE_FLASH_KEY = "knowledge_success_notice"
_KNOWLEDGE_SUCCESS_MESSAGES = frozenset(
    {"Knowledge draft updated successfully.", "Knowledge draft archived successfully."}
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


def _edit_draft(item_id: int, title: str, content: str) -> bool:
    try:
        with _knowledge_service() as service:
            service.edit_draft(item_id, title, content)
    except KnowledgeValidationError as exc:
        st.error(str(exc))
        return False
    except (KnowledgeNotFoundError, KnowledgeReadOnlyError) as exc:
        st.warning(str(exc))
        return False
    except Exception:
        st.error("Knowledge draft update failed. Please try again.")
        return False
    return True


def _archive_draft(item_id: int) -> bool:
    try:
        with _knowledge_service() as service:
            service.archive_draft(item_id)
    except (
        KnowledgeNotFoundError,
        KnowledgeReadOnlyError,
        KnowledgeAlreadyArchivedError,
    ) as exc:
        st.warning(str(exc))
        return False
    except Exception:
        st.error("Knowledge draft archive failed. Please try again.")
        return False
    return True


def _refresh_with_success(
    message: str, *, clear_session_keys: tuple[str, ...] = ()
) -> None:
    if message not in _KNOWLEDGE_SUCCESS_MESSAGES:
        raise ValueError("Unsupported knowledge success notice")
    for key in clear_session_keys:
        st.session_state.pop(key, None)
    st.session_state[_KNOWLEDGE_FLASH_KEY] = message
    st.rerun()


def _render_success_notice() -> None:
    message = st.session_state.pop(_KNOWLEDGE_FLASH_KEY, None)
    if message in _KNOWLEDGE_SUCCESS_MESSAGES:
        st.success(message)


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

                if selected.status == "archived":
                    st.info("Archived knowledge draft — read-only.")
                    return
                if selected.status != "draft":
                    st.warning(
                        "This knowledge item has an unsupported status and is read-only."
                    )
                    return

                st.subheader("Edit knowledge draft")
                with st.form(f"edit_knowledge_{selected.id}"):
                    edited_title = st.text_input(
                        "Knowledge title",
                        value=selected.title,
                        max_chars=300,
                        key=f"knowledge_edit_title_{selected.id}",
                    )
                    edited_content = st.text_area(
                        "Knowledge content",
                        value=selected.content,
                        height=180,
                        key=f"knowledge_edit_content_{selected.id}",
                    )
                    edit_submitted = st.form_submit_button(
                        "Save changes", type="primary"
                    )
                if edit_submitted and _edit_draft(
                    selected.id, edited_title, edited_content
                ):
                    _refresh_with_success(
                        "Knowledge draft updated successfully.",
                        clear_session_keys=(
                            f"knowledge_edit_title_{selected.id}",
                            f"knowledge_edit_content_{selected.id}",
                            f"knowledge_content_{selected.id}",
                        ),
                    )

                st.subheader("Archive knowledge draft")
                with st.form(f"archive_knowledge_{selected.id}"):
                    archive_confirmed = st.checkbox(
                        "I confirm that this knowledge draft should be archived."
                    )
                    archive_submitted = st.form_submit_button(
                        "Archive knowledge draft"
                    )
                if archive_submitted:
                    if not archive_confirmed:
                        st.warning("Confirm archiving before submitting.")
                    elif _archive_draft(selected.id):
                        _refresh_with_success(
                            "Knowledge draft archived successfully."
                        )
    except Exception:
        st.error("Knowledge items could not be loaded. Please try again.")


def render():
    st.header("Knowledge Hub")
    st.write("Capture draft knowledge and review saved items.")
    _render_success_notice()

    st.subheader("Create knowledge draft")
    with st.form("create_knowledge_draft"):
        title = st.text_input("Title", max_chars=300)
        content = st.text_area("Content", height=180)
        submitted = st.form_submit_button("Create draft", type="primary")
    if submitted:
        _create_draft(title, content)

    _render_items()
