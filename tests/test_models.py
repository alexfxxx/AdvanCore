"""Smoke and metadata tests for the AdvanCore model foundation."""


def test_model_package_imports():
    """All public models and Base import successfully from advancore.models."""
    from advancore.models import (
        ActivityLog,
        Base,
        KnowledgeItem,
        Project,
        SystemSetting,
    )

    assert Base is not None
    assert Project is not None
    assert KnowledgeItem is not None
    assert ActivityLog is not None
    assert SystemSetting is not None


def test_expected_model_tables_registered():
    """The four existing model tables are present in Base.metadata."""
    from advancore.models import Base

    table_names = set(Base.metadata.tables.keys())

    assert "projects" in table_names
    assert "knowledge_items" in table_names
    assert "activity_logs" in table_names
    assert "system_settings" in table_names
