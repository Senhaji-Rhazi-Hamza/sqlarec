"""Immutable query wrappers for SQLAlchemy ``AsyncSession``."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, Self, TypeVar, cast

from sqlalchemy import Select, select, union, union_all
from sqlalchemy.engine import MappingResult, Result, Row, ScalarResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from sqlarec.core.query import Query

ModelT = TypeVar("ModelT")


class AsyncModelQuery(Query[AsyncSession], Generic[ModelT]):
    """Execute a select statement asynchronously and return mapped models."""

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

    async def execute(self) -> ScalarResult[ModelT]:
        """Execute the statement and return its scalar result."""
        return await self.session.scalars(self.statement)

    async def all(self) -> Sequence[ModelT]:
        """Return all matching model instances."""
        return (await self.execute()).all()

    async def first(self) -> ModelT | None:
        """Return the first matching model, or ``None``."""
        result = await self.session.scalars(self.statement.limit(1))
        return result.first()

    async def one(self) -> ModelT:
        """Return exactly one model or raise a SQLAlchemy result error."""
        return (await self.execute()).one()

    async def one_or_none(self) -> ModelT | None:
        """Return zero or one model or raise when multiple rows match."""
        return (await self.execute()).one_or_none()

    async def exists(self) -> bool:
        """Return whether this query matches at least one model."""
        return bool(await self.session.scalar(select(self.statement.exists())))


class AsyncRowQuery(Query[AsyncSession]):
    """Execute a select statement asynchronously and return SQLAlchemy rows."""

    async def execute(self) -> Result[Any]:
        """Execute the statement and return its row result."""
        return await self.session.execute(self.statement)

    async def all(self) -> Sequence[Row[Any]]:
        """Return all matching rows."""
        return (await self.execute()).all()

    async def first(self) -> Row[Any] | None:
        """Return the first matching row, or ``None``."""
        result = await self.session.execute(self.statement.limit(1))
        return result.first()

    async def one(self) -> Row[Any]:
        """Return exactly one row or raise a SQLAlchemy result error."""
        return (await self.execute()).one()

    async def one_or_none(self) -> Row[Any] | None:
        """Return zero or one row or raise when multiple rows match."""
        return (await self.execute()).one_or_none()

    async def exists(self) -> bool:
        """Return whether this query matches at least one row."""
        return bool(await self.session.scalar(select(self.statement.exists())))

    async def mappings(self) -> MappingResult:
        """Execute the statement and return mapping-style rows."""
        return (await self.execute()).mappings()


def select_rows(*entities: Any) -> AsyncRowQuery:
    """Create an unbound async row query from entities and expressions."""
    return AsyncRowQuery(select(*entities))


class _AsyncModelQueryProperty:
    """Descriptor that creates a fresh async model query on every access."""

    def __get__(
        self,
        instance: object | None,
        owner: type[ModelT],
    ) -> AsyncModelQuery[ModelT]:
        return AsyncModelQuery(
            select(cast(Any, owner)),
            cast(Any, owner)._get_session_provider(),
        )
