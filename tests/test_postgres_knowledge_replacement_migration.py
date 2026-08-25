"""PostgreSQL-only verification for Knowledge replacement history.

This test resets only GitHub Actions' disposable service database and skips
every local environment so it cannot mutate the owner's saved database.
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
APPROVAL_REVISION = "3f61b4a9c2d7"


def test_existing_rows_survive_replacement_migration_and_lineage_is_enforced():
    database_url = os.environ["DATABASE_URL"]
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)

    command.downgrade(config, "base")
    command.upgrade(config, APPROVAL_REVISION)

    engine = create_engine(database_url)
    created_at = datetime(2026, 8, 25, 10, 30, tzinfo=timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO knowledge_items "
                "(title, content, status, created_at, updated_at) "
                "VALUES ('Existing draft', 'Retained', 'draft', "
                ":created_at, :created_at)"
            ),
            {"created_at": created_at},
        )
        source_id = connection.execute(
            text(
                "INSERT INTO knowledge_items "
                "(title, content, status, approved_at, approved_by, "
                "created_at, updated_at) VALUES "
                "('Existing approved', 'Official', 'approved', :created_at, "
                "'owner', :created_at, :created_at) RETURNING id"
            ),
            {"created_at": created_at},
        ).scalar_one()

    command.upgrade(config, "head")

    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT title, replaces_knowledge_item_id FROM knowledge_items "
                "ORDER BY id"
            )
        ).all()
    assert rows == [("Existing draft", None), ("Existing approved", None)]

    inspector = inspect(engine)
    assert {constraint["name"] for constraint in inspector.get_check_constraints(
        "knowledge_items"
    )} >= {
        "ck_knowledge_items_not_self_replacing",
        "ck_knowledge_items_superseded_has_metadata",
    }
    assert {key["name"] for key in inspector.get_foreign_keys("knowledge_items")} >= {
        "fk_knowledge_items_replaces_knowledge_item_id"
    }
    assert {index["name"] for index in inspector.get_indexes("knowledge_items")} >= {
        "uq_knowledge_items_open_replacement"
    }

    with engine.begin() as connection:
        replacement_id = connection.execute(
            text(
                "INSERT INTO knowledge_items "
                "(title, content, status, replaces_knowledge_item_id, "
                "created_at, updated_at) VALUES "
                "('Attempt one', 'Draft', 'draft', :source_id, "
                ":created_at, :created_at) RETURNING id"
            ),
            {"source_id": source_id, "created_at": created_at},
        ).scalar_one()

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO knowledge_items "
                    "(title, content, status, replaces_knowledge_item_id, "
                    "created_at, updated_at) VALUES "
                    "('Parallel', 'Draft', 'draft', :source_id, "
                    ":created_at, :created_at)"
                ),
                {"source_id": source_id, "created_at": created_at},
            )

    with engine.begin() as connection:
        connection.execute(
            text("UPDATE knowledge_items SET status='archived' WHERE id=:item_id"),
            {"item_id": replacement_id},
        )
        connection.execute(
            text(
                "INSERT INTO knowledge_items "
                "(title, content, status, replaces_knowledge_item_id, "
                "created_at, updated_at) VALUES "
                "('Fresh attempt', 'Draft', 'draft', :source_id, "
                ":created_at, :created_at)"
            ),
            {"source_id": source_id, "created_at": created_at},
        )

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO knowledge_items "
                    "(id, title, content, status, replaces_knowledge_item_id, "
                    "created_at, updated_at) VALUES "
                    "(9001, 'Self', 'Invalid', 'draft', 9001, "
                    ":created_at, :created_at)"
                ),
                {"created_at": created_at},
            )

    engine.dispose()
