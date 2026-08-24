"""Knowledge Hub application service for bounded draft capture and viewing."""

from collections.abc import Sequence

from advancore.models import KnowledgeItem
from advancore.repositories import KnowledgeItemRepository
from advancore.services.activity_service import ActivityLogService


class KnowledgeValidationError(ValueError):
    """Raised when submitted draft knowledge is invalid."""


class KnowledgeNotFoundError(ValueError):
    """Raised when a selected knowledge item no longer exists."""


class KnowledgeReadOnlyError(ValueError):
    """Raised when an item cannot be changed in its lifecycle state."""


class KnowledgeAlreadyArchivedError(ValueError):
    """Raised when an archived item is archived again."""


class KnowledgeService:
    """Application service for the first draft-only Knowledge Hub slice."""

    def __init__(
        self,
        knowledge_repository: KnowledgeItemRepository,
        activity_service: ActivityLogService | None = None,
    ):
        self._repo = knowledge_repository
        self._activity_service = activity_service

    def _record_activity(self, action: str, item_id: int) -> None:
        if self._activity_service is not None:
            self._activity_service.record_activity(action, "knowledge", item_id)

    @staticmethod
    def _normalize_fields(title: str, content: str) -> tuple[str, str]:
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
        return normalized_title, normalized_content

    def create_draft(self, title: str, content: str) -> KnowledgeItem:
        """Validate, normalize, and persist one unlinked draft item."""
        normalized_title, normalized_content = self._normalize_fields(title, content)

        saved = self._repo.add(
            KnowledgeItem(
                title=normalized_title,
                content=normalized_content,
                status="draft",
                project_id=None,
                source_type=None,
                source_reference=None,
            )
        )
        self._record_activity("knowledge_created", saved.id)
        return saved

    def edit_draft(self, item_id: int, title: str, content: str) -> KnowledgeItem:
        """Validate and persist edits to one draft item."""
        item = self._repo.get_by_id(item_id)
        if item is None:
            raise KnowledgeNotFoundError(
                "The selected knowledge item could not be found."
            )
        if item.status != "draft":
            raise KnowledgeReadOnlyError(
                "This knowledge item is read-only and cannot be edited."
            )
        normalized_title, normalized_content = self._normalize_fields(title, content)
        previous = (item.title, item.content)
        item.title = normalized_title
        item.content = normalized_content
        try:
            saved = self._repo.save(item)
        except Exception:
            item.title, item.content = previous
            raise
        try:
            self._record_activity("knowledge_updated", saved.id)
        except Exception:
            item.title, item.content = previous
            raise
        return saved

    def archive_draft(self, item_id: int) -> KnowledgeItem:
        """Persist the one-way draft-to-archived lifecycle transition."""
        item = self._repo.get_by_id(item_id)
        if item is None:
            raise KnowledgeNotFoundError(
                "The selected knowledge item could not be found."
            )
        if item.status == "archived":
            raise KnowledgeAlreadyArchivedError(
                "This knowledge item is already archived."
            )
        if item.status != "draft":
            raise KnowledgeReadOnlyError(
                "This knowledge item has an unsupported status and cannot be archived."
            )
        item.status = "archived"
        try:
            saved = self._repo.save(item)
        except Exception:
            item.status = "draft"
            raise
        try:
            self._record_activity("knowledge_archived", saved.id)
        except Exception:
            item.status = "draft"
            raise
        return saved

    def get_item(self, item_id: int) -> KnowledgeItem | None:
        """Return one knowledge item by identifier."""
        return self._repo.get_by_id(item_id)

    def list_items(self) -> Sequence[KnowledgeItem]:
        """Return all knowledge items in repository order."""
        return self._repo.list()
