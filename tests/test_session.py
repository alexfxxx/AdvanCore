"""Tests for the SQLAlchemy session lifecycle helpers."""

import pytest
from sqlalchemy import create_engine, text

from advancore.models import Base, Vehicle
from advancore.services.database import create_session_factory, session_scope


@pytest.fixture
def sqlite_engine():
    """Create an in-memory SQLite engine for isolated tests."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def sqlite_session_factory(sqlite_engine):
    """Return a session factory bound to the isolated SQLite engine."""
    return create_session_factory(sqlite_engine)


def test_session_scope_commits_and_closes_on_success(
    sqlite_session_factory, sqlite_engine
):
    """A successful block commits its work and ends the transaction."""
    with session_scope(sqlite_session_factory) as session:
        session.execute(text("CREATE TABLE test_scope (id INTEGER PRIMARY KEY)"))
        assert session.in_transaction() is True

    assert session.in_transaction() is False

    with sqlite_engine.connect() as connection:
        result = connection.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='test_scope'"))
        assert result.scalar() == "test_scope"


def test_committed_loaded_values_remain_available_for_read_only_rendering(
    sqlite_session_factory,
):
    """Page renderers can safely use loaded scalar values after the session closes."""
    with session_scope(sqlite_session_factory) as session:
        vehicle = Vehicle(registration_number="VIEW-1", status="active")
        session.add(vehicle)
        session.flush()

    assert vehicle.id == 1
    assert vehicle.registration_number == "VIEW-1"


def test_session_scope_rolls_back_and_closes_on_exception(
    sqlite_session_factory, sqlite_engine
):
    """An exception inside the block triggers rollback and ends the transaction."""
    with sqlite_engine.connect() as connection:
        connection.execute(text("CREATE TABLE test_rollback (id INTEGER PRIMARY KEY)"))
        connection.commit()

    session = None
    with pytest.raises(RuntimeError, match="boom"):
        with session_scope(sqlite_session_factory) as session:
            session.execute(text("INSERT INTO test_rollback (id) VALUES (1)"))
            assert session.in_transaction() is True
            raise RuntimeError("boom")

    assert session is not None
    assert session.in_transaction() is False

    with sqlite_engine.connect() as connection:
        result = connection.execute(text("SELECT id FROM test_rollback WHERE id = 1"))
        assert result.scalar() is None
