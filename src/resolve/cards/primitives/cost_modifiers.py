"""Cost modifiers (601.2f, 118.7, design.md §17.6): what changes the total cost of a spell.

A ``CostModifier`` is data that changes a total cost's mana part (``apply``). Its ``step`` says
where 601.2f applies it: increases (with additional costs) first, then reductions, then effects
that directly affect the total, after which the total is locked in.

- ``ReduceGeneric``: "costs {N} less", by generic mana only (118.7a).

Static abilities that modify the costs of spells are ``SpellCostModifier`` abilities: for a
spell being cast, ``modifier`` says what, if anything, the ability does to its cost. They
function only where 113.6 says they do; ``resolve.rules.costs`` gathers them.

- ``SpellCostReduction``: "[Quality] spells you cast cost {N} less to cast." (Emerald
  Medallion, Kinjalli's Caller).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from resolve.cards.keywords.qualities import Quality
from resolve.cards.primitives.base import Ability
from resolve.data.mana_cost import ManaCost
from resolve.errors import NotImplementedRule
from resolve.values import Immutable

if TYPE_CHECKING:
    from resolve.state.game import GameState
    from resolve.state.ids import ObjectId, PlayerId


class ModifierStep(Enum):
    """Where 601.2f applies a cost modifier, in its order."""

    INCREASE = 1
    """Additional costs and cost increases: added to the mana cost or alternative cost."""
    REDUCTION = 2
    """Cost reductions: subtracted after every increase (601.2f)."""
    TOTAL = 3
    """Effects that directly affect the total cost, once it is determined (601.2f)."""


@dataclass(frozen=True)
class CostModifier(Immutable, ABC):
    """A change to the mana part of a total cost (601.2f)."""

    @property
    @abstractmethod
    def step(self) -> ModifierStep:
        """Where 601.2f applies it."""

    @abstractmethod
    def apply(self, cost: ManaCost) -> ManaCost:
        """``cost`` changed by this modifier."""


@dataclass(frozen=True)
class ReduceGeneric(CostModifier):
    """Reduce a cost by ``amount`` generic mana (118.7a)."""

    amount: int

    @property
    def step(self) -> ModifierStep:
        return ModifierStep.REDUCTION

    def apply(self, cost: ManaCost) -> ManaCost:
        raise NotImplementedRule("118.7a: reducing a cost by generic mana")


@dataclass(frozen=True)
class SpellCostModifier(Ability, ABC):
    """A static ability that changes the total cost of spells (601.2f, 113.3d)."""

    @abstractmethod
    def modifier(
        self, state: GameState, source: ObjectId, spell: ObjectId, caster: PlayerId
    ) -> CostModifier | None:
        """What this ability of ``source`` does to the cost of ``spell``, which ``caster`` is
        casting; ``None`` if it doesn't apply to that spell."""


@dataclass(frozen=True)
class SpellCostReduction(SpellCostModifier):
    """ "[Quality] spells you cast cost {N} less to cast." (601.2f, 118.7a)."""

    spells: Quality
    amount: int = 1

    def modifier(
        self, state: GameState, source: ObjectId, spell: ObjectId, caster: PlayerId
    ) -> CostModifier | None:
        raise NotImplementedRule("601.2f: cost reductions")

    @property
    def text(self) -> str:
        spells = f"{self.spells.adjective} spells".strip()
        return f"{spells[0].upper()}{spells[1:]} you cast cost {{{self.amount}}} less to cast."
