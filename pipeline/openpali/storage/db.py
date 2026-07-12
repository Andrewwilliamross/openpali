"""Engine/session wiring.

Connection URLs come from explicit environment variables with local-fixture
defaults that match infra/compose.yaml. Real deployments override via the
documented configuration interface; nothing here reads dotenv files.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_URL = "postgresql+psycopg://openpali:openpali-local-fixture-db@127.0.0.1:55432/openpali"


def database_url() -> str:
    return os.environ.get("OPENPALI_DATABASE_URL", DEFAULT_URL)


_engine: Engine | None = None


def get_engine(url: str | None = None) -> Engine:
    global _engine
    if url is not None:
        return create_engine(url, pool_pre_ping=True)
    if _engine is None:
        _engine = create_engine(database_url(), pool_pre_ping=True)
    return _engine


def get_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=engine or get_engine(), expire_on_commit=False)


@contextmanager
def session_scope(engine: Engine | None = None) -> Iterator[Session]:
    factory = get_session_factory(engine)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
