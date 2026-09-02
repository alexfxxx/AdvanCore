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


def test_knowledge_replacement_migration_adds_nullable_bounded_lineage():
    migration_path = _migration_file("*_knowledge_replacement_history.py")
    spec = importlib.util.spec_from_file_location(
        "knowledge_replacement_migration", migration_path
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.down_revision == "3f61b4a9c2d7"
    mock_op = MagicMock()
    migration.op = mock_op
    migration.upgrade()

    added_column = mock_op.add_column.call_args.args[1]
    assert added_column.name == "replaces_knowledge_item_id"
    assert added_column.nullable is True
    assert added_column.type.python_type is int

    foreign_key_call = mock_op.create_foreign_key.call_args
    assert foreign_key_call.args[:3] == (
        "fk_knowledge_items_replaces_knowledge_item_id",
        "knowledge_items",
        "knowledge_items",
    )
    assert foreign_key_call.args[3:] == (
        ["replaces_knowledge_item_id"],
        ["id"],
    )
    assert foreign_key_call.kwargs["ondelete"] == "RESTRICT"

    constraint_names = {
        call.args[0] for call in mock_op.create_check_constraint.call_args_list
    }
    assert constraint_names == {
        "ck_knowledge_items_not_self_replacing",
        "ck_knowledge_items_superseded_has_metadata",
    }
    index_call = mock_op.create_index.call_args
    assert index_call.args[:3] == (
        "uq_knowledge_items_open_replacement",
        "knowledge_items",
        ["replaces_knowledge_item_id"],
    )
    assert index_call.kwargs["unique"] is True
    assert "status <> 'archived'" in str(
        index_call.kwargs["postgresql_where"]
    )
    mock_op.drop_table.assert_not_called()
    mock_op.drop_column.assert_not_called()
    mock_op.drop_constraint.assert_not_called()
    mock_op.drop_index.assert_not_called()
    mock_op.alter_column.assert_not_called()
    mock_op.execute.assert_not_called()

def test_fleet_identity_migration_is_additive_nullable_and_at_current_head():
    migration_path = _migration_file("*_fleet_identity_current_cost.py")
    spec = importlib.util.spec_from_file_location("fleet_identity_migration", migration_path)
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    assert migration.down_revision == "d1e111fin"
    mock_op = MagicMock(); migration.op = mock_op; migration.upgrade()
    assert mock_op.create_table.call_args.args[0] == "legal_entities"
    added = [call.args[1] for call in mock_op.add_column.call_args_list]
    assert len(added) == 21
    assert all(column.nullable is True for column in added)
    mock_op.drop_table.assert_not_called(); mock_op.drop_column.assert_not_called(); mock_op.execute.assert_not_called()


def test_recurring_service_migration_constraints_reference_real_columns():
    migration_path = _migration_file("*recurring_customer_services.py")
    spec = importlib.util.spec_from_file_location(
        "recurring_service_migration", migration_path
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    mock_op = MagicMock()
    migration.op = mock_op

    migration.upgrade()

    table_calls = {
        call.args[0]: call.args[1:] for call in mock_op.create_table.call_args_list
    }
    day_unique_columns = {
        tuple(item._pending_colargs)
        for item in table_calls["recurring_service_days"]
        if item.__class__.__name__ == "UniqueConstraint"
    }
    stop_unique_columns = {
        tuple(item._pending_colargs)
        for item in table_calls["recurring_service_stops"]
        if item.__class__.__name__ == "UniqueConstraint"
    }
    service_unique_columns = {
        tuple(item._pending_colargs)
        for item in table_calls["recurring_services"]
        if item.__class__.__name__ == "UniqueConstraint"
    }
    assert ("recurring_service_id", "weekday") in day_unique_columns
    assert ("recurring_service_id", "stop_order") in stop_unique_columns
    assert ("replaces_recurring_service_id",) in service_unique_columns
    live_index = next(
        call
        for call in mock_op.create_index.call_args_list
        if call.args[0] == "uq_recurring_services_live_reference"
    )
    assert live_index.args[1:3] == (
        "recurring_services",
        ["customer_id", "service_reference"],
    )
    assert live_index.kwargs["unique"] is True
    assert "active" in str(live_index.kwargs["postgresql_where"])


def test_fleet_hire_purchase_migration_is_additive_nullable_and_new_head():
    migration_path = _migration_file("*_fleet_hire_purchase.py")
    spec = importlib.util.spec_from_file_location(
        "fleet_hire_purchase_migration", migration_path
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.down_revision == "e2f119fleet2"
    mock_op = MagicMock()
    migration.op = mock_op
    migration.upgrade()

    added = {call.args[1].name: call.args[1] for call in mock_op.add_column.call_args_list}
    assert set(added) == {
        "finance_company",
        "original_loan_amount",
        "monthly_instalment",
        "loan_start_date",
        "loan_term_months",
    }
    assert all(column.nullable is True for column in added.values())
    assert added["finance_company"].type.length == 120
    assert added["original_loan_amount"].type.precision == 12
    assert added["monthly_instalment"].type.scale == 2
    constraint_names = {
        call.args[0] for call in mock_op.create_check_constraint.call_args_list
    }
    assert constraint_names == {
        "ck_vehicles_original_loan_amount",
        "ck_vehicles_monthly_instalment",
        "ck_vehicles_loan_term_months",
    }
    mock_op.drop_table.assert_not_called()
    mock_op.drop_column.assert_not_called()
    mock_op.alter_column.assert_not_called()
    mock_op.execute.assert_not_called()
