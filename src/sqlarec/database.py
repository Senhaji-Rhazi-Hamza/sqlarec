"""Session construction helpers for synchronous SQLAlchemy applications."""

from typing import Any

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def new_session_from_engine(
    engine: Engine,
    *,
    autoflush: bool = False,
    expire_on_commit: bool = False,
    **kwargs: Any,
) -> Session:
    """Create a synchronous session from an application-owned engine.

    Args:
        engine: Engine to bind to the session.
        autoflush: Whether query operations automatically flush pending changes.
        expire_on_commit: Whether commit expires loaded model attributes.
        **kwargs: Additional options forwarded to :class:`sqlalchemy.orm.sessionmaker`.

    Returns:
        A new session configured with the supplied options.
    """
    factory = sessionmaker(
        bind=engine,
        autoflush=autoflush,
        expire_on_commit=expire_on_commit,
        **kwargs,
    )
    return factory()
