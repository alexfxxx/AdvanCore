"""Knowledge Hub application service for bounded draft capture and viewing."""

from collections.abc import Sequence

from advancore.models import KnowledgeItem
from advancore.repositories import KnowledgeItemRepository


class KnowledgeValidationError(ValueError):
    """Raised when submitted draft knowledge is invalid."""


class KnowledgeService:
    """Application service for the first draft-only Knowledge Hub slice."""

    def __init__(self, knowledge_repository: KnowledgeItemRepository):
        self._repo = knowledge_repository

    def create_draft(self, title: str, content: str) -> KnowledgeItem:
        """Validate, normalize, and persist one unlinked draft item."""
        normalized_title = title.strip()
        normalized_content = content.strip()
        if not normalized_title:
            raise KnowledgeValidationError("Knowledge title is required.")
        if len(normalized_title) > 300:
            raise KnowledgeValidationError(
                "Knowledge title must be 300 characters or fewer."
            )
        if not normalized_content:
            raise KnowledgeValidationError("Knowledge content is required.")

        return self._repo.add(
            KnowledgeItem(
                title=normalized_title,
                content=normalized_content,
                status="draft",
                project_id=None,
                source_type=None,
                source_reference=None,
            )
        )

    def get_item(self, item_id: int) -> KnowledgeItem | None:
        """Return one knowledge item by identifier."""
        return self._repo.get_by_id(item_id)

    def list_items(self) -> Sequence[KnowledgeItem]:
        """Return all knowledge items in repository order."""
        return self._repo.list()
