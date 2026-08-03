"""Immutable wrappers around SQLAlchemy select statements."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Generic, Self, TypeVar, cast

from sqlalchemy import Select, select, union, union_all
from sqlalchemy.engine import MappingResult, Result, Row, ScalarResult
from sqlalchemy.orm import Session, aliased

ModelT = TypeVar("ModelT")
SessionT = TypeVar("SessionT")


class Query(Generic[SessionT]):
    """Build a select statement without mutating earlier query objects."""

    def __init__(
        self,
        statement: Any,
        session: SessionT | Callable[[], SessionT],
    ) -> None:
        """Initialize a query with a session or context-aware provider."""
        self.statement = statement
        if callable(session):
            self._session_provider = cast(Callable[[], SessionT], session)
        else:
            self._session_provider = lambda: session

    @property
    def session(self) -> SessionT:
        """Resolve and return the session for the current execution context."""
        return self._session_provider()

    def _new(self, statement: Any) -> Self:
        return self.__class__(statement, self._session_provider)

    def where(self, *criteria: Any) -> Self:
        """Return a query with SQL ``WHERE`` criteria applied."""
        return self._new(self.statement.where(*criteria))

    def filter_by(self, **kwargs: Any) -> Self:
        """Return a query filtered by mapped attribute names."""
        return self._new(self.statement.filter_by(**kwargs))

    def order_by(self, *clauses: Any) -> Self:
        """Return a query with SQL ``ORDER BY`` clauses applied."""
        return self._new(self.statement.order_by(*clauses))

    def group_by(self, *clauses: Any) -> Self:
        """Return a query with SQL ``GROUP BY`` clauses applied."""
        return self._new(self.statement.group_by(*clauses))

    def having(self, *criteria: Any) -> Self:
        """Return a query with SQL ``HAVING`` criteria applied."""
        return self._new(self.statement.having(*criteria))

    def join(self, target: Any, *props: Any, **kwargs: Any) -> Self:
        """Return a query with an inner join applied."""
        return self._new(self.statement.join(target, *props, **kwargs))

    def outerjoin(self, target: Any, *props: Any, **kwargs: Any) -> Self:
        """Return a query with a left outer join applied."""
        return self._new(self.statement.outerjoin(target, *props, **kwargs))

    def limit(self, limit: int | None) -> Self:
        """Return a query limited to at most ``limit`` rows."""
        return self._new(self.statement.limit(limit))

    def offset(self, offset: int | None) -> Self:
        """Return a query with a row offset applied."""
        return self._new(self.statement.offset(offset))

    def distinct(self, *expressions: Any) -> Self:
        """Return a query with SQL ``DISTINCT`` applied."""
        return self._new(self.statement.distinct(*expressions))

    def options(self, *options: Any) -> Self:
        """Return a query with SQLAlchemy ORM loader options applied."""
        return self._new(self.statement.options(*options))

    def union(self, *others: Query[Any] | Select[Any]) -> Self:
        """Return a query that unions this statement with other statements."""
        statements = [
            other.statement if isinstance(other, Query) else other for other in others
        ]
        return self._new(union(self.statement, *statements))

    def union_all(self, *others: Query[Any] | Select[Any]) -> Self:
        """Return a query that unions all rows from the supplied statements."""
        statements = [
            other.statement if isinstance(other, Query) else other for other in others
        ]
        return self._new(union_all(self.statement, *statements))

    def compile(self, *args: Any, **kwargs: Any) -> Any:
        """Compile the wrapped statement with SQLAlchemy."""
        return self.statement.compile(*args, **kwargs)


class ModelQuery(Query[Session], Generic[ModelT]):
    """Execute a select statement and return mapped model instances."""

    def _compound_query(
        self,
        operation: Any,
        *others: Query[Any] | Select[Any],
    ) -> Self:
        entity = self.statement.column_descriptions[0]["entity"]
        statements = [
            other.statement if isinstance(other, Query) else other for other in others
        ]
        compound_subquery = operation(self.statement, *statements).subquery()
        entity_alias = aliased(entity, compound_subquery)
        return self.__class__(select(entity_alias), self._session_provider)

    def union(self, *others: Query[Any] | Select[Any]) -> Self:
        """Return an entity query containing distinct rows from all statements."""
        return self._compound_query(union, *others)

    def union_all(self, *others: Query[Any] | Select[Any]) -> Self:
        """Return an entity query containing every row from all statements."""
        return self._compound_query(union_all, *others)

    def execute(self) -> ScalarResult[ModelT]:
        """Execute the statement and return its scalar result."""
        return self.session.scalars(self.statement)

    def all(self) -> Sequence[ModelT]:
        """Return all matching model instances."""
        return self.execute().all()

    def first(self) -> ModelT | None:
        """Return the first matching model, or ``None``."""
        return self.session.scalars(self.statement.limit(1)).first()

    def one(self) -> ModelT:
        """Return exactly one model or raise a SQLAlchemy result error."""
        return self.execute().one()

    def one_or_none(self) -> ModelT | None:
        """Return zero or one model or raise when multiple rows match."""
        return self.execute().one_or_none()


class RowQuery(Query[Session]):
    """Execute a select statement and return SQLAlchemy rows."""

    def execute(self) -> Result[Any]:
        """Execute the statement and return its row result."""
        return self.session.execute(self.statement)

    def all(self) -> Sequence[Row[Any]]:
        """Return all matching rows."""
        return self.execute().all()

    def first(self) -> Row[Any] | None:
        """Return the first matching row, or ``None``."""
        return self.session.execute(self.statement.limit(1)).first()

    def one(self) -> Row[Any]:
        """Return exactly one row or raise a SQLAlchemy result error."""
        return self.execute().one()

    def one_or_none(self) -> Row[Any] | None:
        """Return zero or one row or raise when multiple rows match."""
        return self.execute().one_or_none()

    def mappings(self) -> MappingResult:
        """Execute the statement and return mapping-style rows."""
        return self.execute().mappings()


class _ModelQueryProperty:
    """Descriptor that creates a fresh model query on every access."""

    def __get__(
        self,
        instance: object | None,
        owner: type[ModelT],
    ) -> ModelQuery[ModelT]:
        return ModelQuery(
            select(cast(Any, owner)),
            cast(Any, owner)._get_session_provider(),
        )
