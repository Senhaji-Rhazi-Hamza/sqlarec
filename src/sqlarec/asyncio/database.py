"""Engine and session helpers for asynchronous SQLAlchemy applications."""

from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_async_engine: AsyncEngine | None = None


def init_async_engine(database_uri: str, **kwargs: Any) -> AsyncEngine:
    """Create and register the package's default asynchronous engine.

    Args:
        database_uri: SQLAlchemy URL using an asynchronous database driver.
        **kwargs: Additional arguments passed to
            :func:`sqlalchemy.ext.asyncio.create_async_engine`.

    Returns:
        The newly created asynchronous engine.
    """
    global _async_engine
    _async_engine = create_async_engine(database_uri, **kwargs)
    return _async_engine


def get_async_engine() -> AsyncEngine:
    """Return the registered default asynchronous engine.

    Raises:
        RuntimeError: If :func:`init_async_engine` has not been called.
    """
    if _async_engine is None:
        raise RuntimeError(
            "Async database engine not initialized; call init_async_engine() first"
        )
    return _async_engine


def new_async_session(engine: AsyncEngine | None = None) -> AsyncSession:
    """Create an asynchronous session bound to an engine.

    Args:
        engine: Engine to bind. The registered default async engine is used when
            omitted.

    Returns:
        An async session configured with ``autoflush=False`` and
        ``expire_on_commit=False``.
    """
    bind = get_async_engine() if engine is None else engine
    factory = async_sessionmaker(
        bind=bind,
        autoflush=False,
        expire_on_commit=False,
    )
    return factory()
