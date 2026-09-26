"""Immutable wrappers around SQLAlchemy ORM bulk insert statements."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any, Generic, Self, TypeVar, cast, overload

from sqlalchemy import Insert as SQLInsert
from sqlalchemy import inspect
from sqlalchemy.engine import MappingResult, Result, Row, ScalarResult
from sqlalchemy.orm import Mapper, Session

ModelT = TypeVar("ModelT")
SessionT = TypeVar("SessionT")

BulkParameters = tuple[dict[str, Any], ...]


class InsertBuilder(Generic[SessionT]):
    """Build an ORM bulk insert without mutating earlier wrapper objects."""

    def __init__(
        self,
        statement: SQLInsert,
        session: SessionT | Callable[[], SessionT],
        parameters: BulkParameters | None = None,
    ) -> None:
        """Initialize a bulk insert with a session and value normalizer."""
        self.statement = statement
        self._parameters = parameters
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
        """Return independent dictionaries containing the bulk insert values."""
        return tuple(dict(values) for values in self._parameters or ())

    def _new(self, statement: SQLInsert) -> Self:
        return self.__class__(
            statement,
            self._session_provider,
            self._parameters,
        )

    def _require_parameters(self) -> BulkParameters:
        if self._parameters is None:
            raise ValueError(
                "Call values() with at least one mapping before execution."
            )
        return self._parameters

    def with_session(self, session: SessionT) -> Self:
        """Return an insert bound to a specific session."""
        return self.__class__(
            self.statement,
            lambda: session,
            self._parameters,
        )

    def values(self, rows: Iterable[Mapping[str, Any]]) -> Self:
        """Return an insert containing normalized bulk parameter mappings.

        A mapping represents one model row and must use mapped Python attribute
        names as keys. Tuples and mapped model instances are intentionally not
        accepted because their insertion semantics are implicit or belong to
        SQLAlchemy's unit-of-work API.

        Args:
            rows: A non-empty iterable of model attribute mappings.

        Raises:
            TypeError: If ``rows`` is a single mapping or contains a non-mapping.
            ValueError: If ``rows`` is empty.
        """
        if isinstance(rows, Mapping):
            raise TypeError(
                "values() expects an iterable of mappings, not one mapping."
            )

        prepared: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, Mapping):
                raise TypeError("Each bulk insert row must be a mapping.")
            prepared.append(dict(row))

        if not prepared:
            raise ValueError("values() requires at least one mapping.")

        return self.__class__(
            self.statement,
            self._session_provider,
            tuple(prepared),
        )

    def execution_options(self, **kwargs: Any) -> Self:
        """Return an insert with SQLAlchemy execution options applied."""
        return self._new(self.statement.execution_options(**kwargs))

    def compile(self, *args: Any, **kwargs: Any) -> Any:
        """Compile the wrapped SQLAlchemy insert statement."""
        return self.statement.compile(*args, **kwargs)


class Insert(InsertBuilder[Session]):
    """Execute a bulk insert or select a typed returning wrapper."""

    @overload
    def returning(
        self,
        entity: type[ModelT],
        /,
        **kwargs: Any,
    ) -> ModelInsert[ModelT]: ...

    @overload
    def returning(
        self,
        column: Any,
        /,
        *columns: Any,
        **kwargs: Any,
    ) -> RowInsert: ...

    def returning(
        self,
        entity_or_column: Any,
        /,
        *columns: Any,
        **kwargs: Any,
    ) -> ModelInsert[Any] | RowInsert:
        """Return an entity or row insert for the returning expressions."""
        expressions = (entity_or_column, *columns)
        statement = self.statement.returning(*expressions, **kwargs)
        wrapper: type[ModelInsert[Any]] | type[RowInsert]
        if len(expressions) == 1 and isinstance(
            inspect(entity_or_column, raiseerr=False),
            Mapper,
        ):
            wrapper = ModelInsert
        else:
            wrapper = RowInsert
        return wrapper(
            statement,
            self._session_provider,
            self._parameters,
        )

    def execute(self) -> Result[Any]:
        """Execute the ORM bulk insert without committing the transaction."""
        return self.session.execute(self.statement, self._require_parameters())


class ModelInsert(InsertBuilder[Session], Generic[ModelT]):
    """Execute a bulk insert that returns mapped model instances."""

    def execute(self) -> ScalarResult[ModelT]:
        """Execute the insert and return its scalar result."""
        return self.session.scalars(self.statement, self._require_parameters())

    def all(self) -> Sequence[ModelT]:
        """Return all inserted model instances produced by ``RETURNING``."""
        return self.execute().all()

    def first(self) -> ModelT | None:
        """Return the first inserted model, or ``None``."""
        return self.execute().first()

    def one(self) -> ModelT:
        """Return exactly one inserted model."""
        return self.execute().one()

    def one_or_none(self) -> ModelT | None:
        """Return zero or one inserted model."""
        return self.execute().one_or_none()


class RowInsert(InsertBuilder[Session]):
    """Execute a bulk insert that returns SQLAlchemy rows."""

    def execute(self) -> Result[Any]:
        """Execute the insert and return its row result."""
        return self.session.execute(self.statement, self._require_parameters())

    def all(self) -> Sequence[Row[Any]]:
        """Return all rows produced by ``RETURNING``."""
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
        """Execute the insert and return mapping-style rows."""
        return self.execute().mappings()
