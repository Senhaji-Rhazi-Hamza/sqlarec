"""Tests for the public Active Record model API."""

from contextvars import ContextVar

import pytest
from sqlalchemy import Column, Integer, String, Table, create_engine, inspect, select
from sqlalchemy.orm import Mapped, Session, mapped_column, registry

from conftest import User
from sqlarec import ActiveRecordMixin, BaseModel, ModelQuery


def test_session_requires_registered_provider() -> None:
    previous_provider = BaseModel._session_provider
    BaseModel._session_provider = None
    try:
        try:
            _ = User.session
        except RuntimeError as error:
            assert "register_session_provider" in str(error)
        else:
            raise AssertionError("accessing session should have failed")
    finally:
        BaseModel._session_provider = previous_provider


def test_session_provider_cannot_be_registered_on_concrete_model(
    session: Session,
) -> None:
    with pytest.raises(TypeError, match="abstract model base"):
        User.register_session_provider(lambda: session)


def test_abstract_model_base_owns_its_session_provider(session: Session) -> None:
    class ApplicationBase(BaseModel):
        __abstract__ = True

    class ApplicationUser(ApplicationBase):
        __tablename__ = "application_users"

        id: Mapped[int] = mapped_column(primary_key=True)

    ApplicationBase.register_session_provider(lambda: session)

    assert ApplicationUser.session is session
    assert "_session_provider" in ApplicationBase.__dict__


def test_builders_resolve_the_session_when_executed() -> None:
    engine_a = create_engine("sqlite:///:memory:")
    engine_b = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine_a)
    BaseModel.metadata.create_all(engine_b)
    previous_provider = BaseModel._session_provider

    try:
        with Session(engine_a) as session_a, Session(engine_b) as session_b:
            session_a.add(
                User(id=1, name="Tenant A", email="a@example.com", active=False)
            )
            session_b.add(
                User(id=1, name="Tenant B", email="b@example.com", active=False)
            )
            session_a.commit()
            session_b.commit()

            current_session = ContextVar[Session]("current_session")
            BaseModel.register_session_provider(current_session.get)

            current_session.set(session_a)
            query = User.query
            rows = User.select(User.name)
            user_update = User.update().where(User.id == 1).values(active=True)

            current_session.set(session_b)

            assert query.one().name == "Tenant B"
            assert rows.one() == ("Tenant B",)
            assert user_update.execute().rowcount == 1
            session_b.commit()
            assert session_a.scalar(select(User.active)) is False
            assert session_b.scalar(select(User.active)) is True
    finally:
        BaseModel._session_provider = previous_provider
        engine_a.dispose()
        engine_b.dispose()


def test_builders_use_explicit_session_without_provider(session: Session) -> None:
    previous_provider = BaseModel._session_provider
    BaseModel._session_provider = None

    try:
        session.add(
            User(
                name="Hamza",
                email="hamza@example.com",
                active=False,
            )
        )
        session.flush()

        query = User.query.filter_by(email="hamza@example.com")
        rows = User.select(User.name).where(User.email == "hamza@example.com")
        user_update = User.update().where(User.email == "hamza@example.com")

        assert query.with_session(session).one().name == "Hamza"
        assert rows.with_session(session).one() == ("Hamza",)
        assert (
            user_update.with_session(session).values(active=True).execute().rowcount
            == 1
        )
        assert query.with_session(session).one().active

        with pytest.raises(RuntimeError, match="register_session_provider"):
            User.query.all()
    finally:
        BaseModel._session_provider = previous_provider


def test_create_flushes_without_committing(session: Session) -> None:
    user = User.create(name="Hamza", email="hamza@example.com")

    assert user.id is not None
    assert session.in_transaction()
    assert User.get_by_pk(user.id) is user


def test_explicit_session_creation_and_attached_writes_override_provider() -> None:
    provider_engine = create_engine("sqlite:///:memory:")
    explicit_engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(provider_engine)
    BaseModel.metadata.create_all(explicit_engine)
    previous_provider = BaseModel._session_provider

    try:
        with (
            Session(provider_engine) as provider_session,
            Session(explicit_engine) as explicit_session,
        ):
            BaseModel.register_session_provider(lambda: provider_session)

            user = User.create_with_session(
                explicit_session,
                name="Hamza",
                email="hamza@example.com",
            )
            assert inspect(user).session is explicit_session

            user.name = "Hamza S."
            assert user.save() is user
            assert User.query.with_session(explicit_session).one().name == "Hamza S."

            user.delete()
            assert User.query.with_session(explicit_session).one_or_none() is None
            assert User.query.with_session(provider_session).one_or_none() is None
    finally:
        BaseModel._session_provider = previous_provider
        provider_engine.dispose()
        explicit_engine.dispose()


def test_save_delete_and_exists(session: Session) -> None:
    user = User(name="Hamza", email="hamza@example.com").save()

    assert User.exists(user.id)

    user.delete()

    assert not User.exists(user.id)


def test_get_or_create_reuses_matching_model(session: Session) -> None:
    existing = User.create(name="Hamza", email="hamza@example.com")

    found = User.get_or_create(email="hamza@example.com")

    assert found is existing


def test_primary_key_and_serialization_helpers(session: Session) -> None:
    user = User.create(name="Hamza", email="hamza@example.com")

    assert User.get_primary_key_name() == "id"
    assert User.get_primary_key_names() == ("id",)
    assert User.has_one_primary_key()
    assert User.is_auto_increment()
    assert user.get_id() == user.id
    assert user.to_dict() == {
        "id": user.id,
        "name": "Hamza",
        "email": "hamza@example.com",
        "active": True,
    }
    assert repr(user).startswith("User(id=")


def test_imperatively_mapped_active_record_mixin_has_full_api() -> None:
    mapper_registry = registry()
    booking_table = Table(
        "bookings",
        mapper_registry.metadata,
        Column("id", Integer, primary_key=True),
        Column("reference", String(100), nullable=False),
    )

    class BookingBehaviour:
        reference: str

        def label(self) -> str:
            return f"Booking {self.reference}"

    class Booking(BookingBehaviour, ActiveRecordMixin):
        id: int
        reference: str

    mapper_registry.map_imperatively(Booking, booking_table)
    engine = create_engine("sqlite:///:memory:")
    mapper_registry.metadata.create_all(engine)
    previous_provider = ActiveRecordMixin._session_provider

    try:
        with Session(engine, expire_on_commit=False) as session:
            ActiveRecordMixin.register_session_provider(lambda: session)

            assert Booking.session is session
            assert isinstance(Booking.query, ModelQuery)
            assert Booking.query.statement.column_descriptions[0]["entity"] is Booking

            booking = Booking.create(reference="SQLAREC-1")
            assert booking.label() == "Booking SQLAREC-1"
            assert Booking.get_by_pk(booking.id) is booking
            assert Booking.get_instance_by_keys(reference="SQLAREC-1") is booking
            assert Booking.filter_by_keys(reference="SQLAREC-1") == [booking]
            assert Booking.all() == [booking]
            assert Booking.select(Booking.reference).one() == ("SQLAREC-1",)
            assert booking.to_dict() == {"id": booking.id, "reference": "SQLAREC-1"}

            Booking.update().where(Booking.id == booking.id).values(
                reference="SQLAREC-2"
            ).execute()
            session.refresh(booking)
            assert booking.reference == "SQLAREC-2"
            assert booking.save() is booking
            booking.delete()
            assert not Booking.exists(booking.id)
            assert session.in_transaction()
    finally:
        ActiveRecordMixin._session_provider = previous_provider
        engine.dispose()
