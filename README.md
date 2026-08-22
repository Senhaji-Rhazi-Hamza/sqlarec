# sqlarec

`sqlarec` adds convenient query and persistence methods to SQLAlchemy 2 models:

```python
user = User.query.where(User.email == "hamza@example.com").one_or_none()
user = User.create(name="Hamza", email="hamza@example.com")
```

Your application still owns the engine, session lifecycle, and transaction
boundaries. SQLARec flushes writes but never commits implicitly.

## Install

```bash
uv add sqlarec
```

SQLARec requires Python 3.11 or later and SQLAlchemy 2.

For asynchronous use, also install a driver for your database:

```bash
uv add aiosqlite          # SQLite
uv add "psycopg[binary]"  # PostgreSQL
```

## Synchronous quickstart

This section contains everything needed for the common synchronous use case.

### Define a model

Inherit from `BaseModel` and define a regular SQLAlchemy declarative model:

```python
from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from sqlarec import BaseModel


class User(BaseModel):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
```

### Configure the database

Create an engine and register the session that model operations should use:

```python
from sqlalchemy import create_engine

from sqlarec import new_session_from_engine


engine = create_engine("sqlite:///:memory:")
BaseModel.metadata.create_all(engine)

session = new_session_from_engine(engine)
BaseModel.register_session_provider(lambda: session)
```

The application creates and owns the engine. `new_session_from_engine()` is an
optional convenience around SQLAlchemy's `sessionmaker`; you can register a
`Session` created by your existing setup instead.

By default, the helper creates sessions with `autoflush=False` and
`expire_on_commit=False`. Override those defaults or pass other `sessionmaker`
options when needed:

```python
session = new_session_from_engine(
    engine,
    autoflush=True,
    expire_on_commit=True,
    info={"service": "accounts"},
)
```

### Create

```python
user = User.create(name="Hamza", email="hamza@example.com")
session.commit()
```

`create()` constructs the model, adds it to the current session, and flushes.
The application decides when to commit.

### Read

Query using mapped attributes:

```python
user = User.query.where(User.email == "hamza@example.com").one()
users = User.query.filter_by(active=True).order_by(User.name).all()
```

Or look up a primary key directly:

```python
same_user = User.get_by_pk(user.id)
```

### Update

Change attributes and call `save()`:

```python
user.name = "Hamza Senhaji"
user.save()
session.commit()
```

For updates that do not require loading each model:

```python
User.update().where(User.id == user.id).values(active=False).execute()
session.commit()
```

### Delete

```python
user.delete()
session.commit()
```

`create()`, `save()`, and `delete()` flush immediately but do not commit. This
allows several operations to remain part of one application-controlled
transaction:

```python
try:
    first = User.create(name="Hamza", email="hamza@example.com")
    second = User.create(name="Reader", email="reader@example.com")
    session.commit()
except Exception:
    session.rollback()
    raise
```

## Asynchronous API

The async API mirrors the synchronous API. Import it from `sqlarec.asyncio` and
await operations that perform database I/O.

### Define an async model

```python
from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from sqlarec.asyncio import AsyncBaseModel


class User(AsyncBaseModel):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
```

### Configure the async database

```python
from sqlalchemy.ext.asyncio import create_async_engine

from sqlarec.asyncio import new_async_session_from_engine


engine = create_async_engine("sqlite+aiosqlite:///:memory:")

async with engine.begin() as connection:
    await connection.run_sync(AsyncBaseModel.metadata.create_all)
```

Open and register a session at the application boundary so it is always closed.
The CRUD examples in the next section run inside this block:

```python
async with new_async_session_from_engine(engine) as session:
    AsyncBaseModel.register_session_provider(lambda: session)
    # Use models here.
```

`new_async_session_from_engine()` accepts the same `autoflush`,
`expire_on_commit`, and additional sessionmaker options as the synchronous
helper.

### Create, read, update, and delete

The operations are the same as the synchronous API, with `await` where I/O
occurs:

```python
# Create
user = await User.create(name="Hamza", email="hamza@example.com")
await session.commit()

# Read
user = await User.query.where(User.email == "hamza@example.com").one()
users = await User.query.filter_by(active=True).all()
same_user = await User.get_by_pk(user.id)

# Update
user.name = "Hamza Senhaji"
await user.save()
await session.commit()

# Delete
await user.delete()
await session.commit()
```

Bulk updates are awaitable too:

```python
result = await User.update().where(User.active.is_(False)).values(active=True).execute()
await session.commit()
```

