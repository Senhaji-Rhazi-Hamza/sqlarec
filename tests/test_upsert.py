"""Tests for synchronous and asynchronous upsert builders."""

from contextvars import ContextVar
from typing import Any, cast

import pytest
from sqlalchemy import Column, Integer, String, Table, create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, Session, mapped_column, registry

from conftest import AsyncStringKeyedRecord, AsyncUser, StringKeyedRecord, User
from sqlarec import ActiveRecordMixin, BaseModel, ModelUpsert, RowUpsert, Upsert
from sqlarec.asyncio import (
    AsyncBaseModel,
    AsyncModelUpsert,
    AsyncRowUpsert,
    AsyncUpsert,
)


class Membership(BaseModel):
    """Model with a composite conflict target."""

    __tablename__ = "memberships"

    organization_id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(String(50))


class AsyncMembership(AsyncBaseModel):
    """Async model with a composite conflict target."""

    __tablename__ = "memberships"

    organization_id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(String(50))


def _rows() -> list[dict[str, Any]]:
    return [
        {"name": "Hamza", "email": "hamza@example.com"},
        {"name": "Reader", "email": "reader@example.com"},
    ]


def _user_upsert() -> Upsert:
    return (
        User.upsert()
        .values(_rows())
        .on_conflict(User.email)
        .update_existing(User.name)
    )


def test_upsert_inserts_and_updates_candidate_rows(session: Session) -> None:
    _user_upsert().execute()

    result = (
        User.upsert()
        .values(
            [
                {"name": "Hamza S.", "email": "hamza@example.com"},
                {"name": "Third", "email": "third@example.com"},
            ]
        )
        .on_conflict(User.email)
        .update_existing(User.name)
        .returning(User)
    )
    users = result.all()

    assert isinstance(result, ModelUpsert)
    assert {user.email for user in users} == {
        "hamza@example.com",
        "third@example.com",
    }
    assert User.query.filter_by(email="hamza@example.com").one().name == "Hamza S."
    assert User.query.filter_by(email="reader@example.com").one().name == "Reader"
    assert session.in_transaction()


def test_upsert_returning_rows_and_mappings(session: Session) -> None:
    result = _user_upsert().returning(User.id, User.email)

    rows = result.mappings().all()

    assert isinstance(result, RowUpsert)
    assert {row["email"] for row in rows} == {
        "hamza@example.com",
        "reader@example.com",
    }


def test_upsert_refreshes_an_existing_identity(session: Session) -> None:
    user = User.create(name="Old name", email="hamza@example.com")

    returned = (
        User.upsert()
        .values([{"name": "New name", "email": user.email}])
        .on_conflict(User.email)
        .update_existing(User.name)
        .returning(User)
        .one()
    )

    assert returned is user
    assert user.name == "New name"


def test_upsert_supports_composite_conflict_targets(session: Session) -> None:
    builder = (
        Membership.upsert()
        .values([{"organization_id": 1, "user_id": 2, "role": "member"}])
        .on_conflict(Membership.organization_id, Membership.user_id)
        .update_existing(Membership.role)
    )
    builder.execute()

    membership = builder.values(
        [{"organization_id": 1, "user_id": 2, "role": "owner"}]
    ).returning(Membership).one()

    assert membership.role == "owner"
    assert Membership.query.one().role == "owner"


def test_upsert_statement_uses_the_current_session_lazily() -> None:
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    previous_provider = BaseModel._session_provider

    try:
        with Session(engine) as session:
            current_session = ContextVar[Session]("upsert_session")
            BaseModel.register_session_provider(current_session.get)
            builder = _user_upsert()
            current_session.set(session)

            assert "ON CONFLICT" in str(builder.statement)
            builder.execute()
            assert {user.email for user in User.query.all()} == {
                "hamza@example.com",
                "reader@example.com",
            }
    finally:
        BaseModel._session_provider = previous_provider
        engine.dispose()


def test_upsert_resolves_the_same_current_session_for_statement_and_execution(
    session: Session,
) -> None:
    previous_provider = BaseModel._session_provider
    calls = 0

    def provide_session() -> Session:
        nonlocal calls
        calls += 1
        return session

    try:
        BaseModel.register_session_provider(provide_session)

        _user_upsert().execute()

        assert calls == 2
    finally:
        BaseModel._session_provider = previous_provider


