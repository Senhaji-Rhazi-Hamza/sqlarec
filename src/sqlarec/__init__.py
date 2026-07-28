"""A context-aware Active Record API for synchronous SQLAlchemy.

Applications remain responsible for creating and registering a session, and for
committing or rolling back transactions.
"""

from sqlarec.core import (
    BaseModel,
    ModelQuery,
    ModelUpdate,
    RowQuery,
    RowUpdate,
)
from sqlarec.database import get_engine, init_engine, new_session

__all__ = [
    "BaseModel",
    "ModelQuery",
    "ModelUpdate",
    "RowQuery",
    "RowUpdate",
    "get_engine",
    "init_engine",
    "new_session",
]

__version__ = "0.2.0"
