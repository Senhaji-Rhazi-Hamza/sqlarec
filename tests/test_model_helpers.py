"""Regression tests for identifier generation, get_or_create, repr, and to_dict."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    String,
    Table,
    Uuid,
    create_engine,
    event,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Mapped, Session, deferred, mapped_column, registry

from sqlarec import ActiveRecordMixin, BaseModel


class UuidKeyed(BaseModel):
    """Model whose primary key is a native UUID column."""

    __tablename__ = "uuid_keyed"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))


class HexUuidKeyed(BaseModel):
    """Model whose UUID primary key is stored as a hex string."""

    __tablename__ = "hex_uuid_keyed"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    name: Mapped[str] = mapped_column(String(50))


class WideStringKeyed(BaseModel):
    """Model whose string primary key has room for a hex identifier."""

    __tablename__ = "wide_string_keyed"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(50))


class UnboundedStringKeyed(BaseModel):
    """Model whose string primary key declares no length."""

    __tablename__ = "unbounded_string_keyed"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))


class NarrowStringKeyed(BaseModel):
    """Model whose string primary key is too short for a hex identifier."""

    __tablename__ = "narrow_string_keyed"

    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    name: Mapped[str] = mapped_column(String(50))


class ManualIntegerKeyed(BaseModel):
    """Model whose integer primary key is supplied by the caller."""

    __tablename__ = "manual_integer_keyed"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(50))


class ProfileOwner(BaseModel):
    """Parent of a model keyed by a foreign key."""

    __tablename__ = "profile_owners"

    id: Mapped[int] = mapped_column(primary_key=True)


class OwnedProfile(BaseModel):
    """Model whose primary key is also a foreign key."""

    __tablename__ = "owned_profiles"

    owner_id: Mapped[int] = mapped_column(
        ForeignKey("profile_owners.id"), primary_key=True
    )
    bio: Mapped[str] = mapped_column(String(50))


class Account(BaseModel):
    """Model with a unique lookup column and an unrelated value column."""

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(100))


class Document(BaseModel):
    """Model carrying a deferred column."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(50))
    body: Mapped[str] = deferred(mapped_column(String(500)))


class Animal(BaseModel):
    """Base of a joined-table inheritance hierarchy."""

    __tablename__ = "animals"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    kind: Mapped[str] = mapped_column(String(50))

    __mapper_args__ = {"polymorphic_on": "kind", "polymorphic_identity": "animal"}


class Dog(Animal):
    """Child of a joined-table inheritance hierarchy."""

    __tablename__ = "dogs"

    id: Mapped[int] = mapped_column(ForeignKey("animals.id"), primary_key=True)
    breed: Mapped[str] = mapped_column(String(50))

    __mapper_args__ = {"polymorphic_identity": "dog"}


