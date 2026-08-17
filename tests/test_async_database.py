"""Tests for the public asynchronous session helper."""

from sqlalchemy.ext.asyncio import create_async_engine

from sqlarec.asyncio import new_async_session_from_engine


async def test_new_async_session_from_engine_uses_sqlarec_defaults() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with new_async_session_from_engine(engine) as session:
        assert session.bind is engine
        assert session.autoflush is False
        assert session.sync_session.expire_on_commit is False

    await engine.dispose()


async def test_new_async_session_from_engine_forwards_sessionmaker_options() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with new_async_session_from_engine(
        engine,
        autoflush=True,
        expire_on_commit=True,
        autobegin=False,
        info={"scope": "test"},
    ) as session:
        assert session.autoflush is True
        assert session.sync_session.expire_on_commit is True
        assert session.sync_session.autobegin is False
        assert session.info == {"scope": "test"}

    await engine.dispose()
