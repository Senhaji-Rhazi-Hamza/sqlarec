# sqlarec

`sqlarec` adds context-aware synchronous and asynchronous Active Record APIs to
SQLAlchemy 2. Models can query and persist themselves without requiring every
service function to receive and forward a session.

```python
# Synchronous
user = User.query.where(User.email == email).one_or_none()

# Asynchronous
user = await AsyncUser.query.where(AsyncUser.email == email).one_or_none()
```

Your application still creates sessions and controls commits, rollbacks, and
cleanup. `sqlarec` does not depend on a web framework and never commits inside a
model method.

## Install

Install the published package from PyPI:

```bash
uv add sqlarec
```

For async use, also install the driver for your database:

```bash
uv add aiosqlite          # SQLite
uv add "psycopg[binary]"  # PostgreSQL
```

`sqlarec` requires Python 3.11 or later and SQLAlchemy 2. It supports
SQLAlchemy's synchronous `Session` and asynchronous `AsyncSession`.

## Use the synchronous API

Import the synchronous API from `sqlarec`:

```python
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from sqlarec import BaseModel, init_engine, new_session


class User(BaseModel):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True)


engine = init_engine("sqlite:///:memory:")
BaseModel.metadata.create_all(engine)

session = new_session()
BaseModel.register_session_provider(lambda: session)

user = User.create(name="Hamza", email="hamza@example.com")
session.commit()

print(User.query.one().email)
```

## Use the asynchronous API

Import the asynchronous API from `sqlarec.asyncio`. Async models use a separate
declarative base and metadata registry:

```python
import asyncio

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from sqlarec.asyncio import (
    AsyncBaseModel,
    init_async_engine,
    new_async_session,
)


class User(AsyncBaseModel):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True)


async def main() -> None:
    engine = init_async_engine("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as connection:
        await connection.run_sync(AsyncBaseModel.metadata.create_all)

    async with new_async_session() as session:
        AsyncBaseModel.register_session_provider(lambda: session)

        user = await User.create(name="Hamza", email="hamza@example.com")
        await session.commit()

        print((await User.query.one()).email)

    await engine.dispose()


asyncio.run(main())
```

Both quickstarts print:

```text
hamza@example.com
```

## Keep sessions at the application boundary

Register a zero-argument session provider during application setup. A command
runner, job worker, dependency scope, or middleware can then bind the current
session while models resolve it only when an operation executes.

For concurrent async applications, use a context-local provider and create one
`AsyncSession` per task:

```python
from contextvars import ContextVar

from sqlalchemy.ext.asyncio import AsyncSession

from sqlarec.asyncio import AsyncBaseModel, new_async_session

current_session = ContextVar[AsyncSession]("current_session")
AsyncBaseModel.register_session_provider(current_session.get)


async def database_middleware(request, handler):
    async with new_async_session() as session:
        token = current_session.set(session)
        try:
            response = await handler(request)
            await session.commit()
            return response
        except Exception:
            await session.rollback()
            raise
        finally:
            current_session.reset(token)
```

Code inside that boundary uses models without accepting a session:

```python
async def find_user(email: str) -> User | None:
    return await User.query.where(User.email == email).one_or_none()
```

The same principle applies to the synchronous API with `Session`.

## Query models and rows

Query-building methods are immutable and do not perform I/O. Result methods are
synchronous or awaitable according to the selected base:

| Operation     | Synchronous                         | Asynchronous                              |
| ------------- | ----------------------------------- | ----------------------------------------- |
| All models    | `User.query.all()`                | `await User.query.all()`                |
| One model     | `User.query.one_or_none()`        | `await User.query.one_or_none()`        |
| Selected rows | `User.select(User.id).all()`      | `await User.select(User.id).all()`      |
| Mappings      | `User.select(User.id).mappings()` | `await User.select(User.id).mappings()` |

Builders include `where()`, `filter_by()`, `order_by()`, `group_by()`,
`having()`, `join()`, `outerjoin()`, `limit()`, `offset()`, `distinct()`,
`options()`, `union()`, and `union_all()`.

## Write without hidden commits

Write helpers flush the current session but never commit:

| Operation          | Synchronous                             | Asynchronous                                  |
| ------------------ | --------------------------------------- | --------------------------------------------- |
| Create             | `User.create(...)`                    | `await User.create(...)`                    |
| Save               | `user.save()`                         | `await user.save()`                         |
| Delete             | `user.delete()`                       | `await user.delete()`                       |
| Primary-key lookup | `User.get_by_pk(42)`                  | `await User.get_by_pk(42)`                  |
| Update             | `User.update().values(...).execute()` | `await User.update().values(...).execute()` |

Keeping commits outside model methods lets the application commit or roll back a
complete unit of work atomically. Models also expose `User.session`, and every
query/update wrapper exposes its underlying `.statement` for direct SQLAlchemy
use.

Async models include SQLAlchemy's `AsyncAttrs`. Prefer eager relationship
loading, or use `await model.awaitable_attrs.relationship`, when attribute access
would otherwise require implicit database I/O.

## Develop the library

Clone the repository and install all development dependencies:

```bash
uv sync
```

| Command            | Purpose                                 |
| ------------------ | --------------------------------------- |
| `make test`      | Run synchronous and asynchronous tests. |
| `make lint`      | Check source and tests with Ruff.       |
| `make typecheck` | Check source and tests with Astral ty.  |
| `make format`    | Format source and tests with Ruff.      |
| `make clean`     | Remove Python, pytest, and Ruff caches. |

## Current limitations

- Sync and async models use separate declarative bases and metadata registries.
- Each concurrent task must use its own `AsyncSession`.
- Async database drivers are selected and installed by the application.
- Query wrappers cover common operations; use `.statement` and the resolved
  session for advanced SQLAlchemy features.