Async models include SQLAlchemy's `AsyncAttrs`. Prefer eager relationship
loading, or use awaitable attributes when lazy loading is required:

```python
items = await booking.awaitable_attrs.items
```

## Advanced: use your own SQLAlchemy mapping

The quickstarts use the simplest mapping style: `BaseModel` provides
SQLAlchemy's `DeclarativeBase`. Most applications can stop there.

SQLARec also supports classes mapped by an application-owned SQLAlchemy
registry. Choose this advanced style when you already have domain classes,
existing tables, or custom mapping requirements.

| Mapping style       | Model foundation      | Who owns the mapping?                                                            |
| ------------------- | --------------------- | -------------------------------------------------------------------------------- |
| Default declarative | `BaseModel`         | SQLARec provides the declarative base; the model declares its table and columns. |
| Custom imperative   | `ActiveRecordMixin` | Your application provides the registry, table, and mapping.                      |

Both styles provide the same query and persistence methods after the class has
been mapped.

### Define domain behavior

`ActiveRecordMixin` adds SQLARec behavior without inheriting from
`DeclarativeBase`:

```python
from sqlarec import ActiveRecordMixin


class BookingBehaviour:
    id: int
    reference: str

    def display_reference(self) -> str:
        return f"Booking {self.reference}"


class Booking(BookingBehaviour, ActiveRecordMixin):
    pass
```

The annotations describe the fields used by the domain behavior. The class has
not selected a table or mapping strategy yet.

### Map the class with a registry

Use SQLAlchemy's normal imperative mapping API:

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

The `id` and `reference` columns become mapped attributes with the same names.
Use SQLAlchemy's imperative `properties` configuration when attribute and
column names differ.

### Register a session and use the model

```python
from sqlalchemy import create_engine

from sqlarec import new_session_from_engine

engine = create_engine("sqlite:///:memory:")
mapper_registry.metadata.create_all(engine)
session = new_session_from_engine(engine)

ActiveRecordMixin.register_session_provider(lambda: session)

booking = Booking.create(reference="SQLAREC-1")
session.commit()

found = Booking.query.where(Booking.reference == "SQLAREC-1").one()
print(found.display_reference())
```

SQLARec does not replace or wrap the registry. Your application can use any
tables, relationships, column properties, or mapping configuration supported by
SQLAlchemy.

For asynchronous imperative mapping, compose the domain class with
`AsyncActiveRecordMixin`, map it with `registry.map_imperatively()`, and
register an `AsyncSession` provider on the mixin.

## Query and persistence reference

These APIs work with declarative and imperatively mapped models.

### Query models

`Model.query` returns mapped model instances:

```python
users = User.query.order_by(User.name).all()
user = User.query.filter_by(email="hamza@example.com").one_or_none()
has_active_users = User.query.where(User.active.is_(True)).exists()
```

Result methods are:

- `all()` for every matching model;
- `first()` for the first model or `None`;
- `one()` for exactly one model;
- `one_or_none()` for zero or one model;
- `exists()` for whether at least one model matches.

SQLAlchemy raises its normal result exceptions when the number of rows does not
match the selected result method.

Query builders are immutable. Each method returns a new query, so a base query
can be reused safely:

```python
example_users = User.query.where(User.email.endswith("@example.com"))

first_page = example_users.order_by(User.name).limit(20)
second_page = example_users.order_by(User.name).offset(20).limit(20)

first_page_users = first_page.all()
second_page_users = second_page.all()
```

The calls do not modify `example_users`, so it can be reused to create more
specialized queries.

Builder methods also work with selected rows. For example, group users and
filter the groups with `having()`:

```python
from sqlalchemy import func


active_summary = (
    User.select(User.active, func.count(User.id).label("total"))
    .group_by(User.active)
    .having(func.count(User.id) > 0)
    .order_by(User.active)
    .all()
)
```

Available builders include `where()`, `filter_by()`, `order_by()`,
`group_by()`, `having()`, `join()`, `outerjoin()`, `limit()`, `offset()`,
`distinct()`, `options()`, `union()`, and `union_all()`.

`exists()` also works with selected rows and uses the complete builder chain:

```python
has_active_emails = User.select(User.email).where(User.active.is_(True)).exists()
```

In async code, await the result:

```python
has_active_users = await AsyncUser.query.where(AsyncUser.active.is_(True)).exists()
```

### Select rows without a model context

Use `select_rows()` when a selection does not naturally belong to one model.
Standalone selections are not connected to a registered provider, so bind the
session explicitly before execution:

