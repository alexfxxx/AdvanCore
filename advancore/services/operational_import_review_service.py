"""Read-only review classification for operational CSV previews."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from advancore.services.operational_import_service import (
    ImportRowPreview,
    OperationalImportPreview,
)


REVIEW_READY = "ready"
REVIEW_INVALID = "invalid"
REVIEW_DUPLICATE_FILE = "duplicate_in_file"
REVIEW_ALREADY_EXISTS = "already_exists"
REVIEW_DUPLICATE_FILE_AND_EXISTS = "duplicate_in_file_and_already_exists"

_IDENTITY_FIELDS = {
    "vehicles": "registration_number",
    "drivers": "employee_reference",
    "customers": "customer_reference",
    "routes": "route_code",
}


@dataclass(frozen=True)
class ImportReviewRow:
    preview_row: ImportRowPreview
    status: str
    message: str

    @property
    def publishable(self) -> bool:
        return self.status == REVIEW_READY


@dataclass(frozen=True)
class OperationalImportReview:
    dataset_type: str
    rows: tuple[ImportReviewRow, ...]

    def count(self, status: str) -> int:
        return sum(row.status == status for row in self.rows)

    @property
    def publishable_count(self) -> int:
        return self.count(REVIEW_READY)


def _identity(dataset_type: str, row: ImportRowPreview) -> str | None:
    field = _IDENTITY_FIELDS[dataset_type]
    value = row.values.get(field)
    return value if isinstance(value, str) and value else None


def review_import(
    preview: OperationalImportPreview,
    existing_identities: set[str] | frozenset[str],
) -> OperationalImportReview:
    """Classify preview rows using only exact normalized identity values."""
    normalized_existing = frozenset(existing_identities)
    identities = [
        _identity(preview.dataset_type, row)
        for row in preview.rows
        if row.is_valid
    ]
    counts = Counter(identity for identity in identities if identity is not None)
    reviewed: list[ImportReviewRow] = []

    for row in preview.rows:
        identity = _identity(preview.dataset_type, row)
        if not row.is_valid:
            status = REVIEW_INVALID
            message = "Correct validation errors before publication."
        elif (
            identity is not None
            and counts[identity] > 1
            and identity in normalized_existing
        ):
            status = REVIEW_DUPLICATE_FILE_AND_EXISTS
            message = (
                "This exact identifier appears more than once in the uploaded file "
                "and already exists."
            )
        elif identity is not None and counts[identity] > 1:
            status = REVIEW_DUPLICATE_FILE
            message = "This exact identifier appears more than once in the uploaded file."
        elif identity is not None and identity in normalized_existing:
            status = REVIEW_ALREADY_EXISTS
            message = "This exact identifier already exists and will not be recreated."
        else:
            status = REVIEW_READY
            message = "Ready for later governed publication."
        reviewed.append(ImportReviewRow(preview_row=row, status=status, message=message))

    return OperationalImportReview(dataset_type=preview.dataset_type, rows=tuple(reviewed))
