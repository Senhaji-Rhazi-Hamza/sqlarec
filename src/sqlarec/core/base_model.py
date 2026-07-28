"""Declarative base model with context-aware persistence helpers."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, ClassVar, Generic, Self, TypeVar, cast, overload

from sqlalchemy import Integer, inspect, select, update
from sqlalchemy import Sequence as SQLSequence
from sqlalchemy.orm import DeclarativeBase, Session

from sqlarec.core.query import ModelQuery, RowQuery, _ModelQueryProperty
from sqlarec.core.update import Update
from sqlarec.utils import generate_identifier

ValueT = TypeVar("ValueT")


class _ClassProperty(Generic[ValueT]):
    """Read-only descriptor for a value computed from a class."""

    def __init__(self, getter: Callable[[Any], ValueT]) -> None:
        self.getter = getter

    def __get__(
        self,
        instance: object | None,
        owner: type[Any],
    ) -> ValueT:
        return self.getter(owner)


class BaseModel(DeclarativeBase):
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

        The provider is shared by every model that inherits from ``BaseModel``.

        Args:
            provider: Zero-argument callable that returns the current synchronous
                SQLAlchemy session.
        """
        BaseModel._session_provider = provider

    @_ClassProperty
    def session(cls) -> Session:
        """Return the current session supplied by the registered provider.

        Raises:
            RuntimeError: If no session provider has been registered.
        """
        provider = BaseModel._session_provider
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
            return RowQuery(select(*entities), cls.session)
        return ModelQuery(select(cls), cls.session)

    @classmethod
    def update(cls) -> Update:
        """Create an immutable update wrapper for this model."""
        return Update(update(cls), cls.session)

    @classmethod
    def create(cls, **values: Any) -> Self:
        """Construct, add, and flush a model without committing.

        A string-compatible single primary key receives a UUID hex identifier
        when it has no supplied value, auto-increment behavior, or default.
        """
        if (
            cls.has_one_primary_key()
            and cls.get_primary_key_name() not in values
            and not cls.is_auto_increment()
            and not cls.has_primary_key_default()
        ):
            values[cls.get_primary_key_name()] = generate_identifier()
        return cls.create_instance(**values)

    @classmethod
    def create_instance(cls, **values: Any) -> Self:
        """Construct, add, and flush a model without generating an identifier."""
        instance = cls(**values)
        return instance.save()

    def save(self) -> Self:
        """Add and flush this model without committing the transaction."""
        self.session.add(self)
        self.session.flush()
        return self

    def delete(self) -> None:
        """Delete and flush this model without committing the transaction."""
        self.session.delete(self)
        self.session.flush()

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
        primary_key_names = cls.get_primary_key_names()
        if all(name in values for name in primary_key_names):
            identity_values = tuple(values[name] for name in primary_key_names)
            identity = (
                identity_values[0] if len(identity_values) == 1 else identity_values
            )
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

    def get_id(self) -> Any:
        """Return the model's primary-key value or composite-key tuple."""
        return self.get_primary_key_value()

    def get_primary_key_value(self) -> Any:
        """Return the primary-key value in mapper-defined column order."""
        values = tuple(getattr(self, name) for name in self.get_primary_key_names())
        return values[0] if len(values) == 1 else values

    @classmethod
    def get_primary_key_name(cls) -> str:
        """Return the primary-key name for a single-key model.

        Raises:
            RuntimeError: If the model uses a composite primary key.
        """
        names = cls.get_primary_key_names()
        if len(names) != 1:
            raise RuntimeError(
                f"{cls.__name__} must have exactly one primary key column"
            )
        return names[0]

    @classmethod
    def get_primary_key_names(cls) -> tuple[str, ...]:
        """Return primary-key names in mapper-defined order."""
        return tuple(cast(str, column.key) for column in inspect(cls).primary_key)

    @classmethod
    def has_one_primary_key(cls) -> bool:
        """Return whether the model has one primary-key column."""
        return len(inspect(cls).primary_key) == 1

    @classmethod
    def is_auto_increment(cls) -> bool:
        """Return whether the single primary key uses integer auto-increment."""
        if not cls.has_one_primary_key():
            return False
        primary_key = inspect(cls).primary_key[0]
        return primary_key.autoincrement is True or (
            primary_key.autoincrement == "auto"
            and isinstance(primary_key.type, Integer)
            and not primary_key.foreign_keys
        )

    @classmethod
    def has_primary_key_default(cls) -> bool:
        """Return whether the single primary key defines a client/server default."""
        if not cls.has_one_primary_key():
            return False
        primary_key = inspect(cls).primary_key[0]
        return primary_key.default is not None or primary_key.server_default is not None

    @classmethod
    def is_following_sequence(cls) -> bool:
        """Return whether the single primary key uses a default or sequence."""
        if not cls.has_one_primary_key():
            return False
        primary_key = inspect(cls).primary_key[0]
        return primary_key.server_default is not None or isinstance(
            primary_key.default,
            SQLSequence,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return mapped column values keyed by column name."""
        return {
            column.key: getattr(self, column.key) for column in self.__table__.columns
        }

    def __repr__(self) -> str:
        values = ", ".join(
            f"{column.key}={getattr(self, column.key)!r}"
            for column in self.__table__.columns
        )
        return f"{type(self).__name__}({values})"
