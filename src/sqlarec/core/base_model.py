"""Declarative base model with context-aware persistence helpers."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, ClassVar, Self, overload

from sqlalchemy import select, update
from sqlalchemy.orm import DeclarativeBase, Session

from sqlarec.core.descriptors import _ClassProperty
from sqlarec.core.model import _ModelMixin
from sqlarec.core.query import ModelQuery, RowQuery, _ModelQueryProperty
from sqlarec.core.update import Update


class BaseModel(_ModelMixin, DeclarativeBase):
    """Base for SQLAlchemy models with query and persistence conveniences.

    Register a session provider before using model operations. Write helpers
    flush changes but never commit, so the application retains control of the
    transaction boundary.
    """

    __abstract__ = True

    _session_provider: ClassVar[Callable[[], Session] | None] = None
    query = _ModelQueryProperty()

    @classmethod
    def register_session_provider(cls, provider: Callable[[], Session]) -> None:
        """Register the callback used to obtain the current session.

        Providers can only be registered on an abstract model base. Concrete
        descendants inherit the provider from their nearest configured base.

        Args:
            provider: Zero-argument callable that returns the current synchronous
                SQLAlchemy session.

        Raises:
            TypeError: If called on a concrete mapped model.
        """
        if not cls.__dict__.get("__abstract__", False):
            raise TypeError(
                "Session providers must be registered on an abstract model base."
            )
        cls._session_provider = provider  # type: ignore[assignment]

    @classmethod
    def _get_session_provider(cls) -> Callable[[], Session]:
        """Return the provider inherited by this model base."""
        provider = cls._session_provider  # type: ignore
        if provider is None:
            raise RuntimeError(
                "No session provider registered. Call "
                "BaseModel.register_session_provider() at app startup."
            )
        return provider

    @_ClassProperty
    def session(cls) -> Session:
        """Return the current session supplied by the registered provider.

        Raises:
            RuntimeError: If no session provider has been registered.
        """
        provider = cls._session_provider
        if provider is None:
            raise RuntimeError(
                "No session provider registered. Call "
                "BaseModel.register_session_provider() at app startup."
            )
        return provider()

    @overload
    @classmethod
    def select(cls) -> ModelQuery[Self]: ...

    @overload
    @classmethod
    def select(cls, *entities: Any) -> RowQuery: ...

    @classmethod
    def select(cls, *entities: Any) -> ModelQuery[Self] | RowQuery:
        """Create an entity query or a row query for selected expressions."""
        if entities:
            return RowQuery(select(*entities), cls._get_session_provider())
        return ModelQuery(select(cls), cls._get_session_provider())

    @classmethod
    def update(cls) -> Update:
        """Create an immutable update wrapper for this model."""
        return Update(update(cls), cls._get_session_provider())

    @classmethod
    def create(cls, **values: Any) -> Self:
        """Construct, add, and flush a model without committing.

        A string-compatible single primary key receives a UUID hex identifier
        when it has no supplied value, auto-increment behavior, or default.
        """
        return cls.create_instance(**cls._prepare_create_values(values))

    @classmethod
    def create_instance(cls, **values: Any) -> Self:
        """Construct, add, and flush a model without generating an identifier."""
        instance = cls(**values)
        return instance.save()

    def save(self) -> Self:
        """Add and flush this model without committing the transaction."""
        session = self.session
        session.add(self)
        session.flush()
        return self

    def delete(self) -> None:
        """Delete and flush this model without committing the transaction."""
        session = self.session
        session.delete(self)
        session.flush()

    @classmethod
    def get_by_pk(cls, value: Any) -> Self | None:
        """Return the model with a primary-key identity, or ``None``."""
        return cls.session.get(cls, value)

    @classmethod
    def exists(cls, value: Any) -> bool:
        """Return whether a model exists for a primary-key identity."""
        return cls.get_by_pk(value) is not None

    @classmethod
    def get_or_create(cls, **values: Any) -> Self:
        """Return a matching model or create and flush a new one."""
        identity = cls._identity_from_values(values)
        if identity is not None:
            instance = cls.get_by_pk(identity)
        else:
            instance = cls.get_instance_by_keys(**values)
        return cls.create(**values) if instance is None else instance

    @classmethod
    def all(cls) -> Sequence[Self]:
        """Return every row mapped by this model."""
        return cls.query.all()

    @classmethod
    def get_instance_by_keys(cls, **values: Any) -> Self | None:
        """Return zero or one model matching mapped attribute values.

        SQLAlchemy raises ``MultipleResultsFound`` when the supplied attributes
        do not identify at most one row.
        """
        return cls.query.filter_by(**values).one_or_none()

    @classmethod
    def filter_by_keys(cls, **values: Any) -> Sequence[Self]:
        """Return all models matching mapped attribute values."""
        return cls.query.filter_by(**values).all()
