"""Regression tests for the asynchronous model helpers."""

from __future__ import annotations

import uuid

from sqlalchemy import String, Uuid, event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column

from sqlarec.asyncio import AsyncBaseModel


class AsyncUuidKeyed(AsyncBaseModel):
    """Async model whose primary key is a native UUID column."""

    __tablename__ = "async_uuid_keyed"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))


class AsyncAccount(AsyncBaseModel):
    """Async model with a unique lookup column and a value column."""

    __tablename__ = "async_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(100))


async def test_async_uuid_primary_key_receives_a_uuid_object(
    async_session: AsyncSession,
) -> None:
    instance = await AsyncUuidKeyed.create(name="uuid")

    assert isinstance(instance.id, uuid.UUID)


async def test_async_get_or_create_returns_existing_row_when_defaults_differ(
    async_session: AsyncSession,
) -> None:
    await AsyncAccount.create(email="hamza@example.com", name="Hamza")
    await async_session.flush()

    found = await AsyncAccount.get_or_create(
        email="hamza@example.com",
        defaults={"name": "New name"},
    )

    assert found.name == "Hamza"
    assert len(await AsyncAccount.all()) == 1


async def test_async_get_or_create_applies_defaults_on_a_miss(
    async_session: AsyncSession,
) -> None:
    created = await AsyncAccount.get_or_create(
        email="new@example.com",
        defaults={"name": "New name"},
    )

    assert created.email == "new@example.com"
    assert created.name == "New name"


async def test_async_repr_after_commit_emits_no_sql() -> None:
    """Rendering an expired async instance must not attempt IO in the event loop."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(AsyncBaseModel.metadata.create_all)

    statements: list[str] = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def record(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        statements.append(statement)

    previous_provider = AsyncBaseModel._session_provider
    try:
        # expire_on_commit=True is the default and expires every attribute.
        async with AsyncSession(engine) as session:
            AsyncBaseModel.register_session_provider(lambda: session)
            account = await AsyncAccount.create(email="a@example.com", name="A")
            await session.commit()

            statements.clear()
            rendered = repr(account)
            formatted = f"{account}"

            assert statements == []
            assert rendered == formatted
            assert rendered == (
                "AsyncAccount(id=<not loaded>, email=<not loaded>, name=<not loaded>)"
            )
    finally:
        AsyncBaseModel._session_provider = previous_provider
        await engine.dispose()
