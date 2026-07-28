"""Immutable wrappers around SQLAlchemy update statements."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, Self, TypeVar, cast, overload

from sqlalchemy import Update as SQLUpdate
from sqlalchemy import inspect
from sqlalchemy.engine import CursorResult, MappingResult, Result, Row, ScalarResult
from sqlalchemy.orm import Mapper, Session

ModelT = TypeVar("ModelT")
SessionT = TypeVar("SessionT")


class UpdateBuilder(Generic[SessionT]):
    """Build an update statement without mutating earlier wrapper objects."""

    def __init__(self, statement: SQLUpdate, session: SessionT) -> None:
        """Initialize a wrapper for a statement and its execution session."""
        self.statement = statement
        self.session = session

    def _new(self, statement: SQLUpdate) -> Self:
        return self.__class__(statement, self.session)

    def where(self, *criteria: Any) -> Self:
        """Return an update with SQL ``WHERE`` criteria applied."""
        return self._new(self.statement.where(*criteria))

    def values(self, *args: Any, **kwargs: Any) -> Self:
        """Return an update with new column values applied."""
        return self._new(self.statement.values(*args, **kwargs))

    def execution_options(self, **kwargs: Any) -> Self:
        """Return an update with SQLAlchemy execution options applied."""
        return self._new(self.statement.execution_options(**kwargs))

    def compile(self, *args: Any, **kwargs: Any) -> Any:
        """Compile the wrapped statement with SQLAlchemy."""
        return self.statement.compile(*args, **kwargs)


class Update(UpdateBuilder[Session]):
    """Execute an update or choose a typed wrapper for returned values."""

    @overload
    def returning(
        self,
        entity: type[ModelT],
        /,
        **kwargs: Any,
    ) -> ModelUpdate[ModelT]: ...

    @overload
    def returning(
        self,
        column: Any,
        /,
        *columns: Any,
        **kwargs: Any,
    ) -> RowUpdate: ...

    def returning(
        self,
        entity_or_column: Any,
        /,
        *columns: Any,
        **kwargs: Any,
    ) -> ModelUpdate[Any] | RowUpdate:
        """Return an entity or row update based on the returning expression."""
        expressions = (entity_or_column, *columns)
        statement = self.statement.returning(*expressions, **kwargs)
        if len(expressions) == 1 and isinstance(
            inspect(entity_or_column, raiseerr=False),
            Mapper,
        ):
            return ModelUpdate(statement, self.session)
        return RowUpdate(statement, self.session)

    def execute(self) -> CursorResult[Any]:
        """Execute the update and return its cursor result."""
        return cast(CursorResult[Any], self.session.execute(self.statement))


class ModelUpdate(UpdateBuilder[Session], Generic[ModelT]):
    """Execute an update that returns mapped model instances."""

    def execute(self) -> ScalarResult[ModelT]:
        """Execute the update and return its scalar result."""
        return self.session.scalars(self.statement)

    def all(self) -> Sequence[ModelT]:
        """Return all updated model instances."""
        return self.execute().all()

    def first(self) -> ModelT | None:
        """Return the first updated model, or ``None``."""
        return self.execute().first()

    def one(self) -> ModelT:
        """Return exactly one updated model."""
        return self.execute().one()

    def one_or_none(self) -> ModelT | None:
        """Return zero or one updated model."""
        return self.execute().one_or_none()


class RowUpdate(UpdateBuilder[Session]):
    """Execute an update that returns SQLAlchemy rows."""

    def execute(self) -> Result[Any]:
        """Execute the update and return its row result."""
        return self.session.execute(self.statement)

    def all(self) -> Sequence[Row[Any]]:
        """Return all rows produced by the update."""
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
        """Execute the update and return mapping-style rows."""
        return self.execute().mappings()
