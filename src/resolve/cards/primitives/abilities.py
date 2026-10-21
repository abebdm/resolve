"""Abilities (113) that card definitions are built from.

So far: activated mana abilities (605.1a), such as basic lands' intrinsic "{T}: Add [mana]"
(305.6, ``intrinsic_mana_ability``), with costs (``resolve.cards.primitives.costs``), an effect
(``AddMana``, ``AddManaOfAnyColor``) and an optional activation condition (602.5,
``resolve.cards.primitives.conditions``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.cards.primitives.base import Ability
from resolve.cards.primitives.conditions import ControlsAtLeast
from resolve.cards.primitives.costs import Cost, ManaPaymentCost, TapSelfCost
from resolve.cards.primitives.effects import AddMana, ManaEffect
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
    object's controller may activate it (602.2), whenever they have priority or are paying a
    cost (605.3a), and only while ``activate_only_if`` (if any) is met (602.5). At most one cost
    is a mana cost (``ManaPaymentCost``, 602.2b).
    """

    cost: tuple[Cost, ...]
    effect: ManaEffect
    activate_only_if: ControlsAtLeast | None = None

    def __post_init__(self) -> None:
        if sum(isinstance(cost, ManaPaymentCost) for cost in self.cost) > 1:
            raise ValueError("an activation cost has at most one mana cost (602.2b)")

    def can_activate(self, state: GameState, source: ObjectId, player: PlayerId) -> bool:
        """Whether ``player`` may begin to activate this ability of ``source`` now (602.2, 602.5,
        118.3). A mana cost is only known to be payable once paid (``ManaPaymentCost``)."""
        if state.object(source).controller != player:
            return False
        if self.activate_only_if is not None and not self.activate_only_if.met(
            state, source, player
        ):
            return False
        return all(cost.can_pay(state, source, player) for cost in self.cost)

    @property
    def mana_cost(self) -> ManaPaymentCost | None:
        """The mana part of the activation cost, if it has one (602.2b)."""
        for cost in self.cost:
            if isinstance(cost, ManaPaymentCost):
                return cost
        return None

    @property
    def text(self) -> str:
        """The ability as printed, such as ``"{T}: Add {G}."``."""
        text = ", ".join(cost.text for cost in self.cost) + ": " + self.effect.text
        if self.activate_only_if is not None:
            text += " " + self.activate_only_if.text
        return text


def intrinsic_mana_ability(land_type: str) -> ActivatedManaAbility:
    """305.6: a land with this basic land type's intrinsic "{T}: Add [mana symbol]"."""
    return ActivatedManaAbility((TapSelfCost(),), AddMana((BASIC_LAND_MANA[land_type],)))
