"""SQLAlchemy engine, session factory and declarative base."""

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _make_engine(url: str):
    if url.startswith("sqlite:///") and ":memory:" not in url:
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    if ":memory:" in url:
        from sqlalchemy.pool import StaticPool

        kwargs["poolclass"] = StaticPool
    return create_engine(url, **kwargs)


engine = _make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


_ADDED_COLUMNS = {  # columns introduced after the first release: name -> DDL type
    "owner": "VARCHAR(64)",
    "draft_title": "VARCHAR(200)",
    "meta_description": "VARCHAR(400)",
}


def _ensure_columns() -> None:
    """Additive migration: add columns introduced after a local DB file was first created."""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if "analyses" not in insp.get_table_names():
        return
    have = {c["name"] for c in insp.get_columns("analyses")}
    with engine.begin() as conn:
        for name, ddl in _ADDED_COLUMNS.items():
            if name not in have:
                conn.execute(text(f"ALTER TABLE analyses ADD COLUMN {name} {ddl}"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_analyses_owner ON analyses (owner)"))


def init_db() -> None:
    """Create all tables if they do not exist (and apply additive column migrations)."""
    from app import models  # noqa: F401  (register models)

    Base.metadata.create_all(bind=engine)
    _ensure_columns()


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