@contextmanager
def recorded_statements(session: Session) -> Iterator[list[str]]:
    """Record every SQL statement the session's engine executes in the block."""
    statements: list[str] = []
    engine = session.get_bind()

    def record(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


def test_uuid_primary_key_receives_a_uuid_object(session: Session) -> None:
    instance = UuidKeyed.create(name="uuid")

    assert isinstance(instance.id, uuid.UUID)


def test_non_native_uuid_primary_key_receives_a_hex_string(session: Session) -> None:
    instance = HexUuidKeyed.create(name="hex uuid")

    assert isinstance(instance.id, str)
    assert len(instance.id) == 32


@pytest.mark.parametrize("model", [WideStringKeyed, UnboundedStringKeyed])
def test_string_primary_key_receives_a_hex_identifier(
    session: Session,
    model: type[WideStringKeyed] | type[UnboundedStringKeyed],
) -> None:
    instance = model.create(name="string")

    assert isinstance(instance.id, str)
    assert len(instance.id) == 32
    assert int(instance.id, 16) >= 0


@pytest.mark.parametrize(
    ("model", "values"),
    [
        (NarrowStringKeyed, {"name": "narrow"}),
        (ManualIntegerKeyed, {"name": "manual"}),
        (OwnedProfile, {"bio": "no owner"}),
    ],
)
def test_unsuitable_primary_key_is_not_generated(
    session: Session,
    model: type[BaseModel],
    values: dict[str, Any],
) -> None:
    with pytest.raises(SQLAlchemyError):
        model.create(**values)

    session.rollback()


def test_supplied_primary_key_is_never_replaced(session: Session) -> None:
    manual = ManualIntegerKeyed.create(id=7, name="manual")
    narrow = NarrowStringKeyed.create(id="short", name="narrow")

    assert manual.id == 7
    assert narrow.id == "short"


def test_explicit_session_creation_generates_an_identifier(session: Session) -> None:
    instance = WideStringKeyed.create_with_session(session, name="explicit")

    assert len(instance.id) == 32


def test_get_or_create_returns_existing_row_when_defaults_differ(
    session: Session,
) -> None:
    Account.create(email="hamza@example.com", name="Hamza")
    session.flush()

    found = Account.get_or_create(
        email="hamza@example.com",
        defaults={"name": "New name"},
    )

    assert found.name == "Hamza"
    assert len(Account.all()) == 1


def test_get_or_create_applies_defaults_on_a_miss(session: Session) -> None:
    created = Account.get_or_create(
        email="new@example.com",
        defaults={"name": "New name"},
    )

    assert created.name == "New name"
    assert created.email == "new@example.com"


def test_get_or_create_without_defaults_still_creates_from_every_value(
    session: Session,
) -> None:
    created = Account.get_or_create(email="plain@example.com", name="Plain")

    assert created.name == "Plain"
    assert Account.get_or_create(email="plain@example.com", name="Plain") is created


def test_repr_of_a_detached_expired_instance_emits_no_sql(session: Session) -> None:
    document = Document.create(id=1, title="Title", body="Body")
    session.flush()
    session.expire(document)
    session.expunge(document)

    with recorded_statements(session) as statements:
        rendered = repr(document)

    assert statements == []
    assert rendered == (
        "Document(id=<not loaded>, title=<not loaded>, body=<not loaded>)"
    )


def test_repr_does_not_load_a_deferred_column(session: Session) -> None:
    Document.create(id=2, title="Deferred", body="Body")
    session.flush()
    session.expunge_all()
    loaded = Document.get_by_pk(2)
    assert loaded is not None

    with recorded_statements(session) as statements:
        rendered = repr(loaded)

    assert statements == []
    assert "title='Deferred'" in rendered
    assert "body=<not loaded>" in rendered


def test_repr_of_a_transient_instance_emits_no_sql(session: Session) -> None:
    transient = Document(title="Never added")

    with recorded_statements(session) as statements:
        rendered = repr(transient)

    assert statements == []
    assert "title='Never added'" in rendered
    assert "id=<not loaded>" in rendered


def test_to_dict_and_repr_include_inherited_columns(session: Session) -> None:
    dog = Dog.create(name="Rex", breed="labrador")
    session.flush()

    assert dog.to_dict() == {
        "id": dog.id,
        "name": "Rex",
        "kind": "dog",
        "breed": "labrador",
    }
    assert repr(dog) == (
        f"Dog(id={dog.id!r}, name='Rex', kind='dog', breed='labrador')"
    )


def test_to_dict_uses_renamed_imperative_attribute_names() -> None:
    mapper_registry = registry()
    ticket_table = Table(
        "tickets",
        mapper_registry.metadata,
        Column("id", Integer, primary_key=True),
        Column("reference", String(100), nullable=False),
    )

    class Ticket(ActiveRecordMixin):
        id: int
        ref: str

    mapper_registry.map_imperatively(
        Ticket, ticket_table, properties={"ref": ticket_table.c.reference}
    )
    engine = create_engine("sqlite:///:memory:")
    mapper_registry.metadata.create_all(engine)
    previous_provider = ActiveRecordMixin._session_provider

    try:
        with Session(engine, expire_on_commit=False) as ticket_session:
            ActiveRecordMixin.register_session_provider(lambda: ticket_session)
            ticket = Ticket.create(id=1, ref="R-1")
            ticket_session.flush()

            assert ticket.to_dict() == {"id": 1, "ref": "R-1"}
            assert repr(ticket) == "Ticket(id=1, ref='R-1')"
    finally:
        ActiveRecordMixin._session_provider = previous_provider
        engine.dispose()
