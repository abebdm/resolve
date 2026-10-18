"""The base class for immutable value types (design.md §4, docs/decisions.md 2026-10-18).

Game state is mutable, but much of what it holds never changes once created: card data, card
definitions, events, decision requests, answer spaces. Those types derive from ``Immutable``,
which makes ``copy.copy`` and ``copy.deepcopy`` return the object itself. Cloning a state for AI
search then shares them instead of copying every card's Oracle text.

That sharing is only safe if the value is *deeply* immutable: a frozen dataclass whose fields hold
only scalars, enums, tuples and other ``Immutable`` values. ``tests/state/test_immutability.py``
checks every subclass for this. Pickling is unaffected.
"""

from __future__ import annotations

from typing import Self


class Immutable:
    """A deeply immutable value; copies of it are the value itself.

    Subclasses must be ``@dataclass(frozen=True)`` and hold only ``None``, ``bool``, ``int``,
    ``float``, ``str``, enums, tuples and other ``Immutable`` values.
    """

    __slots__ = ()

    def __copy__(self) -> Self:
        return self

    def __deepcopy__(self, memo: dict[int, object]) -> Self:
        return self
