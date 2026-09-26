"""A context-aware Active Record API for synchronous SQLAlchemy.

Applications remain responsible for creating and registering a session, and for
committing or rolling back transactions.
"""

from sqlarec.core import (
    ActiveRecordMixin,
    BaseModel,
    Insert,
    ModelInsert,
    ModelQuery,
    ModelUpdate,
    RowInsert,
    RowQuery,
    RowUpdate,
    select_rows,
)
from sqlarec.database import new_session_from_engine

__all__ = [
    "ActiveRecordMixin",
    "BaseModel",
    "Insert",
    "ModelInsert",
    "ModelQuery",
    "ModelUpdate",
    "RowInsert",
    "RowQuery",
    "RowUpdate",
    "new_session_from_engine",
    "select_rows",
]

__version__ = "0.7.0"
