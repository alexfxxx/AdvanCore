import os
from contextlib import contextmanager

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from advancore.models import Base


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not configured.")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine)


def create_session_factory(bind_engine):
    """Return a new session factory bound to the supplied engine.

    This helper is intended for tests and isolated database contexts that must
    not use the module-level production engine.
    """
    return sessionmaker(bind=bind_engine)


@contextmanager
def session_scope(session_factory=None):
    """Run a block of work inside a SQLAlchemy session.

    Commits on successful completion, rolls back on exception, and always
    closes the session.  A custom ``session_factory`` may be supplied for
    testing or for working against a non-default engine.
    """
    factory = session_factory or SessionLocal
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def test_database_connection() -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)