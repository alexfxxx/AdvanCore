"""Tests for TASK-046 bounded unattended review/repair."""

from unittest.mock import Mock

from advancore.agent_runner.standing_authority import RoutineAction
from advancore.agent_runner.unattended_review import (
    IndependentReviewResult,
    RepairResult,
    UnattendedReviewStatus,
    run_unattended_review_loop,
)


class Authority:
    def __init__(self, fail_on=None):
        self.actions = []
        self.fail_on = fail_on

    def consume(self, task_id, branch, action):
        from advancore.agent_runner.standing_authority import StandingAuthorityError

        self.actions.append((task_id, branch, action))
        if action == self.fail_on:
            raise StandingAuthorityError("manual authority required")


def review(clean, count=0, repairable=False, summary="reviewed"):
    return IndependentReviewResult(clean, count, repairable, summary)


def test_clean_review_never_repairs_or_approves():
    authority = Authority()
    repairer = Mock()
    result = run_unattended_review_loop(
        task_id="TASK-046",
        branch="feature",
        authority=authority,
        reviewer=lambda: review(True),
        repairer=repairer,
    )
    assert result.status == UnattendedReviewStatus.CLEAN
    assert result.reviews == 1 and result.repairs == 0
    assert result.manual_approval_required is True
    repairer.assert_not_called()
    assert [item[2] for item in authority.actions] == [RoutineAction.INDEPENDENT_REVIEW]


def test_repairs_are_followed_by_fresh_review_until_clean():
    authority = Authority()
    reviews = iter([review(False, 2, True), review(False, 1, True), review(True)])
    repairer = Mock(return_value=RepairResult(True, "repaired"))
    result = run_unattended_review_loop(
        task_id="TASK-046",
        branch="feature",
        authority=authority,
        reviewer=lambda: next(reviews),
        repairer=repairer,
    )
    assert result.status == UnattendedReviewStatus.CLEAN
    assert (result.reviews, result.repairs) == (3, 2)
    assert repairer.call_count == 2


def test_budget_exhaustion_stops_without_extra_repair():
    authority = Authority()
    repairer = Mock(return_value=RepairResult(True, "repaired"))
    result = run_unattended_review_loop(
        task_id="TASK-046",
        branch="feature",
        authority=authority,
        reviewer=lambda: review(False, 1, True),
        repairer=repairer,
        max_repairs=2,
    )
    assert result.status == UnattendedReviewStatus.REPAIR_EXHAUSTED
    assert (result.reviews, result.repairs) == (3, 2)
    assert repairer.call_count == 2


def test_nonrepairable_and_authority_failures_require_manual_attention():
    nonrepairable = run_unattended_review_loop(
        task_id="TASK-046",
        branch="feature",
        authority=Authority(),
        reviewer=lambda: review(False, 1, False),
        repairer=Mock(),
    )
    assert nonrepairable.status == UnattendedReviewStatus.MANUAL_REVIEW_REQUIRED

    blocked = run_unattended_review_loop(
        task_id="TASK-046",
        branch="feature",
        authority=Authority(RoutineAction.BOUNDED_REPAIR),
        reviewer=lambda: review(False, 1, True),
        repairer=Mock(),
    )
    assert blocked.status == UnattendedReviewStatus.AUTHORITY_BLOCKED


def test_malformed_and_failed_tools_stop_safely():
    malformed = run_unattended_review_loop(
        task_id="TASK-046",
        branch="feature",
        authority=Authority(),
        reviewer=lambda: object(),
        repairer=Mock(),
    )
    assert malformed.status == UnattendedReviewStatus.REVIEW_FAILED

    failed = run_unattended_review_loop(
        task_id="TASK-046",
        branch="feature",
        authority=Authority(),
        reviewer=lambda: review(False, 1, True),
        repairer=lambda _review: RepairResult(False, "cannot repair"),
    )
    assert failed.status == UnattendedReviewStatus.REPAIR_FAILED


def test_malformed_typed_fields_and_summary_objects_never_escape():
    malformed_reviews = [
        IndependentReviewResult(True, 0, True, "clean cannot be repairable"),
        IndependentReviewResult(True, 0, False, None),
        IndependentReviewResult(False, 1, True, object()),
        IndependentReviewResult(False, True, True, "boolean count"),
    ]
    for evidence in malformed_reviews:
        result = run_unattended_review_loop(
            task_id="TASK-046",
            branch="feature",
            authority=Authority(),
            reviewer=lambda evidence=evidence: evidence,
            repairer=Mock(),
        )
        assert result.status == UnattendedReviewStatus.REVIEW_FAILED

    malformed_repair = run_unattended_review_loop(
        task_id="TASK-046",
        branch="feature",
        authority=Authority(),
        reviewer=lambda: review(False, 1, True),
        repairer=lambda _review: RepairResult(True, None),
    )
    assert malformed_repair.status == UnattendedReviewStatus.REPAIR_FAILED
