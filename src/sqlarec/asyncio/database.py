"""Session construction helpers for asynchronous SQLAlchemy applications."""

from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)


def new_async_session_from_engine(
    engine: AsyncEngine,
    *,
    autoflush: bool = False,
    expire_on_commit: bool = False,
    **kwargs: Any,
) -> AsyncSession:
    """Create an asynchronous session from an application-owned engine.

    Args:
        engine: Async engine to bind to the session.
        autoflush: Whether query operations automatically flush pending changes.
        expire_on_commit: Whether commit expires loaded model attributes.
        **kwargs: Additional options forwarded to
            :class:`sqlalchemy.ext.asyncio.async_sessionmaker`.

    Returns:
        A new async session configured with the supplied options.
    """
    factory = async_sessionmaker(
        bind=engine,
        autoflush=autoflush,
        expire_on_commit=expire_on_commit,
        **kwargs,
    )
    return factory()
