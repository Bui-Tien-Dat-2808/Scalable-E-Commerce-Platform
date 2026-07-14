"""
Shared database module.
Tạo SQLAlchemy engine từ DATABASE_URL env var.
Mặc định dùng SQLite (phù hợp cho dev/test).
Khi chạy Docker dùng PostgreSQL qua DATABASE_URL.
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

# SQLite cần check_same_thread=False; PostgreSQL không cần
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency: tạo DB session cho mỗi request, đóng khi xong."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
