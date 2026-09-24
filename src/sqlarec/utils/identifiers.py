"""Identifier generation helpers."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import Column, Enum, String, Uuid

_HEX_IDENTIFIER_LENGTH = 32


def generate_identifier() -> str:
    """Return a random UUID encoded as 32 lowercase hexadecimal characters."""
    return uuid4().hex


def generate_identifier_for_column(column: Column[Any]) -> Any | None:
    """Return an identifier suited to ``column``, or ``None`` when unsuitable.

    A value is only produced for column types able to hold a generated
    identifier: UUID columns receive a :class:`uuid.UUID` object, or its hex
    form when the column is configured with ``as_uuid=False``, and string
    columns wide enough for 32 hexadecimal characters receive a hex identifier.
    Every other type, and any column carrying a foreign key, returns ``None`` so
    that SQLAlchemy or the database reports the missing value itself.
    """
    if column.foreign_keys:
        return None
    column_type = column.type
    if isinstance(column_type, Uuid):
        return uuid4() if column_type.as_uuid else generate_identifier()
    if isinstance(column_type, String) and not isinstance(column_type, Enum):
        length = column_type.length
        if length is None or length >= _HEX_IDENTIFIER_LENGTH:
            return generate_identifier()
    return None
