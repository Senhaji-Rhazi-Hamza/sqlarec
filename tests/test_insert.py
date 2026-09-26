"""Tests for synchronous and asynchronous bulk insert builders."""

from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from conftest import AsyncStringKeyedRecord, AsyncUser, StringKeyedRecord, User
from sqlarec import BaseModel, Insert, ModelInsert, RowInsert
from sqlarec.asyncio import AsyncInsert, AsyncModelInsert, AsyncRowInsert


def _user_rows() -> list[dict[str, Any]]:
    return [
        {"name": "Hamza", "email": "hamza@example.com"},
        {
            "name": "Reader",
            "email": "reader@example.com",
            "active": False,
        },
    ]


def test_insert_executes_bulk_mappings_without_committing(session: Session) -> None:
    builder = User.insert()
    insert = builder.values(_user_rows())

    insert.execute()

    assert isinstance(builder, Insert)
    assert builder.parameters == ()
    assert [user.name for user in User.query.order_by(User.id).all()] == [
        "Hamza",
        "Reader",
    ]
    assert session.in_transaction()


def test_insert_returning_selects_entity_and_row_wrappers(
    session: Session,
) -> None:
    model_insert = User.insert().values(_user_rows()).returning(User)

    users = model_insert.all()

    assert isinstance(model_insert, ModelInsert)
    assert {user.email for user in users} == {
        "hamza@example.com",
        "reader@example.com",
    }

    row_insert = (
        User.insert()
        .values([{"name": "Third", "email": "third@example.com"}])
        .returning(User.id, User.email)
    )

    assert isinstance(row_insert, RowInsert)
    assert row_insert.mappings().one()["email"] == "third@example.com"


def test_insert_requires_non_empty_mapping_iterable() -> None:
    with pytest.raises(ValueError, match="Call values"):
        User.insert().execute()

    with pytest.raises(ValueError, match="at least one mapping"):
        User.insert().values([])

    with pytest.raises(TypeError, match="not one mapping"):
        User.insert().values(cast(Any, {"name": "Hamza"}))

    with pytest.raises(TypeError, match="must be a mapping"):
        User.insert().values(cast(Any, [("Hamza", "hamza@example.com")]))


def test_insert_preserves_supplied_mappings_without_generating_identifiers() -> None:
    assert StringKeyedRecord.insert().values([{"name": "sync"}]).parameters == (
        {"name": "sync"},
    )
    assert AsyncStringKeyedRecord.insert().values(
        [{"name": "async"}]
    ).parameters == ({"name": "async"},)


def test_insert_can_use_an_explicit_session_without_provider(
    session: Session,
) -> None:
    previous_provider = BaseModel._session_provider
    BaseModel._session_provider = None
    try:
        User.insert().with_session(session).values(_user_rows()).execute()

        assert len(User.query.with_session(session).all()) == 2
    finally:
        BaseModel._session_provider = previous_provider


async def test_async_insert_executes_and_returns_models(
    async_session: AsyncSession,
) -> None:
    builder = AsyncUser.insert()
    model_insert = builder.values(_user_rows()).returning(AsyncUser)

    users = await model_insert.all()

    assert isinstance(builder, AsyncInsert)
    assert isinstance(model_insert, AsyncModelInsert)
    assert {user.email for user in users} == {
        "hamza@example.com",
        "reader@example.com",
    }
    assert async_session.in_transaction()


async def test_async_insert_returns_mapping_rows(
    async_session: AsyncSession,
) -> None:
    row_insert = (
        AsyncUser.insert()
        .values(_user_rows())
        .returning(AsyncUser.id, AsyncUser.email)
    )

    rows = await row_insert.mappings()

    assert isinstance(row_insert, AsyncRowInsert)
    assert {row["email"] for row in rows} == {
        "hamza@example.com",
        "reader@example.com",
    }


async def test_async_insert_requires_values() -> None:
    with pytest.raises(ValueError, match="Call values"):
        await AsyncUser.insert().execute()
