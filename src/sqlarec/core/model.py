"""Session-independent helpers shared by synchronous and asynchronous models."""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy import Integer, inspect
from sqlalchemy import Sequence as SQLSequence
from sqlalchemy.orm import InstanceState, Mapper

from sqlarec.utils import generate_identifier


class _ModelMixin:
    """Provide model inspection and serialization without performing I/O."""

    @classmethod
    def _mapper(cls) -> Mapper[Any]:
        """Return SQLAlchemy's mapper inspection for this model."""
        return cast(Mapper[Any], inspect(cls))

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
        return tuple(cast(str, column.key) for column in cls._mapper().primary_key)

    @classmethod
    def has_one_primary_key(cls) -> bool:
        """Return whether the model has one primary-key column."""
        return len(cls._mapper().primary_key) == 1

    @classmethod
    def is_auto_increment(cls) -> bool:
        """Return whether the single primary key uses integer auto-increment."""
        if not cls.has_one_primary_key():
            return False
        primary_key = cls._mapper().primary_key[0]
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
        primary_key = cls._mapper().primary_key[0]
        return primary_key.default is not None or primary_key.server_default is not None

    @classmethod
    def is_following_sequence(cls) -> bool:
        """Return whether the single primary key uses a default or sequence."""
        if not cls.has_one_primary_key():
            return False
        primary_key = cls._mapper().primary_key[0]
        return primary_key.server_default is not None or isinstance(
            primary_key.default,
            SQLSequence,
        )

    @classmethod
    def _prepare_create_values(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Return creation values with a generated identifier when required."""
        prepared = values.copy()
        if (
            cls.has_one_primary_key()
            and cls.get_primary_key_name() not in prepared
            and not cls.is_auto_increment()
            and not cls.has_primary_key_default()
        ):
            prepared[cls.get_primary_key_name()] = generate_identifier()
        return prepared

    def to_dict(self) -> dict[str, Any]:
        """Return mapped column values keyed by column name."""
        table = cast(Any, self).__table__
        return {column.key: getattr(self, column.key) for column in table.columns}

    def __repr__(self) -> str:
        state = cast(InstanceState[Any], inspect(self))
        identity = state.identity
        if identity is None:
            return f"{type(self).__name__}()"
        values = ", ".join(
            f"{name}={value!r}"
            for name, value in zip(self.get_primary_key_names(), identity, strict=True)
        )
        return f"{type(self).__name__}({values})"

    @classmethod
    def _identity_from_values(cls, values: dict[str, Any]) -> Any | None:
        """Return a supplied complete primary-key identity, if present."""
        names = cls.get_primary_key_names()
        if not all(name in values for name in names):
            return None
        identity = tuple(values[name] for name in names)
        return identity[0] if len(identity) == 1 else identity
