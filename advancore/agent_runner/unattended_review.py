"""Provider-neutral bounded independent-review and repair coordination."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable

from advancore.agent_runner.standing_authority import (
    RoutineAction,
    StandingAuthorityError,
    StandingAuthorityService,
)


MAX_REVIEW_REPAIR_CYCLES = 3
MAX_SUMMARY_LENGTH = 240


class UnattendedReviewStatus(str, Enum):
    CLEAN = "clean"
    REPAIR_EXHAUSTED = "repair-exhausted"
    MANUAL_REVIEW_REQUIRED = "manual-review-required"
    REVIEW_FAILED = "review-failed"
    REPAIR_FAILED = "repair-failed"
    AUTHORITY_BLOCKED = "authority-blocked"


@dataclass(frozen=True)
class IndependentReviewResult:
    clean: bool
    findings_count: int
    repairable: bool
    summary: str


@dataclass(frozen=True)
class RepairResult:
    success: bool
    summary: str


@dataclass(frozen=True)
class UnattendedReviewResult:
    status: UnattendedReviewStatus
    reviews: int
    repairs: int
    findings_count: int | None
    summary: str
    manual_approval_required: bool


def _summary(value: object) -> str:
    text = " ".join(str(value).split())
    if not text:
        return "No bounded summary was supplied."
    return text[:MAX_SUMMARY_LENGTH]


def _valid_review(value: object) -> bool:
    return (
        isinstance(value, IndependentReviewResult)
        and isinstance(value.clean, bool)
        and isinstance(value.repairable, bool)
        and isinstance(value.findings_count, int)
        and not isinstance(value.findings_count, bool)
        and value.findings_count >= 0
        and bool(value.clean) == (value.findings_count == 0)
        and (value.clean or value.repairable or not value.repairable)
    )


def run_unattended_review_loop(
    *,
    task_id: str,
    branch: str,
    authority: StandingAuthorityService,
    reviewer: Callable[[], IndependentReviewResult],
    repairer: Callable[[IndependentReviewResult], RepairResult],
    max_repairs: int = MAX_REVIEW_REPAIR_CYCLES,
) -> UnattendedReviewResult:
    """Run fresh review after each bounded routine repair; never approve work."""
    if isinstance(max_repairs, bool) or not isinstance(max_repairs, int):
        max_repairs = 0
    max_repairs = max(0, min(max_repairs, MAX_REVIEW_REPAIR_CYCLES))
    reviews = 0
    repairs = 0
    latest_findings: int | None = None
    while True:
        try:
            authority.consume(task_id, branch, RoutineAction.INDEPENDENT_REVIEW)
        except StandingAuthorityError as exc:
            return UnattendedReviewResult(
                UnattendedReviewStatus.AUTHORITY_BLOCKED,
                reviews,
                repairs,
                latest_findings,
                _summary(exc),
                True,
            )
        try:
            review = reviewer()
        except Exception as exc:
            return UnattendedReviewResult(
                UnattendedReviewStatus.REVIEW_FAILED,
                reviews + 1,
                repairs,
                latest_findings,
                f"Independent reviewer failed: {type(exc).__name__}",
                True,
            )
        reviews += 1
        if not _valid_review(review):
            return UnattendedReviewResult(
                UnattendedReviewStatus.REVIEW_FAILED,
                reviews,
                repairs,
                latest_findings,
                "Independent reviewer returned malformed bounded evidence.",
                True,
            )
        latest_findings = review.findings_count
        if review.clean:
            return UnattendedReviewResult(
                UnattendedReviewStatus.CLEAN,
                reviews,
                repairs,
                0,
                _summary(review.summary),
                True,
            )
        if not review.repairable:
            return UnattendedReviewResult(
                UnattendedReviewStatus.MANUAL_REVIEW_REQUIRED,
                reviews,
                repairs,
                review.findings_count,
                _summary(review.summary),
                True,
            )
        if repairs >= max_repairs:
            return UnattendedReviewResult(
                UnattendedReviewStatus.REPAIR_EXHAUSTED,
                reviews,
                repairs,
                review.findings_count,
                _summary(review.summary),
                True,
            )
        try:
            authority.consume(task_id, branch, RoutineAction.BOUNDED_REPAIR)
        except StandingAuthorityError as exc:
            return UnattendedReviewResult(
                UnattendedReviewStatus.AUTHORITY_BLOCKED,
                reviews,
                repairs,
                review.findings_count,
                _summary(exc),
                True,
            )
        try:
            repair = repairer(review)
        except Exception as exc:
            return UnattendedReviewResult(
                UnattendedReviewStatus.REPAIR_FAILED,
                reviews,
                repairs + 1,
                review.findings_count,
                f"Repair worker failed: {type(exc).__name__}",
                True,
            )
        repairs += 1
        if not isinstance(repair, RepairResult) or not isinstance(repair.success, bool):
            return UnattendedReviewResult(
                UnattendedReviewStatus.REPAIR_FAILED,
                reviews,
                repairs,
                review.findings_count,
                "Repair worker returned malformed bounded evidence.",
                True,
            )
        if not repair.success:
            return UnattendedReviewResult(
                UnattendedReviewStatus.REPAIR_FAILED,
                reviews,
                repairs,
                review.findings_count,
                _summary(repair.summary),
                True,
            )

