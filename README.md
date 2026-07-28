# sqlarec

`sqlarec` adds a context-aware Active Record API to synchronous SQLAlchemy 2.
It gives models concise query and persistence methods without requiring every
service function to receive and forward a `Session`.

```python
user = User.query.where(User.email == "hamza@example.com").one_or_none()
users = User.query.order_by(User.name).all()
user = User.create(name="Hamza", email="hamza@example.com")
```

Your application still creates the session and controls commits, rollbacks, and
cleanup. `sqlarec` does not depend on a web framework and never commits inside a
model method.

## Install

Install the published package from PyPI:

```bash
uv add sqlarec
```

You can also install it with pip:

```bash
python -m pip install sqlarec
```

`sqlarec` requires Python 3.11 or later, SQLAlchemy 2, and a synchronous
SQLAlchemy `Session`.

## Quickstart

Define models with standard SQLAlchemy mapped columns:

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


engine = init_engine("sqlite:///:memory:")
BaseModel.metadata.create_all(engine)

session = new_session()
BaseModel.register_session_provider(lambda: session)

User.create(name="Hamza", email="hamza@example.com")
session.commit()

user = User.query.one()
print(user.email)
```

Expected output:

```text
hamza@example.com
```

`BaseModel` inherits from SQLAlchemy's `DeclarativeBase`, so relationships,
constraints, indexes, and mapper configuration continue to use normal SQLAlchemy
APIs.

## Keep session handling at the application boundary

Regular SQLAlchemy often requires passing a session through each application
layer:

```python
from sqlalchemy import select
from sqlalchemy.orm import Session


def find_user(session: Session, email: str) -> User | None:
    return session.scalars(select(User).where(User.email == email)).one_or_none()
```

With `sqlarec`, your application registers a zero-argument provider once. Models
resolve the current session when an operation executes:

```python
from contextvars import ContextVar

from sqlalchemy.orm import Session

from sqlarec import BaseModel

current_session = ContextVar[Session]("current_session")
BaseModel.register_session_provider(current_session.get)


def find_user(email: str) -> User | None:
    return User.query.where(User.email == email).one_or_none()
```

The provider can read from application state, a dependency scope, or a
`ContextVar`. This allows middleware to bind one session to the current request:

```python
from sqlarec import new_session


def database_middleware(request, handler):
    session = new_session()
    token = current_session.set(session)
    try:
        response = handler(request)
        session.commit()
        return response
    except Exception:
        session.rollback()
        raise
    finally:
        current_session.reset(token)
        session.close()
```

Handlers and services inside that middleware can use `User.query`,
`User.create()`, or `User.session` without receiving a session argument.
Transaction ownership remains explicit at the middleware boundary.

## Query models and rows

`Model.query` and `Model.select()` return immutable `ModelQuery` wrappers:

```python
users = User.query.all()
user = User.query.where(User.email == "hamza@example.com").one_or_none()
active = User.query.filter_by(active=True).order_by(User.name).limit(20).all()
```

Pass individual columns to `Model.select()` to receive SQLAlchemy rows:

```python
rows = User.select(User.id, User.email).order_by(User.id).all()
mappings = User.select(User.id, User.email).mappings().all()
```

```text
User.query.all()                       -> Sequence[User]
User.select().all()                    -> Sequence[User]
User.select(User.id, User.email).all() -> Sequence[Row]
```

Query builders include `where()`, `filter_by()`, `order_by()`, `group_by()`,
`having()`, `join()`, `outerjoin()`, `limit()`, `offset()`, `distinct()`,
`options()`, `union()`, and `union_all()`.

## Write without hidden commits

Create, update, and delete operations flush the current session but do not
commit:

```python
user = User.create(name="Hamza", email="hamza@example.com")

user.name = "Hamza S."
user.save()

User.update().where(User.active.is_(False)).values(active=True).execute()

user.delete()
session.commit()
```

Keeping commits outside model methods lets your application commit or roll back
the complete unit of work atomically.

Single primary keys support direct lookup:

```python
user = User.get_by_pk(42)
exists = User.exists(42)
```

String primary keys without a Python or database default receive a generated
UUID hex value. Composite primary-key lookup accepts a tuple in mapper-defined
key order.

## Use SQLAlchemy directly when needed

Wrappers expose their underlying SQLAlchemy statement:

```python
query = User.query.where(User.active.is_(True))
statement = query.statement
```

The resolved session is also available on the model:

```python
result = User.session.execute(custom_statement)
```

`sqlarec` is an ergonomic layer, not a replacement for SQLAlchemy.

## Develop the library

Clone the repository, then install the package and development tools:

```bash
uv sync
```

| Command | Purpose |
| --- | --- |
| `make install` | Install runtime and development dependencies. |
| `make install-prod` | Install runtime dependencies only. |
| `make test` | Run pytest. |
| `make lint` | Check source and tests with Ruff. |
| `make typecheck` | Check package types with mypy. |
| `make format` | Format source and tests with Ruff. |
| `make clean` | Remove Python, pytest, and Ruff caches. |

## Current limitations

- You must register a session provider before model operations.
- Only synchronous SQLAlchemy sessions are supported.
- Query wrappers cover common operations; use the underlying statement for
  advanced SQLAlchemy features.
