"""Deterministic tests for the bounded DashboardService."""

from types import SimpleNamespace

from advancore.services.dashboard_service import DashboardService, DashboardSummary


class FakeRepository:
    def __init__(self, statuses=()):
        self.items = [SimpleNamespace(status=status) for status in statuses]
        self.list_calls = 0

    def list(self):
        self.list_calls += 1
        return list(self.items)


def test_empty_summary_is_all_zero():
    summary = DashboardService(
        FakeRepository(), FakeRepository(), FakeRepository()
    ).get_summary()
    assert summary == DashboardSummary(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)


def test_populated_summary_counts_known_and_other_statuses():
    projects = FakeRepository(["active", "active", "archived", "unexpected"])
    knowledge = FakeRepository(["draft", "draft", "approved", "unexpected"])
    activity = FakeRepository(["ignored"] * 4)
    activity.items = [
        SimpleNamespace(entity_type="project"),
        SimpleNamespace(entity_type="project"),
        SimpleNamespace(entity_type="knowledge"),
        SimpleNamespace(entity_type="legacy"),
    ]
    summary = DashboardService(projects, knowledge, activity).get_summary()
    assert summary == DashboardSummary(
        total_projects=4,
        active_projects=2,
        archived_projects=1,
        other_projects=1,
        total_knowledge=4,
        draft_knowledge=2,
        other_knowledge=2,
        total_activity=4,
        project_activity=2,
        knowledge_activity=1,
        other_activity=1,
    )
    assert projects.list_calls == knowledge.list_calls == activity.list_calls == 1


def test_summary_is_immutable():
    summary = DashboardSummary(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    try:
        summary.total_projects = 1
    except AttributeError:
        pass
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("DashboardSummary must be immutable")
