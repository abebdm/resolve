"""Abilities (113) that card definitions are built from.

So far: activated mana abilities (605.1a), such as basic lands' intrinsic "{T}: Add [mana]"
(305.6, ``intrinsic_mana_ability``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.cards.primitives.base import Ability
from resolve.cards.primitives.costs import Cost, TapSelfCost
from resolve.cards.primitives.effects import AddMana
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import ManaType

if TYPE_CHECKING:
    from resolve.state.game import GameState

# 305.6: each basic land type and the mana its intrinsic ability adds.
BASIC_LAND_MANA: dict[str, ManaType] = {
    "Plains": ManaType.WHITE,
    "Island": ManaType.BLUE,
    "Swamp": ManaType.BLACK,
    "Mountain": ManaType.RED,
    "Forest": ManaType.GREEN,
}


@dataclass(frozen=True)
class ActivatedManaAbility(Ability):
    """An activated mana ability (605.1a): ``cost``, then ``effect`` adds mana.

    It doesn't use the stack and resolves as soon as it is activated (605.3b). Only the
    object's controller may activate it (602.2), whenever they have priority (605.3a).
    """

    cost: tuple[Cost, ...]
    effect: AddMana

    def can_activate(self, state: GameState, source: ObjectId, player: PlayerId) -> bool:
        """Whether ``player`` may activate this ability of ``source`` now (602.2, 118.3)."""
        if state.object(source).controller != player:
            return False
        return all(cost.can_pay(state, source, player) for cost in self.cost)

    @property
    def text(self) -> str:
        """The ability as printed, such as ``"{T}: Add {G}."``."""
        return ", ".join(cost.text for cost in self.cost) + ": " + self.effect.text


def intrinsic_mana_ability(land_type: str) -> ActivatedManaAbility:
    """305.6: a land with this basic land type's intrinsic "{T}: Add [mana symbol]"."""
    return ActivatedManaAbility((TapSelfCost(),), AddMana((BASIC_LAND_MANA[land_type],)))
