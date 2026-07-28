"""Static assertions for the synchronous and asynchronous public APIs."""

from collections.abc import Sequence
from typing import assert_type

from conftest import AsyncUser, User
from sqlarec import ModelQuery
from sqlarec.asyncio import AsyncModelQuery


def _check_sync_types() -> None:
    assert_type(User.query, ModelQuery[User])
    assert_type(User.query.all(), Sequence[User])
    assert_type(User.create(name="Hamza", email="hamza@example.com"), User)


async def _check_async_types() -> None:
    assert_type(AsyncUser.query, AsyncModelQuery[AsyncUser])
    assert_type(await AsyncUser.query.all(), Sequence[AsyncUser])
    assert_type(
        await AsyncUser.create(name="Hamza", email="hamza@example.com"),
        AsyncUser,
    )
