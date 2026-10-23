"""Values: numbers in a definition's text, as expressions (design.md §17.9).

A value is evaluated only through ``resolve.effects.evaluation.evaluate``, whose context says
when: on announcement (601.2b, 113.7a) or on resolution, once per effect as it applies (608.2h).

- ``Fixed(n)``: a number printed in the text.
- ``PowerOf(ref)``: the power of an object (208.1), as it last existed if it has left its zone
  (608.2h); nothing if the object is an illegal target (608.2b).

X (107.3, M2.7), counts and "the greatest power among" (M2.10) and arithmetic join them with
their cards. 107.1b: an effect that uses a negative result as an amount uses 0 instead; the
effects apply that (``DealDamage``, ``GainLife``, ``DrawCards``).
"""

from __future__ import annotations

from dataclasses import dataclass

from resolve.cards.primitives.refs import ObjectRef, Phrasing
from resolve.values import Immutable

_NUMBER_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")


@dataclass(frozen=True)
class Fixed(Immutable):
    """A number printed in the text, such as Test Shock's 2."""

    value: int

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValueError("a printed number can't be negative (107.1b)")

    @property
    def word(self) -> str:
        """The number in words, as card text writes small counts ("two")."""
        return _NUMBER_WORDS[self.value] if self.value < len(_NUMBER_WORDS) else str(self.value)


@dataclass(frozen=True)
class PowerOf(Immutable):
    """The power of the object ``object`` refers to (208.1, 608.2h)."""

    object: ObjectRef

    def describe(self, phrasing: Phrasing) -> str:
        """``"its power"``, ``"target creature's power"``."""
        return f"{phrasing.possessive(self.object)} power"


Value = Fixed | PowerOf
"""A number in a definition."""
