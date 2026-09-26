"""Immutable wrappers around a backend-neutral ORM upsert API."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any, Generic, Self, TypeVar, cast, overload

from sqlalchemy import Column, Table, UniqueConstraint, inspect
from sqlalchemy import Insert as SQLInsert
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import MappingResult, Result, Row, ScalarResult
from sqlalchemy.orm import ColumnProperty, Mapper, Session

from sqlarec.core.insert import BulkParameters

ModelT = TypeVar("ModelT")
SessionT = TypeVar("SessionT")


class UpsertBuilder(Generic[SessionT]):
    """Build a native upsert without mutating earlier wrapper objects."""

    def __init__(
        self,
        model: type[Any],
        session: SessionT | Callable[[], SessionT],
        parameters: BulkParameters | None = None,
        conflict_attributes: tuple[str, ...] = (),
        update_attributes: tuple[str, ...] = (),
        returning_expressions: tuple[Any, ...] = (),
        returning_options: Mapping[str, Any] | None = None,
        execution_options: Mapping[str, Any] | None = None,
    ) -> None:
        """Initialize an upsert builder with instance-owned state."""
        self._model = model
        self._parameters = parameters
        self._conflict_attributes = conflict_attributes
        self._update_attributes = update_attributes
        self._returning_expressions = returning_expressions
        self._returning_options = dict(returning_options or {})
        self._execution_options = dict(execution_options or {})
        if callable(session):
            self._session_provider = cast(Callable[[], SessionT], session)
        else:
            self._session_provider = lambda: session

    @property
    def session(self) -> SessionT:
        """Resolve and return the session for the current execution context."""
        return self._session_provider()

    @property
    def parameters(self) -> BulkParameters:
        """Return independent dictionaries containing the candidate rows."""
        return tuple(dict(values) for values in self._parameters or ())

    @property
    def statement(self) -> SQLInsert:
        """Build the native statement for the currently resolved session.

        Unlike other statement wrappers, an upsert must resolve its session
        before exposing a statement because SQLAlchemy provides native upsert
        constructs through individual database dialects.
        """
        parameters = self._validate_complete()
        session = cast(Any, self.session)
        dialect_name = session.get_bind(mapper=self._model).dialect.name
        if dialect_name == "postgresql":
            statement = postgresql_insert(self._model).values(parameters)
        elif dialect_name == "sqlite":
            statement = sqlite_insert(self._model).values(parameters)
        else:
            raise NotImplementedError(
                f"Native upsert is not supported for the {dialect_name!r} database."
            )

        conflict_columns = [
            self._column_for_attribute(name) for name in self._conflict_attributes
        ]
        update_values: dict[Column[Any], Any] = {}
        for name in self._update_attributes:
            column = self._column_for_attribute(name)
            update_values[column] = statement.excluded[column.key]
        statement = statement.on_conflict_do_update(
            index_elements=conflict_columns,
            set_=update_values,
        )
        if self._returning_expressions:
            statement = statement.returning(
                *self._returning_expressions,
                **self._returning_options,
            )
        if self._execution_options:
            statement = statement.execution_options(**self._execution_options)
        return cast(SQLInsert, statement)

    def _copy(
        self,
        *,
        session: SessionT | Callable[[], SessionT] | None = None,
        conflict_attributes: tuple[str, ...] | None = None,
        update_attributes: tuple[str, ...] | None = None,
        returning_expressions: tuple[Any, ...] | None = None,
        returning_options: Mapping[str, Any] | None = None,
        execution_options: Mapping[str, Any] | None = None,
    ) -> Self:
        return self.__class__(
            self._model,
            self._session_provider if session is None else session,
            self._parameters,
            self._conflict_attributes
            if conflict_attributes is None
            else conflict_attributes,
            self._update_attributes if update_attributes is None else update_attributes,
            self._returning_expressions
            if returning_expressions is None
            else returning_expressions,
            self._returning_options if returning_options is None else returning_options,
            self._execution_options if execution_options is None else execution_options,
        )

    def with_session(self, session: SessionT) -> Self:
        """Return an upsert bound to a specific session."""
        return self._copy(session=lambda: session)

    def values(self, rows: Iterable[Mapping[str, Any]]) -> Self:
        """Return an upsert containing non-empty candidate mappings.

        Every mapping must contain the same mapped Python attribute names.
        Tuples and ORM instances are intentionally not accepted.
        """
        if isinstance(rows, Mapping):
            raise TypeError(
                "values() expects an iterable of mappings, not one mapping."
            )

        prepared: list[dict[str, Any]] = []
        expected_keys: set[str] | None = None
        mapped_names = set(self._mapper().column_attrs.keys())
        for row in rows:
            if not isinstance(row, Mapping):
                raise TypeError("Each upsert row must be a mapping.")
            if not all(isinstance(key, str) for key in row):
                raise TypeError("Upsert mapping keys must be strings.")
            values = dict(row)
            unknown = set(values).difference(mapped_names)
            if unknown:
                names = ", ".join(sorted(unknown))
                raise ValueError(f"Unknown mapped attribute(s): {names}.")
            keys = set(values)
            if expected_keys is None:
                expected_keys = keys
            elif keys != expected_keys:
                raise ValueError("Every upsert mapping must contain the same keys.")
            prepared.append(values)

        if not prepared:
            raise ValueError("values() requires at least one mapping.")

        return self.__class__(
            self._model,
            self._session_provider,
            tuple(prepared),
            self._conflict_attributes,
            self._update_attributes,
            self._returning_expressions,
            self._returning_options,
            self._execution_options,
        )

    def on_conflict(self, *attributes: Any) -> Self:
        """Return an upsert matched by a primary or unique mapped key."""
        names = self._attribute_names(attributes, operation="conflict")
        self._validate_unique_target(names)
        return self._copy(conflict_attributes=names)

    def update_existing(self, *attributes: Any) -> Self:
        """Return an upsert that copies candidate values into existing rows."""
        names = self._attribute_names(attributes, operation="update")
        primary_keys = set(self._primary_key_attribute_names())
        forbidden = primary_keys.union(self._conflict_attributes)
        invalid = forbidden.intersection(names)
        if invalid:
            joined = ", ".join(sorted(invalid))
            raise ValueError(
                f"Primary-key and conflict attributes cannot be updated: {joined}."
            )
        return self._copy(update_attributes=names)

    def execution_options(self, **kwargs: Any) -> Self:
        """Return an upsert with SQLAlchemy execution options applied."""
        return self._copy(
            execution_options={**self._execution_options, **kwargs},
        )

    def compile(self, *args: Any, **kwargs: Any) -> Any:
        """Compile the native statement for the current session."""
        return self.statement.compile(*args, **kwargs)

    def _mapper(self) -> Mapper[Any]:
        return cast(Mapper[Any], inspect(self._model))

    def _attribute_names(
        self,
        attributes: tuple[Any, ...],
        *,
        operation: str,
    ) -> tuple[str, ...]:
        if not attributes:
            raise ValueError(f"{operation} attributes cannot be empty.")

        mapper = self._mapper()
        names: list[str] = []
        for attribute in attributes:
            key = getattr(attribute, "key", None)
            property_ = getattr(attribute, "property", None)
            mapped_property = mapper.attrs.get(key) if isinstance(key, str) else None
            if (
                not isinstance(mapped_property, ColumnProperty)
                or mapped_property is not property_
                or len(mapped_property.columns) != 1
                or not isinstance(mapped_property.columns[0], Column)
            ):
                raise ValueError(
                    f"Every {operation} target must be a mapped column "
                    f"on {self._model.__name__}."
                )
            names.append(cast(str, key))

        if len(set(names)) != len(names):
            raise ValueError(f"Duplicate {operation} attributes are not allowed.")
        return tuple(names)

    def _column_for_attribute(self, name: str) -> Column[Any]:
        property_ = cast(ColumnProperty[Any], self._mapper().attrs[name])
        return cast(Column[Any], property_.columns[0])

    def _primary_key_attribute_names(self) -> tuple[str, ...]:
        mapper = self._mapper()
        return tuple(
            mapper.get_property_by_column(column).key for column in mapper.primary_key
        )

    def _validate_unique_target(self, names: tuple[str, ...]) -> None:
        mapper = self._mapper()
        if len(mapper.tables) != 1:
            raise ValueError("Upsert does not support multi-table mappings.")

        columns = tuple(self._column_for_attribute(name) for name in names)
        target = frozenset(columns)
        table = cast(Table, mapper.local_table)
        unique_targets: set[frozenset[Column[Any]]] = {
            frozenset(constraint.columns)
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        }
        for index in table.indexes:
            has_predicate = any(
                options.get("where") is not None
                for options in index.dialect_options.values()
            )
            if (
                index.unique
                and not has_predicate
                and all(
                    isinstance(expression, Column) for expression in index.expressions
                )
            ):
                unique_targets.add(frozenset(index.columns))
        unique_targets.add(
            frozenset(cast(Column[Any], column) for column in mapper.primary_key)
        )
        if target not in unique_targets:
            joined = ", ".join(names)
            raise ValueError(
                f"Conflict attributes must match a primary or unique key: {joined}."
            )

    def _validate_complete(self) -> BulkParameters:
        if self._parameters is None:
            raise ValueError("Call values() before building an upsert statement.")
        if not self._conflict_attributes:
            raise ValueError("Call on_conflict() before building an upsert statement.")
        if not self._update_attributes:
            raise ValueError(
                "Call update_existing() before building an upsert statement."
            )

        identity_attributes = set(self._conflict_attributes).union(
            self._primary_key_attribute_names()
        )
        invalid_updates = identity_attributes.intersection(self._update_attributes)
        if invalid_updates:
            joined = ", ".join(sorted(invalid_updates))
            raise ValueError(
                f"Primary-key and conflict attributes cannot be updated: {joined}."
            )

        keys = set(self._parameters[0])
        missing_conflict = set(self._conflict_attributes).difference(keys)
        if missing_conflict:
            joined = ", ".join(sorted(missing_conflict))
            raise ValueError(
                f"Every upsert row must contain conflict values: {joined}."
            )
        missing_updates = set(self._update_attributes).difference(keys)
        if missing_updates:
            joined = ", ".join(sorted(missing_updates))
            raise ValueError(f"Every upsert row must contain update values: {joined}.")
        return self._parameters


class Upsert(UpsertBuilder[Session]):
    """Execute an upsert or select a typed returning wrapper."""

    @overload
    def returning(
        self,
        entity: type[ModelT],
        /,
        **kwargs: Any,
    ) -> ModelUpsert[ModelT]: ...

    @overload
    def returning(
        self,
        column: Any,
        /,
        *columns: Any,
        **kwargs: Any,
    ) -> RowUpsert: ...

    def returning(
        self,
        entity_or_column: Any,
        /,
        *columns: Any,
        **kwargs: Any,
    ) -> ModelUpsert[Any] | RowUpsert:
        """Return an entity or row upsert for the returning expressions."""
        expressions = (entity_or_column, *columns)
        wrapper: type[ModelUpsert[Any]] | type[RowUpsert]
        if len(expressions) == 1 and isinstance(
            inspect(entity_or_column, raiseerr=False),
            Mapper,
        ):
            wrapper = ModelUpsert
        else:
            wrapper = RowUpsert
        return wrapper(
            self._model,
            self._session_provider,
            self._parameters,
            self._conflict_attributes,
            self._update_attributes,
            expressions,
            kwargs,
            self._execution_options,
        )

    def execute(self) -> Result[Any]:
        """Execute the upsert without committing the transaction."""
        return self.session.execute(self.statement)


class ModelUpsert(UpsertBuilder[Session], Generic[ModelT]):
    """Execute an upsert that returns mapped model instances."""

    def execute(self) -> ScalarResult[ModelT]:
        """Execute the upsert and refresh identities already in the session."""
        return self.session.scalars(
            self.statement,
            execution_options={"populate_existing": True},
        )

    def all(self) -> Sequence[ModelT]:
        """Return all models produced by the upsert."""
        return self.execute().all()

    def first(self) -> ModelT | None:
        """Return the first produced model, or ``None``."""
        return self.execute().first()

    def one(self) -> ModelT:
        """Return exactly one produced model."""
        return self.execute().one()

    def one_or_none(self) -> ModelT | None:
        """Return zero or one produced model."""
        return self.execute().one_or_none()


class RowUpsert(UpsertBuilder[Session]):
    """Execute an upsert that returns SQLAlchemy rows."""

    def execute(self) -> Result[Any]:
        """Execute the upsert and return its row result."""
        return self.session.execute(self.statement)

    def all(self) -> Sequence[Row[Any]]:
        """Return all rows produced by the upsert."""
        return self.execute().all()

    def first(self) -> Row[Any] | None:
        """Return the first produced row, or ``None``."""
        return self.execute().first()

    def one(self) -> Row[Any]:
        """Return exactly one produced row."""
        return self.execute().one()

    def one_or_none(self) -> Row[Any] | None:
        """Return zero or one produced row."""
        return self.execute().one_or_none()

    def mappings(self) -> MappingResult:
        """Execute the upsert and return mapping-style rows."""
        return self.execute().mappings()
