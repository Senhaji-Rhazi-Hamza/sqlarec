"""Mapping-independent async helpers and the default declarative base."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, ClassVar, Self, overload

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from sqlarec.asyncio.query import (
    AsyncModelQuery,
    AsyncRowQuery,
    _AsyncModelQueryProperty,
)
from sqlarec.asyncio.update import AsyncUpdate
from sqlarec.core.descriptors import _ClassProperty
from sqlarec.core.model import _ModelMixin


class AsyncActiveRecordMixin(AsyncAttrs, _ModelMixin):
    """Mapping-independent asynchronous Active Record helpers.

    Register an async-session provider before model operations. Write helpers
    flush changes but never commit, leaving transaction ownership with the
    application. The class must be mapped by SQLAlchemy before using helpers
    that inspect or query it.
    """

    __abstract__ = True

    _session_provider: ClassVar[Callable[[], AsyncSession] | None] = None
    query = _AsyncModelQueryProperty()

    @classmethod
    def register_session_provider(
        cls,
        provider: Callable[[], AsyncSession],
    ) -> None:
        """Register the callback used to obtain the current async session.

        Providers can only be registered on an abstract model base. Concrete
        descendants inherit the provider from their nearest configured base.

        Raises:
            TypeError: If called on a concrete mapped model.
        """
        if not cls.__dict__.get("__abstract__", False):
            raise TypeError(
                "Session providers must be registered on an abstract model base."
            )
        cls._session_provider = provider

    @classmethod
    def _get_session_provider(cls) -> Callable[[], AsyncSession]:
        """Return the provider inherited by this async model base."""
        provider = cls._session_provider
        if provider is None:
            raise RuntimeError(
                "No async session provider registered. Call "
                "AsyncActiveRecordMixin.register_session_provider() or register "
                "it on an abstract model base at app startup."
            )
        return provider

    @_ClassProperty
    def session(cls) -> AsyncSession:
        """Return the current async session supplied by the provider.

        Raises:
            RuntimeError: If no async-session provider has been registered.
        """
        return cls._get_session_provider()()

    @overload
    @classmethod
    def select(cls) -> AsyncModelQuery[Self]: ...

    @overload
    @classmethod
    def select(cls, *entities: Any) -> AsyncRowQuery: ...

    @classmethod
    def select(cls, *entities: Any) -> AsyncModelQuery[Self] | AsyncRowQuery:
        """Create an async entity query or row query."""
        if entities:
            return AsyncRowQuery(select(*entities), cls._get_session_provider())
        return AsyncModelQuery(select(cls), cls._get_session_provider())

    @classmethod
    def update(cls) -> AsyncUpdate:
        """Create an immutable asynchronous update wrapper."""
        return AsyncUpdate(update(cls), cls._get_session_provider())

    @classmethod
    async def create(cls, **values: Any) -> Self:
        """Construct, add, and flush a model without committing."""
        return await cls.create_instance(**cls._prepare_create_values(values))

    @classmethod
    async def create_instance(cls, **values: Any) -> Self:
        """Construct, add, and flush without generating an identifier."""
        instance = cls(**values)
        return await instance.save()

    async def save(self) -> Self:
        """Add and flush this model without committing the transaction."""
        session = self.session
        session.add(self)
        await session.flush()
        return self

    async def delete(self) -> None:
        """Delete and flush this model without committing the transaction."""
        session = self.session
        await session.delete(self)
        await session.flush()

    @classmethod
    async def get_by_pk(cls, value: Any) -> Self | None:
        """Return the model with a primary-key identity, or ``None``."""
        return await cls.session.get(cls, value)

    @classmethod
    async def exists(cls, value: Any) -> bool:
        """Return whether a model exists for a primary-key identity."""
        return await cls.get_by_pk(value) is not None

    @classmethod
    async def get_or_create(cls, **values: Any) -> Self:
        """Return a matching model or create and flush a new one."""
        identity = cls._identity_from_values(values)
        if identity is not None:
            instance = await cls.get_by_pk(identity)
        else:
            instance = await cls.get_instance_by_keys(**values)
        return await cls.create(**values) if instance is None else instance

    @classmethod
    async def all(cls) -> Sequence[Self]:
        """Return every row mapped by this model."""
        return await cls.query.all()

    @classmethod
    async def get_instance_by_keys(cls, **values: Any) -> Self | None:
        """Return zero or one model matching mapped attribute values."""
        return await cls.query.filter_by(**values).one_or_none()

    @classmethod
    async def filter_by_keys(cls, **values: Any) -> Sequence[Self]:
        """Return all models matching mapped attribute values."""
        return await cls.query.filter_by(**values).all()


class AsyncBaseModel(AsyncActiveRecordMixin, DeclarativeBase):
    """Default declarative base with asynchronous Active Record capabilities."""

    __abstract__ = True
