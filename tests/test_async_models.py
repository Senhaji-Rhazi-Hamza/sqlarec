"""Tests for the public asynchronous Active Record model API."""

from contextvars import ContextVar

import pytest
from sqlalchemy import Column, Integer, String, Table, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column, registry

from conftest import AsyncUser
from sqlarec.asyncio import (
    AsyncActiveRecordMixin,
    AsyncBaseModel,
    AsyncModelQuery,
    AsyncModelUpdate,
    AsyncRowQuery,
    AsyncRowUpdate,
)


def test_async_session_requires_registered_provider() -> None:
    previous_provider = AsyncBaseModel._session_provider
    AsyncBaseModel._session_provider = None
    try:
        try:
            _ = AsyncUser.session
        except RuntimeError as error:
            assert "register_session_provider" in str(error)
        else:
            raise AssertionError("accessing async session should have failed")
    finally:
        AsyncBaseModel._session_provider = previous_provider


def test_async_session_provider_cannot_be_registered_on_concrete_model(
    async_session: AsyncSession,
) -> None:
    with pytest.raises(TypeError, match="abstract model base"):
        AsyncUser.register_session_provider(lambda: async_session)


def test_async_abstract_base_owns_its_session_provider(
    async_session: AsyncSession,
) -> None:
    class ApplicationBase(AsyncBaseModel):
        __abstract__ = True

    class ApplicationUser(ApplicationBase):
        __tablename__ = "async_application_users"

        id: Mapped[int] = mapped_column(primary_key=True)

    ApplicationBase.register_session_provider(lambda: async_session)

    assert ApplicationUser.session is async_session
    assert "_session_provider" in ApplicationBase.__dict__


async def test_async_builders_resolve_the_session_when_executed() -> None:
    engine_a = create_async_engine("sqlite+aiosqlite:///:memory:")
    engine_b = create_async_engine("sqlite+aiosqlite:///:memory:")
    previous_provider = AsyncBaseModel._session_provider

    try:
        for engine in (engine_a, engine_b):
            async with engine.begin() as connection:
                await connection.run_sync(AsyncBaseModel.metadata.create_all)

        async with (
            AsyncSession(engine_a) as session_a,
            AsyncSession(engine_b) as session_b,
        ):
            session_a.add(
                AsyncUser(
                    id=1,
                    name="Tenant A",
                    email="a@example.com",
                    active=False,
                )
            )
            session_b.add(
                AsyncUser(
                    id=1,
                    name="Tenant B",
                    email="b@example.com",
                    active=False,
                )
            )
            await session_a.commit()
            await session_b.commit()

            current_session = ContextVar[AsyncSession]("current_async_session")
            AsyncBaseModel.register_session_provider(current_session.get)

            current_session.set(session_a)
            query = AsyncUser.query
            rows = AsyncUser.select(AsyncUser.name)
            user_update = (
                AsyncUser.update().where(AsyncUser.id == 1).values(active=True)
            )

            current_session.set(session_b)

            assert (await query.one()).name == "Tenant B"
            assert await rows.one() == ("Tenant B",)
            assert (await user_update.execute()).rowcount == 1
            await session_b.commit()
            assert await session_a.scalar(select(AsyncUser.active)) is False
            assert await session_b.scalar(select(AsyncUser.active)) is True
    finally:
        AsyncBaseModel._session_provider = previous_provider
        await engine_a.dispose()
        await engine_b.dispose()


async def test_async_builders_use_explicit_session_without_provider(
    async_session: AsyncSession,
) -> None:
    previous_provider = AsyncBaseModel._session_provider
    AsyncBaseModel._session_provider = None

    try:
        async_session.add(
            AsyncUser(
                name="Hamza",
                email="hamza@example.com",
                active=False,
            )
        )
        await async_session.flush()

        query = AsyncUser.query.filter_by(email="hamza@example.com")
        rows = AsyncUser.select(AsyncUser.name).where(
            AsyncUser.email == "hamza@example.com"
        )
        user_update = AsyncUser.update().where(AsyncUser.email == "hamza@example.com")

        assert (await query.with_session(async_session).one()).name == "Hamza"
        assert await rows.with_session(async_session).one() == ("Hamza",)
        result = await (
            user_update.with_session(async_session).values(active=True).execute()
        )
        assert result.rowcount == 1
        assert (await query.with_session(async_session).one()).active

        with pytest.raises(RuntimeError, match="register_session_provider"):
            await AsyncUser.query.all()
    finally:
        AsyncBaseModel._session_provider = previous_provider


async def test_async_create_query_save_and_delete(
    async_session: AsyncSession,
) -> None:
    user = await AsyncUser.create(name="Hamza", email="hamza@example.com")

    assert user.id is not None
    assert isinstance(AsyncUser.query, AsyncModelQuery)
    assert await AsyncUser.exists(user.id)
    assert await AsyncUser.get_by_pk(user.id) is user

    user.name = "Hamza S."
    assert await user.save() is user
    assert (await AsyncUser.query.one()).name == "Hamza S."

    await user.delete()
    assert not await AsyncUser.exists(user.id)


