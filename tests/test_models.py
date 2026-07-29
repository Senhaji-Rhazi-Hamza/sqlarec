"""Tests for the public Active Record model API."""

import pytest
from sqlalchemy.orm import Mapped, Session, mapped_column

from conftest import User
from sqlarec import BaseModel


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


def test_create_flushes_without_committing(session: Session) -> None:
    user = User.create(name="Hamza", email="hamza@example.com")

    assert user.id is not None
    assert session.in_transaction()
    assert User.get_by_pk(user.id) is user


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
