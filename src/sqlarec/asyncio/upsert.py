"""Immutable upsert wrappers for SQLAlchemy ``AsyncSession``."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, TypeVar, overload

from sqlalchemy import inspect
from sqlalchemy.engine import MappingResult, Result, Row, ScalarResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapper

from sqlarec.core.upsert import UpsertBuilder

ModelT = TypeVar("ModelT")


class AsyncUpsert(UpsertBuilder[AsyncSession]):
    """Execute an async upsert or select a typed returning wrapper."""

    @overload
    def returning(
        self,
        entity: type[ModelT],
        /,
        **kwargs: Any,
    ) -> AsyncModelUpsert[ModelT]: ...

    @overload
    def returning(
        self,
        column: Any,
        /,
        *columns: Any,
        **kwargs: Any,
    ) -> AsyncRowUpsert: ...

    def returning(
        self,
        entity_or_column: Any,
        /,
        *columns: Any,
        **kwargs: Any,
    ) -> AsyncModelUpsert[Any] | AsyncRowUpsert:
        """Return an entity or row upsert for the returning expressions."""
        expressions = (entity_or_column, *columns)
        wrapper: type[AsyncModelUpsert[Any]] | type[AsyncRowUpsert]
        if len(expressions) == 1 and isinstance(
            inspect(entity_or_column, raiseerr=False),
            Mapper,
        ):
            wrapper = AsyncModelUpsert
        else:
            wrapper = AsyncRowUpsert
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

    async def execute(self) -> Result[Any]:
        """Execute the upsert without committing the transaction."""
        return await self.session.execute(self.statement)


class AsyncModelUpsert(UpsertBuilder[AsyncSession], Generic[ModelT]):
    """Execute an async upsert that returns mapped model instances."""

    async def execute(self) -> ScalarResult[ModelT]:
        """Execute the upsert and refresh identities already in the session."""
        return await self.session.scalars(
            self.statement,
            execution_options={"populate_existing": True},
        )

    async def all(self) -> Sequence[ModelT]:
        """Return all models produced by the upsert."""
        return (await self.execute()).all()

    async def first(self) -> ModelT | None:
        """Return the first produced model, or ``None``."""
        return (await self.execute()).first()

    async def one(self) -> ModelT:
        """Return exactly one produced model."""
        return (await self.execute()).one()

    async def one_or_none(self) -> ModelT | None:
        """Return zero or one produced model."""
        return (await self.execute()).one_or_none()


class AsyncRowUpsert(UpsertBuilder[AsyncSession]):
    """Execute an async upsert that returns SQLAlchemy rows."""

    async def execute(self) -> Result[Any]:
        """Execute the upsert and return its row result."""
        return await self.session.execute(self.statement)

    async def all(self) -> Sequence[Row[Any]]:
        """Return all rows produced by the upsert."""
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
        """Execute the upsert and return mapping-style rows."""
        return (await self.execute()).mappings()
