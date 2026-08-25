"""PostgreSQL-only verification for the Knowledge approval migration.

This test resets only the disposable GitHub Actions service database. It skips
every local environment so it can never mutate the owner's saved database.
"""

from datetime import datetime, timezone
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


pytestmark = pytest.mark.skipif(
    os.getenv("GITHUB_ACTIONS") != "true",
    reason="requires the disposable GitHub Actions PostgreSQL service",
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASELINE_REVISION = "639d8b65223c"


def test_existing_draft_survives_approval_migration_and_checks_are_enforced():
    database_url = os.environ["DATABASE_URL"]
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)

    command.downgrade(config, "base")
    command.upgrade(config, BASELINE_REVISION)

    engine = create_engine(database_url)
    created_at = datetime(2026, 8, 25, 10, 30, tzinfo=timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO knowledge_items "
                "(title, content, status, created_at, updated_at) "
                "VALUES (:title, :content, 'draft', :created_at, :created_at)"
            ),
            {
                "title": "Existing draft",
                "content": "Retained content",
                "created_at": created_at,
            },
        )

    command.upgrade(config, "head")

    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT status, approved_at, approved_by "
                "FROM knowledge_items WHERE title = 'Existing draft'"
            )
        ).one()
    assert tuple(row) == ("draft", None, None)

    constraint_names = {
        constraint["name"]
        for constraint in inspect(engine).get_check_constraints("knowledge_items")
    }
    assert constraint_names >= {
        "ck_knowledge_items_approval_fields_paired",
        "ck_knowledge_items_approved_has_metadata",
        "ck_knowledge_items_draft_unapproved",
        "ck_knowledge_items_approver_nonblank",
    }

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO knowledge_items "
                    "(title, content, status, created_at, updated_at) "
                    "VALUES ('Invalid approved', 'Content', 'approved', "
                    ":created_at, :created_at)"
                ),
                {"created_at": created_at},
            )

    engine.dispose()
