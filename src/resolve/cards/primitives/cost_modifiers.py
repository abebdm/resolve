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
    """Reduce a cost by ``amount`` generic mana (118.7a): its colored and colorless symbols stay,
    and its generic part stops at nothing (601.2f: ``{0}`` if nothing else is left). Generic
    reductions give the same total in any order, so 601.2f's "in any order" asks nothing."""

    amount: int

    @property
    def step(self) -> ModifierStep:
        return ModifierStep.REDUCTION

    def apply(self, cost: ManaCost) -> ManaCost:
        # 118.7a: only the generic component; 601.2f: never below nothing ({0}).
        return cost.with_generic(max(0, cost.generic - self.amount))


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
    """ "[Quality] spells you cast cost {N} less to cast." (601.2f, 118.7a): a spell with the
    quality ``spells`` (a color, a subtype: 205.3, "a Dinosaur spell" has that subtype) that the
    ability's controller casts costs ``amount`` less generic mana. A permanent's ability, so it
    functions only on the battlefield (113.6). It changes the total cost, never the mana cost or
    mana value (202.3, 118.7)."""

    spells: Quality
    amount: int = 1

    def modifier(
        self, state: GameState, source: ObjectId, spell: ObjectId, caster: PlayerId
    ) -> CostModifier | None:
        from resolve.effects.characteristics import characteristics

        # "You": the controller of the ability's source; the spell is judged by its
        # characteristics on the stack, as it is being cast (601.2f).
        if state.object(source).controller != caster:
            return None
        if not self.spells.matches(characteristics(state, spell)):
            return None
        return ReduceGeneric(self.amount)

    @property
    def text(self) -> str:
        spells = f"{self.spells.adjective} spells".strip()
        return f"{spells[0].upper()}{spells[1:]} you cast cost {{{self.amount}}} less to cast."
