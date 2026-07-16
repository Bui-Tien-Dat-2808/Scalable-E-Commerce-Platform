"""
Shared database module.
Creates SQLAlchemy engine from DATABASE_URL env var.
Defaults to SQLite (suitable for dev/test).
When running in Docker, PostgreSQL is used via DATABASE_URL.
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

# SQLite requires check_same_thread=False; PostgreSQL does not
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency: creates a DB session for each request, closes it when done."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
