"""Fail-closed publication of fully reviewed operational import batches."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from advancore.services.operational_import_review_service import (
    OperationalImportReview,
)


class ImportPublicationError(ValueError):
    """Raised before publication when a batch is not safely publishable."""


@dataclass(frozen=True)
class ImportPublicationResult:
    dataset_type: str
    published_count: int


def publish_import(
    review: OperationalImportReview,
    *,
    confirmed: bool,
    create_record: Callable[[dict[str, str | None]], object],
) -> ImportPublicationResult:
    """Create every reviewed row or fail before starting the batch."""
    if not confirmed:
        raise ImportPublicationError("Explicit operator confirmation is required.")
    if not review.rows:
        raise ImportPublicationError("The reviewed batch contains no rows to publish.")
    if any(not row.publishable for row in review.rows):
        raise ImportPublicationError(
            "Every row must be ready before the batch can be published."
        )

    for row in review.rows:
        create_record(dict(row.preview_row.values))
    return ImportPublicationResult(
        dataset_type=review.dataset_type,
        published_count=len(review.rows),
    )
