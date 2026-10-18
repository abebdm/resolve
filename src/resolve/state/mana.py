"""Mana (106).

There are six types of mana (106.1b): white, blue, black, red, green and colorless. Mana in a
pool is kept as units, one ``Mana`` each, so restrictions and "when this mana is spent" effects
(106.6) can attach to a unit later. ``source`` is the object that produced it (106.3), when
known.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from resolve.state.ids import ObjectId
from resolve.values import Immutable


class ManaType(Enum):
    """The six types of mana (106.1b), by their symbols."""

    WHITE = "W"
    BLUE = "U"
    BLACK = "B"
    RED = "R"
    GREEN = "G"
    COLORLESS = "C"

    @property
    def symbol(self) -> str:
        """The mana symbol, such as ``"{G}"`` (107.4)."""
        return "{" + self.value + "}"


@dataclass(frozen=True)
class Mana(Immutable):
    """One unit of mana in a pool (106.4), and the object it came from (106.3)."""

    type: ManaType
    source: ObjectId | None = None


def describe_mana(mana: tuple[Mana, ...]) -> str:
    """The mana as symbols, such as ``"{G}{G}"``; ``"nothing"`` for none."""
    return "".join(unit.type.symbol for unit in mana) or "nothing"
