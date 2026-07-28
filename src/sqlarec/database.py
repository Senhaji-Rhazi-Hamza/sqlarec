"""Engine and session helpers for synchronous SQLAlchemy applications."""

from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_engine: Engine | None = None


def init_engine(database_uri: str, **kwargs: Any) -> Engine:
    """Create and register the package's default SQLAlchemy engine.

    Args:
        database_uri: SQLAlchemy database URL.
        **kwargs: Additional keyword arguments passed to
            :func:`sqlalchemy.create_engine`.

    Returns:
        The newly created synchronous engine.

    Note:
        Calling this function replaces the registered default engine. Existing
        sessions continue to use the engine to which they were originally bound.
    """
    global _engine
    _engine = create_engine(database_uri, **kwargs)
    return _engine


def get_engine() -> Engine:
    """Return the registered default engine.

    Raises:
        RuntimeError: If :func:`init_engine` has not been called.
    """
    if _engine is None:
        raise RuntimeError("Database engine not initialized; call init_engine() first")
    return _engine


def new_session(engine: Engine | None = None) -> Session:
    """Create a synchronous session without opening a transaction eagerly.

    Args:
        engine: Engine to bind. The registered default engine is used when this
            argument is omitted.

    Returns:
        A session configured with ``autoflush=False`` and
        ``expire_on_commit=False``.
    """
    bind = get_engine() if engine is None else engine
    factory = sessionmaker(
        bind=bind,
        autoflush=False,
        expire_on_commit=False,
    )
    return factory()
