"""Shared database fixtures for sqlarec tests."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Boolean, String, create_engine
from sqlalchemy.orm import Mapped, Session, mapped_column

from sqlarec import BaseModel


class User(BaseModel):
    """Test model used across the suite."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


@pytest.fixture
def session() -> Iterator[Session]:
    """Provide an isolated in-memory database session."""
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as current_session:
        BaseModel.register_session_provider(lambda: current_session)
        yield current_session
        current_session.rollback()
    engine.dispose()
