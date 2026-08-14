# sqlarec

`sqlarec` adds a small Active Record API to SQLAlchemy 2 models:

```python
user = User.query.where(User.email == "hamza@example.com").one_or_none()
user = User.create(name="Hamza", email="hamza@example.com")
user.save()
```

Your application remains in control of engines, sessions, commits, rollbacks,
and cleanup. SQLARec resolves the current session and flushes writes, but never
commits implicitly.

You can use SQLARec in two ways:

- Start with `BaseModel` for a simple declarative setup.
- Combine `ActiveRecordMixin` with your own SQLAlchemy registry when you want
  complete control over mapping.

## Install

```bash
uv add sqlarec
```

For asynchronous use, also install a driver for your database:

```bash
uv add aiosqlite          # SQLite
uv add "psycopg[binary]"  # PostgreSQL
```

SQLARec requires Python 3.11 or later and SQLAlchemy 2.

## Quickstart with `BaseModel`

`BaseModel` is the easiest way to get started. It already combines SQLARec's
Active Record behavior with SQLAlchemy's `DeclarativeBase`.

```python
from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from sqlarec import BaseModel, init_engine, new_session


class User(BaseModel):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


# Set up the database.
engine = init_engine("sqlite:///:memory:")
BaseModel.metadata.create_all(engine)

# Register the session used by model operations.
session = new_session()
BaseModel.register_session_provider(lambda: session)

# Create and persist a user. create() adds and flushes; your app commits.
user = User.create(name="Hamza", email="hamza@example.com")
session.commit()

# Query models directly from the class.
user = User.query.where(User.email == "hamza@example.com").one()

# Change and persist an existing model.
user.name = "Hamza Senhaji"
user.save()
session.commit()

# Delete follows the same transaction rule.
user.delete()
session.commit()
```

Use this style unless your application already has its own mapping layer or you
specifically want to keep domain classes independent from table definitions.

## Choose a mapping style

Both styles provide the same query and persistence API. The difference is who
defines the SQLAlchemy mapping foundation.

| Style | Choose it when | Mapping ownership |
| --- | --- | --- |
| `BaseModel` | You want the shortest setup and standard declarative models. | SQLARec provides `DeclarativeBase`; your model declares columns. |
| `ActiveRecordMixin` + `registry` | You have domain classes, existing tables, or custom mapping requirements. | Your application creates the registry, tables, and mappings. |

The model API remains familiar in either case:

```python
Model.query.where(...).all()
Model.get_by_pk(...)
Model.create(...)

instance.save()
instance.delete()
```

## Use your own SQLAlchemy registry

`ActiveRecordMixin` supplies SQLARec behavior without inheriting from
`DeclarativeBase`. This means a class can contain domain behavior first and be
mapped separately afterward.

### 1. Define the domain class

```python
from sqlarec import ActiveRecordMixin


class BookingBehaviour:
    def display_reference(self) -> str:
        return f"Booking {self.reference}"


class Booking(BookingBehaviour, ActiveRecordMixin):
    pass
```

At this point, `Booking` does not choose a table or a declarative mapping
strategy.

### 2. Define and apply the mapping

Use SQLAlchemy's regular imperative mapping API:

```python
from sqlalchemy import Column, Integer, String, Table
from sqlalchemy.orm import registry


mapper_registry = registry()

booking_table = Table(
    "bookings",
    mapper_registry.metadata,
    Column("id", Integer, primary_key=True),
    Column("reference", String(100), nullable=False),
)

mapper_registry.map_imperatively(Booking, booking_table)
```

Your application can use any registry, metadata, tables, column properties, or
relationships supported by SQLAlchemy. SQLARec does not replace or wrap that
configuration.

### 3. Register a session and use the model

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


engine = create_engine("sqlite:///:memory:")
mapper_registry.metadata.create_all(engine)
session = Session(engine, expire_on_commit=False)

ActiveRecordMixin.register_session_provider(lambda: session)

booking = Booking.create(reference="SQLAREC-1")
session.commit()

found = Booking.query.where(Booking.reference == "SQLAREC-1").one()
print(found.display_reference())
```

This is still normal SQLAlchemy imperative mapping. The mixin only adds the
query and persistence conveniences.

## Manage sessions at the application boundary

Register a zero-argument provider that returns the session for the current
request, job, command, or task:

```python
BaseModel.register_session_provider(lambda: current_session)
```

For imperatively mapped models, register it on the mixin:

```python
ActiveRecordMixin.register_session_provider(lambda: current_session)
```

SQLARec deliberately does not:

- create a session for each operation;
- commit or roll back a transaction;
- decide when a transaction begins or ends;
- close application-owned sessions.

Query and update builders retain the provider rather than a particular session.
They resolve the current session only when the statement executes. This makes a
context-local provider suitable for request-scoped and task-scoped sessions.

For example, an async application can bind one session to each task:

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

Code inside that boundary can use models without receiving a session argument:

```python
async def find_user(email: str) -> User | None:
    return await User.query.where(User.email == email).one_or_none()
