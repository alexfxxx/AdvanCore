"""Safe, isolated tests for advancore.services.database behavior.

These tests avoid touching production credentials or databases by using a
dummy DATABASE_URL and mocking the SQLAlchemy engine/connection.
"""

import importlib
from unittest.mock import MagicMock


def _reload_database_module(monkeypatch, database_url: str):
    """Reload database.py with a controlled DATABASE_URL environment variable."""
    monkeypatch.setenv("DATABASE_URL", database_url)
    from advancore.services import database as db_module

    return importlib.reload(db_module)


def test_database_connection_returns_true_on_success(monkeypatch):
    """test_database_connection() returns True when the read-only SELECT 1 succeeds."""
    db_module = _reload_database_module(
        monkeypatch, "postgresql+psycopg://user:pass@localhost/test"
    )

    mock_connection = MagicMock()
    mock_engine = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_connection

    monkeypatch.setattr(db_module, "engine", mock_engine)

    assert db_module.test_database_connection() is True
    mock_connection.execute.assert_called_once()


def test_database_connection_returns_false_on_failure(monkeypatch):
    """test_database_connection() returns False when the engine connection fails."""
    db_module = _reload_database_module(
        monkeypatch, "postgresql+psycopg://user:pass@localhost/test"
    )

    mock_engine = MagicMock()
    mock_engine.connect.side_effect = Exception("connection refused")

    monkeypatch.setattr(db_module, "engine", mock_engine)

    assert db_module.test_database_connection() is False
