"""Reusable class-level descriptors."""

from collections.abc import Callable
from typing import Any, Generic, TypeVar

ValueT = TypeVar("ValueT")


class _ClassProperty(Generic[ValueT]):
    """Read-only descriptor for a value computed from a class."""

    def __init__(self, getter: Callable[[Any], ValueT]) -> None:
        self.getter = getter

    def __get__(
        self,
        instance: object | None,
        owner: type[Any],
    ) -> ValueT:
        return self.getter(owner)
