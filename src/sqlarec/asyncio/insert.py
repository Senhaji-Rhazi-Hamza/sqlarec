"""Immutable bulk insert wrappers for SQLAlchemy ``AsyncSession``."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, TypeVar, overload

from sqlalchemy import inspect
from sqlalchemy.engine import MappingResult, Result, Row, ScalarResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapper

from sqlarec.core.insert import InsertBuilder

ModelT = TypeVar("ModelT")


class AsyncInsert(InsertBuilder[AsyncSession]):
    """Execute an async bulk insert or select a returning wrapper."""

    @overload
    def returning(
        self,
        entity: type[ModelT],
        /,
        **kwargs: Any,
    ) -> AsyncModelInsert[ModelT]: ...

    @overload
    def returning(
        self,
        column: Any,
        /,
        *columns: Any,
        **kwargs: Any,
    ) -> AsyncRowInsert: ...

    def returning(
        self,
        entity_or_column: Any,
        /,
        *columns: Any,
        **kwargs: Any,
    ) -> AsyncModelInsert[Any] | AsyncRowInsert:
        """Return an entity or row insert for the returning expressions."""
        expressions = (entity_or_column, *columns)
        statement = self.statement.returning(*expressions, **kwargs)
        wrapper: type[AsyncModelInsert[Any]] | type[AsyncRowInsert]
        if len(expressions) == 1 and isinstance(
            inspect(entity_or_column, raiseerr=False),
            Mapper,
        ):
            wrapper = AsyncModelInsert
        else:
            wrapper = AsyncRowInsert
        return wrapper(
            statement,
            self._session_provider,
            self._prepare_values,
            self._parameters,
        )

    async def execute(self) -> Result[Any]:
        """Execute the ORM bulk insert without committing the transaction."""
        return await self.session.execute(
            self.statement,
            self._require_parameters(),
        )


class AsyncModelInsert(InsertBuilder[AsyncSession], Generic[ModelT]):
    """Execute an async bulk insert that returns mapped model instances."""

    async def execute(self) -> ScalarResult[ModelT]:
        """Execute the insert and return its scalar result."""
        return await self.session.scalars(
            self.statement,
            self._require_parameters(),
        )

    async def all(self) -> Sequence[ModelT]:
        """Return all inserted models produced by ``RETURNING``."""
        return (await self.execute()).all()

    async def first(self) -> ModelT | None:
        """Return the first inserted model, or ``None``."""
        return (await self.execute()).first()

    async def one(self) -> ModelT:
        """Return exactly one inserted model."""
        return (await self.execute()).one()

    async def one_or_none(self) -> ModelT | None:
        """Return zero or one inserted model."""
        return (await self.execute()).one_or_none()


class AsyncRowInsert(InsertBuilder[AsyncSession]):
    """Execute an async bulk insert that returns SQLAlchemy rows."""

    async def execute(self) -> Result[Any]:
        """Execute the insert and return its row result."""
        return await self.session.execute(
            self.statement,
            self._require_parameters(),
        )

    async def all(self) -> Sequence[Row[Any]]:
        """Return all rows produced by ``RETURNING``."""
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
        """Execute the insert and return mapping-style rows."""
        return (await self.execute()).mappings()
