"""The base classes of primitives, kept free of engine imports so card definitions can name
them without import cycles."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from resolve.values import Immutable


@dataclass(frozen=True)
class Ability(Immutable, ABC):
    """An ability of an object (113)."""

    @property
    @abstractmethod
    def text(self) -> str:
        """The ability's rules text, such as ``"{T}: Add {G}."``."""