async def test_async_explicit_session_overrides_provider() -> None:
    provider_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    explicit_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    previous_provider = AsyncBaseModel._session_provider

    try:
        for engine in (provider_engine, explicit_engine):
            async with engine.begin() as connection:
                await connection.run_sync(AsyncBaseModel.metadata.create_all)

        async with (
            AsyncSession(provider_engine) as provider_session,
            AsyncSession(explicit_engine) as explicit_session,
        ):
            AsyncBaseModel.register_session_provider(lambda: provider_session)

            user = await AsyncUser.create_with_session(
                explicit_session,
                name="Hamza",
                email="hamza@example.com",
            )
            assert inspect(user).async_session is explicit_session

            user.name = "Hamza S."
            assert await user.save() is user
            assert (
                await AsyncUser.query.with_session(explicit_session).one()
            ).name == "Hamza S."

            await user.delete()
            assert (
                await AsyncUser.query.with_session(explicit_session).one_or_none()
                is None
            )
            assert (
                await AsyncUser.query.with_session(provider_session).one_or_none()
                is None
            )
    finally:
        AsyncBaseModel._session_provider = previous_provider
        await provider_engine.dispose()
        await explicit_engine.dispose()


async def test_async_queries_are_immutable(async_session: AsyncSession) -> None:
    await AsyncUser.create(name="Hamza", email="hamza@example.com")
    await AsyncUser.create(
        name="Reader",
        email="reader@example.com",
        active=False,
    )

    base_query = AsyncUser.query.order_by(AsyncUser.id)
    active_query = base_query.filter_by(active=True)

    assert [user.name for user in await base_query.all()] == ["Hamza", "Reader"]
    assert [user.name for user in await active_query.all()] == ["Hamza"]
    assert (await active_query.first()) is not None
    assert (await active_query.one()).name == "Hamza"
    assert await AsyncUser.query.filter_by(name="Missing").one_or_none() is None


async def test_async_row_query_and_mappings(async_session: AsyncSession) -> None:
    user = await AsyncUser.create(name="Hamza", email="hamza@example.com")

    rows = AsyncUser.select(AsyncUser.id, AsyncUser.email).where(
        AsyncUser.id == user.id
    )

    assert isinstance(rows, AsyncRowQuery)
    assert await rows.one() == (user.id, "hamza@example.com")
    assert (await rows.mappings()).one()["email"] == "hamza@example.com"


async def test_async_query_exists_returns_boolean(
    async_session: AsyncSession,
) -> None:
    await AsyncUser.create(name="Hamza", email="hamza@example.com")

    assert await AsyncUser.query.filter_by(email="hamza@example.com").exists()
    assert not await AsyncUser.query.filter_by(email="missing@example.com").exists()
    assert (
        await AsyncUser.select(AsyncUser.id).where(AsyncUser.name == "Hamza").exists()
    )
    assert (
        not await AsyncUser.select(AsyncUser.id)
        .where(AsyncUser.name == "Missing")
        .exists()
    )


async def test_async_union_preserves_entities(async_session: AsyncSession) -> None:
    first = await AsyncUser.create(name="Hamza", email="hamza@example.com")
    second = await AsyncUser.create(name="Reader", email="reader@example.com")

    combined = AsyncUser.query.where(AsyncUser.id == first.id).union(
        AsyncUser.query.where(AsyncUser.id == second.id)
    )

    assert {user.id for user in await combined.all()} == {first.id, second.id}


async def test_async_update_wrappers(async_session: AsyncSession) -> None:
    user = await AsyncUser.create(
        name="Hamza",
        email="hamza@example.com",
        active=False,
    )

    result = await (
        AsyncUser.update().where(AsyncUser.id == user.id).values(active=True).execute()
    )
    await async_session.refresh(user)

    assert result.rowcount == 1
    assert user.active
    assert isinstance(
        AsyncUser.update().values(active=True).returning(AsyncUser),
        AsyncModelUpdate,
    )
    assert isinstance(
        AsyncUser.update().values(active=True).returning(AsyncUser.id),
        AsyncRowUpdate,
    )


async def test_async_imperatively_mapped_active_record_mixin_has_full_api() -> None:
    mapper_registry = registry()
    booking_table = Table(
        "async_bookings",
        mapper_registry.metadata,
        Column("id", Integer, primary_key=True),
        Column("reference", String(100), nullable=False),
    )

    class Booking(AsyncActiveRecordMixin):
        id: int
        reference: str

    mapper_registry.map_imperatively(Booking, booking_table)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    previous_provider = AsyncActiveRecordMixin._session_provider

    try:
        async with engine.begin() as connection:
            await connection.run_sync(mapper_registry.metadata.create_all)

        async with AsyncSession(engine, expire_on_commit=False) as session:
            AsyncActiveRecordMixin.register_session_provider(lambda: session)

            assert Booking.session is session
            assert isinstance(Booking.query, AsyncModelQuery)
            assert Booking.query.statement.column_descriptions[0]["entity"] is Booking

            booking = await Booking.create(reference="ASYNC-1")
            assert await Booking.get_by_pk(booking.id) is booking
            assert await Booking.all() == [booking]
            assert await Booking.select(Booking.reference).one() == ("ASYNC-1",)

            await (
                Booking.update()
                .where(Booking.id == booking.id)
                .values(reference="ASYNC-2")
                .execute()
            )
            await session.refresh(booking)
            assert booking.reference == "ASYNC-2"
            assert await booking.save() is booking
            await booking.delete()
            assert not await Booking.exists(booking.id)
            assert session.in_transaction()
    finally:
        AsyncActiveRecordMixin._session_provider = previous_provider
        await engine.dispose()
