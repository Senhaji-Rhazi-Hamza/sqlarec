"""Identifier generation helpers."""

from uuid import uuid4


def generate_identifier() -> str:
    """Return a random UUID encoded as 32 lowercase hexadecimal characters."""
    return uuid4().hex