```

The same pattern works with synchronous `Session` objects.

## Query and persist models

The APIs below work with declarative and imperative models. Async methods have
the same shape but must be awaited.

### Query mapped models

`Model.query` starts a query that returns instances of that model:

```python
users = User.query.order_by(User.name).all()

active_users = (
    User.query.where(User.active.is_(True)).order_by(User.name).limit(20).all()
)

user = User.query.filter_by(email="hamza@example.com").one_or_none()
```

Result methods are:

- `all()` for every matching model;
- `first()` for the first model or `None`;
- `one()` for exactly one model;
- `one_or_none()` for zero or one model.

SQLAlchemy raises its normal result exceptions when `one()` or `one_or_none()`
receives an unexpected number of rows.

### Select individual values

Pass mapped attributes to `select()` when you need rows instead of model
instances:

```python
rows = User.select(User.id, User.email).order_by(User.id).all()
email_row = User.select(User.email).where(User.id == 42).one()
mappings = User.select(User.id, User.email).mappings().all()
```

Model and row queries support immutable builder methods including `where()`,
`filter_by()`, `order_by()`, `group_by()`, `having()`, `join()`, `outerjoin()`,
`limit()`, `offset()`, `distinct()`, `options()`, `union()`, and `union_all()`.
Each call returns a new query, so a base query can safely be reused:

```python
users = User.query.order_by(User.id)
active_users = users.filter_by(active=True)
```

### Find models with helper methods

```python
user = User.get_by_pk(42)
exists = User.exists(42)
users = User.all()

user = User.get_instance_by_keys(email="hamza@example.com")
users = User.filter_by_keys(active=True)
user = User.get_or_create(email="hamza@example.com", name="Hamza")
```

Models also provide primary-key inspection and serialization helpers such as
`get_id()`, `get_primary_key_name()`, `get_primary_key_names()`, and `to_dict()`.

### Create, save, and delete

```python
user = User.create(name="Hamza", email="hamza@example.com")

user.name = "Hamza Senhaji"
user.save()

user.delete()

session.commit()
```

`create()`, `save()`, and `delete()` flush immediately, which makes generated
identifiers and database errors available to the caller. They do not commit.
The final transaction can still be committed or rolled back as one unit.

### Execute bulk updates

```python
result = User.update().where(User.active.is_(False)).values(active=True).execute()

session.commit()
print(result.rowcount)
```

Use `returning()` when supported by the database:

```python
updated_users = (
    User.update()
    .where(User.active.is_(False))
    .values(active=True)
    .returning(User)
    .all()
)
```

Every query and update wrapper exposes `.statement` for SQLAlchemy features not
covered by SQLARec. Models expose the resolved session through `Model.session`.

## Use the asynchronous API

The async API mirrors the synchronous API and lives in `sqlarec.asyncio`:

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

        found = await User.query.where(User.id == user.id).one()
        found.name = "Hamza Senhaji"
        await found.save()
        await session.commit()

    await engine.dispose()


asyncio.run(main())
```

For custom imperative mappings, combine your domain class with
`AsyncActiveRecordMixin`, map it with `registry.map_imperatively()`, and register
an `AsyncSession` provider on the mixin. `AsyncActiveRecordMixin` also includes
SQLAlchemy's `AsyncAttrs`.

Prefer eager relationship loading in async code. When lazy loading is needed,
use SQLAlchemy's awaitable attributes:

```python
items = await booking.awaitable_attrs.items
```

## How the pieces fit together

```text
ActiveRecordMixin
    = SQLARec persistence and query capabilities

BaseModel
    = ActiveRecordMixin + SQLAlchemy DeclarativeBase

Imperatively mapped model
    = domain behavior + ActiveRecordMixin
      + application-owned SQLAlchemy mapping
```

The async equivalents are `AsyncActiveRecordMixin` and `AsyncBaseModel`.

`init_engine()` and `new_session()` are optional conveniences. Applications can
use their existing SQLAlchemy engine and session setup with either mapping
style.

## Develop the library

Install all development dependencies:

```bash
uv sync
```

| Command | Purpose |
| --- | --- |
| `make test` | Run synchronous and asynchronous tests. |
| `make lint` | Check source and tests with Ruff. |
| `make typecheck` | Check source and tests with Astral ty. |
| `make format` | Format source and tests with Ruff. |
| `make clean` | Remove Python, pytest, and Ruff caches. |

## Current limitations

- Sync and async models use separate declarative bases and metadata registries.
- Each concurrent task must use its own `AsyncSession`.
- Async database drivers are selected and installed by the application.
- Query wrappers cover common operations; use `.statement` and the resolved
  session for advanced SQLAlchemy features.
