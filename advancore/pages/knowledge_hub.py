"""Streamlit presentation for bounded draft knowledge capture and viewing."""

from collections.abc import Iterator
from contextlib import contextmanager
import hashlib

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
_KNOWLEDGE_SELECTED_VALUE_KEY = "knowledge_selected_value"
_KNOWLEDGE_SELECTBOX_PREFIX = "knowledge_selected_id_"
_KNOWLEDGE_CREATE_GENERATION_KEY = "knowledge_create_generation"
_KNOWLEDGE_SUCCESS_MESSAGES = frozenset(
    {
        "Knowledge draft created successfully.",
        "Knowledge draft updated successfully.",
        "Knowledge draft archived successfully.",
    }
)


@contextmanager
def _knowledge_service() -> Iterator[KnowledgeService]:
    """Provide a KnowledgeService inside the established unit of work."""
    from advancore.services.database import session_scope

    with session_scope() as session:
        yield KnowledgeService(KnowledgeItemRepository(session))


def _create_draft(title: str, content: str) -> int | None:
    """Create one draft and render a presentation-safe outcome."""
    try:
        with _knowledge_service() as service:
            created = service.create_draft(title, content)
            created_id = created.id
    except KnowledgeValidationError as exc:
        st.error(str(exc))
        return None
    except Exception:
        st.error("Knowledge draft creation failed. Please try again.")
        return None
    return created_id


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


def _content_widget_key(item_id: int, content: str) -> str:
    """Return a stable, non-plaintext identity for the saved content value."""
    content_digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
    return f"knowledge_content_{item_id}_{content_digest}"


def _clear_superseded_content_state(item_id: int, current_key: str) -> None:
    """Discard old detail widgets before rendering the current saved value."""
    prefix = f"knowledge_content_{item_id}_"
    for key in tuple(st.session_state):
        if key.startswith(prefix) and key != current_key:
            st.session_state.pop(key, None)


def _selection_widget_key(items: list) -> str:
    """Version the selector from its current saved user-facing labels."""
    label_material = "\n".join(
        f"{item.id}\0{item.title}\0{item.status}" for item in items
    )
    label_digest = hashlib.sha256(label_material.encode("utf-8")).hexdigest()[:12]
    return f"{_KNOWLEDGE_SELECTBOX_PREFIX}{label_digest}"


def _clear_superseded_selection_state(current_key: str) -> None:
    """Discard stale selector widgets while retaining the selected value."""
    for key in tuple(st.session_state):
        if key == "knowledge_selected_id" or (
            key.startswith(_KNOWLEDGE_SELECTBOX_PREFIX) and key != current_key
        ):
            st.session_state.pop(key, None)


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
                item_ids = list(item_by_id)
                selection_widget_key = _selection_widget_key(items)
                _clear_superseded_selection_state(selection_widget_key)
                preferred_id = st.session_state.get(_KNOWLEDGE_SELECTED_VALUE_KEY)
                selected_index = (
                    item_ids.index(preferred_id) if preferred_id in item_by_id else 0
                )
                selected_id = st.selectbox(
                    "Select a knowledge item",
                    options=item_ids,
                    index=selected_index,
                    format_func=lambda item_id: (
                        f"{item_by_id[item_id].title} ({item_by_id[item_id].status})"
                    ),
                    key=selection_widget_key,
                )
                st.session_state[_KNOWLEDGE_SELECTED_VALUE_KEY] = selected_id
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
                content_widget_key = _content_widget_key(
                    selected.id, selected.content
                )
                _clear_superseded_content_state(
                    selected.id, content_widget_key
                )
                st.text_area(
                    "Content",
                    value=selected.content,
                    height=240,
                    disabled=True,
                    key=content_widget_key,
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
    create_generation = int(
        st.session_state.get(_KNOWLEDGE_CREATE_GENERATION_KEY, 0)
    )
    create_title_key = f"knowledge_create_title_{create_generation}"
    create_content_key = f"knowledge_create_content_{create_generation}"
    with st.form("create_knowledge_draft"):
        title = st.text_input(
            "Title", max_chars=300, key=create_title_key
        )
        content = st.text_area(
            "Content", height=180, key=create_content_key
        )
        submitted = st.form_submit_button("Create draft", type="primary")
    if submitted:
        created_id = _create_draft(title, content)
        if created_id is not None:
            st.session_state[_KNOWLEDGE_SELECTED_VALUE_KEY] = created_id
            st.session_state[_KNOWLEDGE_CREATE_GENERATION_KEY] = (
                create_generation + 1
            )
            _refresh_with_success(
                "Knowledge draft created successfully.",
                clear_session_keys=(
                    create_title_key,
                    create_content_key,
                ),
            )

    _render_items()
