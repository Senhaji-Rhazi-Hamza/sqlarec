"""Shared database fixtures for sqlarec tests."""

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from sqlalchemy import Boolean, String, create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Mapped, Session, mapped_column

from sqlarec import BaseModel
from sqlarec.asyncio import AsyncBaseModel


class User(BaseModel):
    """Test model used across the suite."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AsyncUser(AsyncBaseModel):
    """Async test model used across the suite."""

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


@pytest_asyncio.fixture
async def async_session() -> AsyncIterator[AsyncSession]:
    """Provide an isolated asynchronous in-memory database session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(AsyncBaseModel.metadata.create_all)
    async with AsyncSession(engine, expire_on_commit=False) as current_session:
        AsyncBaseModel.register_session_provider(lambda: current_session)
        yield current_session
        await current_session.rollback()
    await engine.dispose()