def test_upsert_uses_an_explicit_session_without_provider(session: Session) -> None:
    previous_provider = BaseModel._session_provider
    BaseModel._session_provider = None
    try:
        _user_upsert().with_session(session).execute()

        assert len(User.query.with_session(session).all()) == 2
    finally:
        BaseModel._session_provider = previous_provider


@pytest.mark.parametrize(
    ("builder", "message"),
    [
        (User.upsert(), "values"),
        (User.upsert().values(_rows()), "on_conflict"),
        (
            User.upsert().values(_rows()).on_conflict(User.email),
            "update_existing",
        ),
    ],
)
def test_upsert_requires_complete_configuration(
    session: Session,
    builder: Upsert,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _ = builder.statement


def test_upsert_validates_before_resolving_a_session() -> None:
    previous_provider = BaseModel._session_provider
    BaseModel._session_provider = None
    try:
        with pytest.raises(ValueError, match="values"):
            _ = User.upsert().statement
    finally:
        BaseModel._session_provider = previous_provider


def test_upsert_validates_candidate_mappings() -> None:
    with pytest.raises(ValueError, match="at least one mapping"):
        User.upsert().values([])
    with pytest.raises(TypeError, match="not one mapping"):
        User.upsert().values(cast(Any, {"email": "hamza@example.com"}))
    with pytest.raises(TypeError, match="must be a mapping"):
        User.upsert().values(cast(Any, [("Hamza", "hamza@example.com")]))
    with pytest.raises(ValueError, match="same keys"):
        User.upsert().values(
            [
                {"name": "Hamza", "email": "hamza@example.com"},
                {"name": "Reader", "email": "reader@example.com", "active": True},
            ]
        )
    with pytest.raises(ValueError, match="Unknown mapped attribute"):
        User.upsert().values([{"unknown": "value"}])


def test_upsert_validates_conflict_and_update_attributes(session: Session) -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        User.upsert().on_conflict()
    with pytest.raises(ValueError, match="primary or unique"):
        User.upsert().on_conflict(User.name)
    with pytest.raises(ValueError, match="mapped column"):
        User.upsert().on_conflict(Membership.role)
    with pytest.raises(ValueError, match="Duplicate"):
        User.upsert().on_conflict(User.email, User.email)
    with pytest.raises(ValueError, match="cannot be empty"):
        User.upsert().update_existing()
    with pytest.raises(ValueError, match="cannot be updated"):
        User.upsert().on_conflict(User.email).update_existing(User.email)
    with pytest.raises(ValueError, match="cannot be updated"):
        (
            User.upsert()
            .values(_rows())
            .update_existing(User.email)
            .on_conflict(User.email)
            .statement
        )


def test_upsert_requires_conflict_and_update_values(session: Session) -> None:
    with pytest.raises(ValueError, match="conflict values"):
        (
            User.upsert()
            .values([{"name": "Hamza"}])
            .on_conflict(User.email)
            .update_existing(User.name)
            .execute()
        )
    with pytest.raises(ValueError, match="update values"):
        (
            User.upsert()
            .values([{"email": "hamza@example.com"}])
            .on_conflict(User.email)
            .update_existing(User.name)
            .execute()
        )


def test_upsert_parameters_are_immutable_copies(session: Session) -> None:
    rows = _rows()
    builder = (
        User.upsert()
        .values(rows)
        .on_conflict(User.email)
        .update_existing(User.name)
    )
    rows[0]["name"] = "Changed outside"
    exposed = builder.parameters
    exposed[0]["name"] = "Changed copy"

    builder.execute()

    assert User.query.filter_by(email="hamza@example.com").one().name == "Hamza"


def test_upsert_preserves_supplied_mappings_without_generating_identifiers() -> None:
    sync = StringKeyedRecord.upsert().values([{"name": "sync"}])
    async_ = AsyncStringKeyedRecord.upsert().values([{"name": "async"}])

    assert sync.parameters == ({"name": "sync"},)
    assert async_.parameters == ({"name": "async"},)


def test_upsert_builders_are_immutable() -> None:
    base = User.upsert()
    with_values = base.values(_rows())
    complete = with_values.on_conflict(User.email).update_existing(User.name)

    assert base.parameters == ()
    assert with_values.parameters == tuple(_rows())
    assert complete.parameters == tuple(_rows())


def test_upsert_uses_mapped_names_with_renamed_columns() -> None:
    mapper_registry = registry()
    contact_table = Table(
        "contacts",
        mapper_registry.metadata,
        Column("record_id", Integer, primary_key=True),
        Column("email_address", String(255), unique=True, nullable=False),
        Column("display_name", String(100), nullable=False),
    )

    class Contact(ActiveRecordMixin):
        id: int
        email: str
        name: str

    mapper_registry.map_imperatively(
        Contact,
        contact_table,
        properties={
            "id": contact_table.c.record_id,
            "email": contact_table.c.email_address,
            "name": contact_table.c.display_name,
        },
    )
    engine = create_engine("sqlite:///:memory:")
    mapper_registry.metadata.create_all(engine)
    previous_provider = ActiveRecordMixin._session_provider

    try:
        with Session(engine) as session:
            ActiveRecordMixin.register_session_provider(lambda: session)
            builder = (
                Contact.upsert()
                .values([{"email": "hamza@example.com", "name": "Hamza"}])
                .on_conflict(Contact.email)
                .update_existing(Contact.name)
            )
            builder.execute()
            builder.values(
                [{"email": "hamza@example.com", "name": "Hamza S."}]
            ).execute()

            assert Contact.query.one().name == "Hamza S."
    finally:
        ActiveRecordMixin._session_provider = previous_provider
        engine.dispose()


def test_upsert_builds_postgresql_statement(session: Session) -> None:
    class PostgreSQLBind:
        dialect = postgresql.dialect()

    class PostgreSQLSession:
        def get_bind(self, **kwargs: Any) -> PostgreSQLBind:
            return PostgreSQLBind()

    statement = _user_upsert().with_session(
        cast(Session, PostgreSQLSession())
    ).statement
    compiled = str(statement.compile(dialect=postgresql.dialect()))

    assert "ON CONFLICT (email) DO UPDATE" in compiled


def test_upsert_rejects_unsupported_databases(session: Session) -> None:
    class UnsupportedDialect:
        name = "unsupported"

    class UnsupportedBind:
        dialect = UnsupportedDialect()

    class UnsupportedSession:
        def get_bind(self, **kwargs: Any) -> UnsupportedBind:
            return UnsupportedBind()

    builder = _user_upsert().with_session(cast(Session, UnsupportedSession()))

    with pytest.raises(NotImplementedError, match="unsupported"):
        _ = builder.statement


async def test_async_upsert_inserts_updates_and_returns_models(
    async_session: AsyncSession,
) -> None:
    builder = (
        AsyncUser.upsert()
        .values(_rows())
        .on_conflict(AsyncUser.email)
        .update_existing(AsyncUser.name)
    )
    await builder.execute()

    result = (
        builder.values(
            [
                {"name": "Hamza S.", "email": "hamza@example.com"},
                {"name": "Third", "email": "third@example.com"},
            ]
        )
        .returning(AsyncUser)
    )
    users = await result.all()

    assert isinstance(builder, AsyncUpsert)
    assert isinstance(result, AsyncModelUpsert)
    assert {user.name for user in users} == {"Hamza S.", "Third"}
    assert async_session.in_transaction()


async def test_async_upsert_returns_mapping_rows(
    async_session: AsyncSession,
) -> None:
    result = (
        AsyncUser.upsert()
        .values(_rows())
        .on_conflict(AsyncUser.email)
        .update_existing(AsyncUser.name)
        .returning(AsyncUser.id, AsyncUser.email)
    )

    rows = await result.mappings()

    assert isinstance(result, AsyncRowUpsert)
    assert {row["email"] for row in rows} == {
        "hamza@example.com",
        "reader@example.com",
    }


async def test_async_upsert_supports_composite_targets(
    async_session: AsyncSession,
) -> None:
    builder = (
        AsyncMembership.upsert()
        .values([{"organization_id": 1, "user_id": 2, "role": "member"}])
        .on_conflict(
            AsyncMembership.organization_id,
            AsyncMembership.user_id,
        )
        .update_existing(AsyncMembership.role)
    )
    await builder.execute()

    membership = await builder.values(
        [{"organization_id": 1, "user_id": 2, "role": "owner"}]
    ).returning(AsyncMembership).one()

    assert membership.role == "owner"