```python
from sqlalchemy import func
from sqlarec import select_rows


active_summary = (
    select_rows(User.active, func.count(User.id).label("total"))
    .where(User.email.endswith("@example.com"))
    .group_by(User.active)
    .with_session(session)
    .all()
)

database_time = (
    select_rows(func.current_timestamp().label("database_time"))
    .with_session(session)
    .one()
)
```

The query remains immutable and exposes the same builder methods and
`statement` property as `Model.select()`. It can be constructed, extended, or
compiled before a session is bound. Executing it without `with_session()`
raises a `RuntimeError`.

Import the async factory from `sqlarec.asyncio` and await its result methods:

```python
from sqlarec.asyncio import select_rows


rows = await select_rows(User.id, User.email).with_session(async_session).all()
```

### Override the session for one builder

Queries and updates normally resolve the session from the model's registered
provider. Use `with_session()` when one builder chain must run through a
specific session:

```python
reporting_query = (
    User.query.with_session(reporting_session)
    .where(User.active.is_(True))
    .order_by(User.name)
)
users = reporting_query.all()

admin_update = User.update().with_session(admin_session)
admin_update.where(User.id == 42).values(active=False).execute()
admin_session.commit()
```

`with_session()` returns a new builder. It does not mutate the original builder
or replace the model's registered provider. Builder methods called afterward
continue using the explicit session.

Use `create_with_session()` when a new model must use an explicit session:

```python
user = User.create_with_session(
    admin_session,
    name="Hamza",
    email="hamza@example.com",
)
```

Models created or loaded through an explicit session remain attached to it.
Their `save()` and `delete()` methods use that attached session instead of the
registered provider. Transient or detached models fall back to the provider.

The same method works with async builders:

```python
user = await AsyncUser.create_with_session(
    async_session,
    name="Hamza",
    email="hamza@example.com",
)

active_users = AsyncUser.query.with_session(async_session).where(
    AsyncUser.active.is_(True)
)
users = await active_users.all()
```

### Select rows and mappings

Pass mapped attributes to `select()` when you need rows rather than model
instances:

```python
rows = User.select(User.id, User.email).order_by(User.id).all()
email_row = User.select(User.email).where(User.id == 42).one()
mappings = User.select(User.id, User.email).mappings().all()
```

### Use model helpers

```python
user = User.get_by_pk(42)
exists = User.exists(42)
users = User.all()

user = User.get_instance_by_keys(email="hamza@example.com")
users = User.filter_by_keys(active=True)
user = User.get_or_create(email="hamza@example.com", name="Hamza")
```

Models also provide primary-key and serialization helpers:

- `get_id()`
- `get_primary_key_name()`
- `get_primary_key_names()`
- `has_one_primary_key()`
- `to_dict()`

### Return values from updates

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

### Use the underlying SQLAlchemy statement

Every query and update wrapper exposes `.statement`. Use it when SQLAlchemy
supports an operation that the SQLARec wrapper does not expose directly.

For example, add `with_for_update()` to a model query and execute the resulting
SQLAlchemy statement with the registered session:

```python
query = User.query.where(User.email == "hamza@example.com")
statement = query.statement.with_for_update()

user = User.session.scalars(statement).one_or_none()
```

The statement can also be compiled for inspection or logging:

```python
compiled = query.statement.compile(
    engine,
    compile_kwargs={"literal_binds": True},
)
print(compiled)
```

With an async model, execute the statement through its `AsyncSession`:

```python
statement = User.query.where(User.active.is_(True)).statement
result = await User.session.scalars(statement)
users = result.all()
```

Models expose the session resolved from the registered provider through
`Model.session`.

For async models, await query results, lookup helpers, write methods, and update
execution.

## Manage sessions in concurrent applications

Register a zero-argument provider that returns the session for the current
request, command, job, or task. Query and update builders retain this provider
and resolve the current session only when a statement executes.

For an async application, a `ContextVar` can bind one session to each task:

```python
from contextvars import ContextVar

from sqlalchemy.ext.asyncio import AsyncSession

from sqlarec.asyncio import AsyncBaseModel, new_async_session_from_engine


current_session = ContextVar[AsyncSession]("current_session")
AsyncBaseModel.register_session_provider(current_session.get)


async def database_middleware(request, handler):
    async with new_async_session_from_engine(engine) as session:
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

SQLARec deliberately does not:

- create a session for each operation;
- commit or roll back transactions;
- decide when transactions begin or end;
- close application-owned sessions.

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

## Develop the library

Install all development dependencies:

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
