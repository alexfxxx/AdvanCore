"""Isolated validation tests for the Alembic migration foundation.

These tests do not connect to or mutate any real database. They verify that
Alembic configuration, metadata discovery, and the baseline migration script
are wired correctly and contain only expected schema operations.
"""

import ast
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from alembic.config import Config

from advancore.models import Base


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"
ALEMBIC_DIR = PROJECT_ROOT / "alembic"
ENV_PY = ALEMBIC_DIR / "env.py"


def test_alembic_ini_exists_and_loads():
    """The Alembic configuration file is present and parseable."""
    assert ALEMBIC_INI.exists()
    config = Config(str(ALEMBIC_INI))
    script_location = config.get_main_option("script_location")
    assert script_location.endswith("/alembic")


def test_alembic_env_target_metadata_matches_base():
    """env.py exposes the AdvanCore SQLAlchemy metadata as target_metadata."""
    # Import env.py in a controlled way so its migration runner block does not
    # attempt to connect to a real database.
    with patch("alembic.context") as mock_context:
        mock_context.is_offline_mode.return_value = True
        mock_context.config = MagicMock()
        mock_context.config.config_file_name = None

        spec = importlib.util.spec_from_file_location("alembic_env", ENV_PY)
        env_module = importlib.util.module_from_spec(spec)
        sys.modules["alembic_env"] = env_module
        spec.loader.exec_module(env_module)

    assert env_module.target_metadata is Base.metadata


def _migration_file(pattern: str) -> Path:
    """Return the one migration matching an explicit semantic filename."""
    versions_dir = ALEMBIC_DIR / "versions"
    assert versions_dir.exists(), "Alembic versions directory is missing"
    revision_files = list(versions_dir.glob(pattern))
    assert len(revision_files) == 1, (
        f"Expected one migration matching {pattern}, found {revision_files}"
    )
    return revision_files[0]


def test_baseline_migration_creates_expected_tables():
    """The baseline migration creates the four existing AdvanCore tables."""
    baseline = _migration_file("*_baseline.py")
    source = baseline.read_text()
    tree = ast.parse(source)

    created_tables = {
        (call := node).args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "create_table"
        and len(node.args) >= 1
        and isinstance(node.args[0], ast.Constant)
    }

    assert created_tables == {
        "activity_logs",
        "projects",
        "system_settings",
        "knowledge_items",
    }


def test_baseline_migration_upgrade_has_no_destructive_operations():
    """The baseline upgrade does not drop tables, columns, or indexes."""
    baseline = _migration_file("*_baseline.py")
    source = baseline.read_text()
    tree = ast.parse(source)

    destructive_calls = {
        "drop_table",
        "drop_column",
        "drop_index",
        "drop_constraint",
    }

    upgrade_calls = []
    in_upgrade = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
            in_upgrade = True
            upgrade_node = node
            break

    assert in_upgrade, "upgrade() function not found in baseline migration"

    for child in ast.walk(upgrade_node):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
            if child.func.attr in destructive_calls:
                upgrade_calls.append(child.func.attr)

    assert not upgrade_calls, (
        f"Baseline upgrade contains destructive operations: {upgrade_calls}"
    )


def test_knowledge_approval_migration_adds_only_nullable_fields_and_checks():
    migration_path = _migration_file("*_knowledge_approval_foundation.py")
    spec = importlib.util.spec_from_file_location(
        "knowledge_approval_migration", migration_path
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.down_revision == "639d8b65223c"
    mock_op = MagicMock()
    migration.op = mock_op
    migration.upgrade()

    added_columns = {
        call.args[1].name: call.args[1]
        for call in mock_op.add_column.call_args_list
    }
    assert set(added_columns) == {"approved_at", "approved_by"}
    assert all(column.nullable is True for column in added_columns.values())
    assert added_columns["approved_at"].type.timezone is True
    assert added_columns["approved_by"].type.length == 100

    constraint_names = {
        call.args[0] for call in mock_op.create_check_constraint.call_args_list
    }
    assert constraint_names == {
        "ck_knowledge_items_approval_fields_paired",
        "ck_knowledge_items_approved_has_metadata",
        "ck_knowledge_items_draft_unapproved",
        "ck_knowledge_items_approver_nonblank",
    }
    mock_op.drop_table.assert_not_called()
    mock_op.drop_column.assert_not_called()
    mock_op.drop_constraint.assert_not_called()
    mock_op.alter_column.assert_not_called()
    mock_op.execute.assert_not_called()
