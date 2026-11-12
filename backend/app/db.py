from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


_clock_offset = [timedelta(0)]


def utcnow() -> datetime:
    """Naive UTC timestamp (stored as UTC; the UI renders WIB)."""
    return datetime.now(UTC).replace(tzinfo=None) + _clock_offset[0]


def set_clock_offset(offset: timedelta) -> None:
    """Used only by the seed script to backdate synthetic history. Never called by the API."""
    _clock_offset[0] = offset


def make_engine(url: str):
    kwargs = {"connect_args": {"check_same_thread": False, "timeout": 30}} if url.startswith("sqlite") else {}
    engine = create_engine(url, future=True, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):  # enforce foreign keys; WAL lets the worker and API read/write together
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()
    return engine


engine = make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
