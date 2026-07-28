"""Tests for public asynchronous engine and session helpers."""

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

import sqlarec.asyncio.database as database
from sqlarec.asyncio import (
    get_async_engine,
    init_async_engine,
    new_async_session,
)


def test_get_async_engine_requires_initialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(database, "_async_engine", None)

    with pytest.raises(RuntimeError, match="init_async_engine"):
        get_async_engine()


@pytest.mark.asyncio
async def test_async_engine_and_session_helpers() -> None:
    engine = init_async_engine("sqlite+aiosqlite:///:memory:")

    assert isinstance(engine, AsyncEngine)
    assert get_async_engine() is engine

    async with new_async_session() as session:
        assert session.bind is engine
        assert session.autoflush is False
        assert session.sync_session.expire_on_commit is False

    await engine.dispose()
