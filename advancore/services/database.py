import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from advancore.models import Base


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not configured.")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)


def test_database_connection() -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False

def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)