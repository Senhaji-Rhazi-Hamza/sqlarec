"""Tests for the public asynchronous Active Record model API."""

from sqlalchemy.ext.asyncio import AsyncSession

from conftest import AsyncUser
from sqlarec.asyncio import (
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
