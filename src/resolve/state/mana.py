"""Mana (106).

There are six types of mana (106.1b): white, blue, black, red, green and colorless. Mana in a
pool is kept as units, one ``Mana`` each, so restrictions and "when this mana is spent" effects
(106.6) can attach to a unit. ``source`` is the object that produced it (106.3), when known;
``restriction`` limits what it can be spent on (106.6).

A payment says what it pays for (``ForSpell``, ``ForAbility``), so a restriction can tell whether
its mana may be spent on it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from resolve.state.ids import ObjectId
from resolve.values import Immutable

if TYPE_CHECKING:
    from resolve.state.game import GameState


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
class ManaRestriction(Immutable, ABC):
    """A restriction on how mana can be spent (106.6), such as Ixalli's Lorekeeper's "Spend this
    mana only to cast a Dinosaur spell or activate an ability of a Dinosaur source." The
    restrictions themselves are primitives (``resolve.cards.primitives.restrictions``)."""

    @abstractmethod
    def allows(self, state: GameState, purpose: PaymentPurpose) -> bool:
        """Whether mana with this restriction may be spent on ``purpose`` now (106.6)."""

    @property
    @abstractmethod
    def text(self) -> str:
        """The restriction as printed, such as ``"Spend this mana only to cast ..."``."""


@dataclass(frozen=True)
class Mana(Immutable):
    """One unit of mana in a pool (106.4), the object it came from (106.3), and what it may be spent
    on (``restriction``, 106.6; ``None``: anything). A restriction doesn't change its type (106.6).
    """

    type: ManaType
    source: ObjectId | None = None
    restriction: ManaRestriction | None = None


@dataclass(frozen=True)
class ForSpell(Immutable):
    """A payment for casting the spell ``spell`` (601.2h)."""

    spell: ObjectId


@dataclass(frozen=True)
class ForAbility(Immutable):
    """A payment for activating ability ``ability`` of ``source`` (602.2b, 601.2h)."""

    source: ObjectId
    ability: int


PaymentPurpose = ForSpell | ForAbility
"""What a payment pays for: a mana restriction (106.6) reads it."""


def describe_mana(mana: tuple[Mana, ...]) -> str:
    """The mana as symbols, such as ``"{G}{G}"``; ``"nothing"`` for none."""
    return "".join(unit.type.symbol for unit in mana) or "nothing"
