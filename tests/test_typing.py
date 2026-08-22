"""Static assertions for the synchronous and asynchronous public APIs."""

from collections.abc import Sequence
from typing import assert_type

from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Session

from conftest import AsyncUser, User
from sqlarec import (
    ActiveRecordMixin,
    ModelQuery,
    RowQuery,
    new_session_from_engine,
    select_rows,
)
from sqlarec.asyncio import (
    AsyncActiveRecordMixin,
    AsyncModelQuery,
    AsyncRowQuery,
    new_async_session_from_engine,
)
from sqlarec.asyncio import select_rows as select_async_rows


class ImperativeUser(ActiveRecordMixin):
    pass


class AsyncImperativeUser(AsyncActiveRecordMixin):
    pass


def _check_session_helper_types(
    engine: Engine,
    async_engine: AsyncEngine,
) -> None:
    assert_type(new_session_from_engine(engine), Session)
    assert_type(new_async_session_from_engine(async_engine), AsyncSession)


def _check_sync_types(session: Session) -> None:
    assert_type(User.query, ModelQuery[User])
    assert_type(User.query.all(), Sequence[User])
    assert_type(User.query.exists(), bool)
    assert_type(select_rows(User.id, User.email), RowQuery)
    assert_type(User.create(name="Hamza", email="hamza@example.com"), User)
    assert_type(
        User.create_with_session(session, name="Hamza", email="hamza@example.com"),
        User,
    )
    assert_type(ImperativeUser.query, ModelQuery[ImperativeUser])
    assert_type(ImperativeUser.create(name="Hamza"), ImperativeUser)


async def _check_async_types(async_session: AsyncSession) -> None:
    assert_type(AsyncUser.query, AsyncModelQuery[AsyncUser])
    assert_type(await AsyncUser.query.all(), Sequence[AsyncUser])
    assert_type(await AsyncUser.query.exists(), bool)
    assert_type(select_async_rows(AsyncUser.id, AsyncUser.email), AsyncRowQuery)
    assert_type(
        await AsyncUser.create(name="Hamza", email="hamza@example.com"),
        AsyncUser,
    )
    assert_type(
        await AsyncUser.create_with_session(
            async_session,
            name="Hamza",
            email="hamza@example.com",
        ),
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
