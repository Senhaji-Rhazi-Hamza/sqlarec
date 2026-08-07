"""Immutable update wrappers for SQLAlchemy ``AsyncSession``."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, TypeVar, cast, overload

from sqlalchemy import inspect
from sqlalchemy.engine import CursorResult, MappingResult, Result, Row, ScalarResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapper

from sqlarec.core.update import UpdateBuilder

ModelT = TypeVar("ModelT")


class AsyncUpdate(UpdateBuilder[AsyncSession]):
    """Execute an async update or choose a typed returning wrapper."""

    @overload
    def returning(
        self,
        entity: type[ModelT],
        /,
        **kwargs: Any,
    ) -> AsyncModelUpdate[ModelT]: ...

    @overload
    def returning(
        self,
        column: Any,
        /,
        *columns: Any,
        **kwargs: Any,
    ) -> AsyncRowUpdate: ...

    def returning(
        self,
        entity_or_column: Any,
        /,
        *columns: Any,
        **kwargs: Any,
    ) -> AsyncModelUpdate[Any] | AsyncRowUpdate:
        """Return an entity or row update based on the returning expression."""
        expressions = (entity_or_column, *columns)
        statement = self.statement.returning(*expressions, **kwargs)
        if len(expressions) == 1 and isinstance(
            inspect(entity_or_column, raiseerr=False),
            Mapper,
        ):
            return AsyncModelUpdate(statement, self._session_provider)
        return AsyncRowUpdate(statement, self._session_provider)

    async def execute(self) -> CursorResult[Any]:
        """Execute the update and return its result."""
        return cast(CursorResult[Any], await self.session.execute(self.statement))


class AsyncModelUpdate(UpdateBuilder[AsyncSession], Generic[ModelT]):
    """Execute an async update that returns mapped model instances."""

    async def execute(self) -> ScalarResult[ModelT]:
        """Execute the update and return its scalar result."""
        return await self.session.scalars(self.statement)

    async def all(self) -> Sequence[ModelT]:
        """Return all updated model instances."""
        return (await self.execute()).all()

    async def first(self) -> ModelT | None:
        """Return the first updated model, or ``None``."""
        return (await self.execute()).first()

    async def one(self) -> ModelT:
        """Return exactly one updated model."""
        return (await self.execute()).one()

    async def one_or_none(self) -> ModelT | None:
        """Return zero or one updated model."""
        return (await self.execute()).one_or_none()


class AsyncRowUpdate(UpdateBuilder[AsyncSession]):
    """Execute an async update that returns SQLAlchemy rows."""

    async def execute(self) -> Result[Any]:
        """Execute the update and return its row result."""
        return await self.session.execute(self.statement)

    async def all(self) -> Sequence[Row[Any]]:
        """Return all rows produced by the update."""
        return (await self.execute()).all()

    async def first(self) -> Row[Any] | None:
        """Return the first produced row, or ``None``."""
        return (await self.execute()).first()

    async def one(self) -> Row[Any]:
        """Return exactly one produced row."""
        return (await self.execute()).one()

    async def one_or_none(self) -> Row[Any] | None:
        """Return zero or one produced row."""
        return (await self.execute()).one_or_none()

    async def mappings(self) -> MappingResult:
        """Execute the update and return mapping-style rows."""
        return (await self.execute()).mappings()
