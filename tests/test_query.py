"""Tests for public query and update wrappers."""

import pytest
from sqlalchemy.orm import Session

from conftest import User
from sqlarec import ModelQuery, ModelUpdate, RowQuery, RowUpdate, select_rows


def test_model_query_is_immutable_and_returns_models(session: Session) -> None:
    User.create(name="Hamza", email="hamza@example.com")
    User.create(name="Reader", email="reader@example.com", active=False)

    base_query = User.query.order_by(User.id)
    active_query = base_query.filter_by(active=True)

    assert isinstance(base_query, ModelQuery)
    assert [user.name for user in base_query.all()] == ["Hamza", "Reader"]
    assert [user.name for user in active_query.all()] == ["Hamza"]
    assert active_query.first() is not None
    assert active_query.one().name == "Hamza"
    assert User.query.filter_by(name="Missing").one_or_none() is None


def test_row_query_returns_rows_and_mappings(session: Session) -> None:
    user = User.create(name="Hamza", email="hamza@example.com")

    rows = User.select(User.id, User.email).where(User.id == user.id)

    assert isinstance(rows, RowQuery)
    assert rows.one() == (user.id, "hamza@example.com")
    assert rows.mappings().one()["email"] == "hamza@example.com"


def test_query_exists_returns_boolean_for_models_and_rows(session: Session) -> None:
    User.create(name="Hamza", email="hamza@example.com")

    assert User.query.filter_by(email="hamza@example.com").exists()
    assert not User.query.filter_by(email="missing@example.com").exists()
    assert User.select(User.id).where(User.name == "Hamza").exists()
    assert not User.select(User.id).where(User.name == "Missing").exists()


def test_standalone_row_query_binds_session_at_execution(session: Session) -> None:
    user = User.create(name="Hamza", email="hamza@example.com")
    query = select_rows(User.id, User.email).where(User.id == user.id)

    assert isinstance(query, RowQuery)
    assert query.statement.column_descriptions[0]["expr"] is User.id
    assert query.compile() is not None

    with pytest.raises(RuntimeError, match="with_session"):
        query.one()

    assert query.with_session(session).one() == (user.id, user.email)

    with pytest.raises(RuntimeError, match="with_session"):
        query.one()


def test_model_query_union_preserves_entity_results(session: Session) -> None:
    first = User.create(name="Hamza", email="hamza@example.com")
    second = User.create(name="Reader", email="reader@example.com")

    combined = User.query.where(User.id == first.id).union(
        User.query.where(User.id == second.id)
    )

    assert {user.id for user in combined.all()} == {first.id, second.id}


def test_update_without_returning_produces_cursor_result(session: Session) -> None:
    user = User.create(name="Hamza", email="hamza@example.com", active=False)

    result = User.update().where(User.id == user.id).values(active=True).execute()
    session.refresh(user)

    assert result.rowcount == 1
    assert user.active


def test_update_selects_return_wrapper_from_expression(session: Session) -> None:
    model_update = User.update().values(active=True).returning(User)
    row_update = User.update().values(active=True).returning(User.id)

    assert isinstance(model_update, ModelUpdate)
    assert isinstance(row_update, RowUpdate)
