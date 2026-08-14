"""Static assertions for the synchronous and asynchronous public APIs."""

from collections.abc import Sequence
from typing import assert_type

from conftest import AsyncUser, User
from sqlarec import ActiveRecordMixin, ModelQuery
from sqlarec.asyncio import AsyncActiveRecordMixin, AsyncModelQuery


class ImperativeUser(ActiveRecordMixin):
    pass


class AsyncImperativeUser(AsyncActiveRecordMixin):
    pass


def _check_sync_types() -> None:
    assert_type(User.query, ModelQuery[User])
    assert_type(User.query.all(), Sequence[User])
    assert_type(User.create(name="Hamza", email="hamza@example.com"), User)
    assert_type(ImperativeUser.query, ModelQuery[ImperativeUser])
    assert_type(ImperativeUser.create(name="Hamza"), ImperativeUser)


async def _check_async_types() -> None:
    assert_type(AsyncUser.query, AsyncModelQuery[AsyncUser])
    assert_type(await AsyncUser.query.all(), Sequence[AsyncUser])
    assert_type(
        await AsyncUser.create(name="Hamza", email="hamza@example.com"),
        AsyncUser,
    )
    assert_type(
        AsyncImperativeUser.query,
        AsyncModelQuery[AsyncImperativeUser],
    )
    assert_type(
        await AsyncImperativeUser.create(name="Hamza"),
        AsyncImperativeUser,
    )
