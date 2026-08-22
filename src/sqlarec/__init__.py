"""A context-aware Active Record API for synchronous SQLAlchemy.

Applications remain responsible for creating and registering a session, and for
committing or rolling back transactions.
"""

from sqlarec.core import (
    ActiveRecordMixin,
    BaseModel,
    ModelQuery,
    ModelUpdate,
    RowQuery,
    RowUpdate,
    select_rows,
)
from sqlarec.database import new_session_from_engine

__all__ = [
    "ActiveRecordMixin",
    "BaseModel",
    "ModelQuery",
    "ModelUpdate",
    "RowQuery",
    "RowUpdate",
    "new_session_from_engine",
    "select_rows",
]

__version__ = "0.5.0"
