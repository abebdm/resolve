"""Activating mana abilities (605) and emptying mana pools (500.5)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.cards.primitives.abilities import ActivatedManaAbility
from resolve.effects.characteristics import characteristics
from resolve.errors import EngineError
from resolve.events.mana import ManaPoolEmptied
from resolve.events.pipeline import ApplyEvents
from resolve.rules import defaults
from resolve.state.game import apnap_order
from resolve.state.ids import ObjectId, PlayerId
from resolve.tasks import Done, Push, Task, TaskResult

if TYPE_CHECKING:
    from resolve.events.base import Event
    from resolve.state.game import GameState


@dataclass(slots=True)
class ActivateManaAbility(Task):
    """``player`` activates ability ``index`` of ``source``, a mana ability (605.3a).

    The costs are paid (602.2b, 601.2h), then the ability resolves at once without using the stack
    (605.3b). ``paid`` records that the costs have been paid.
    """

    player: PlayerId
    source: ObjectId
    index: int
    paid: bool = False

    def run(self, state: GameState) -> TaskResult:
        ability = characteristics(state, self.source).abilities[self.index]
        if not isinstance(ability, ActivatedManaAbility):
            raise EngineError(f"ability {self.index} of object {self.source} isn't a mana ability")
        if not self.paid:
            if not ability.can_activate(state, self.source, self.player):
                raise EngineError(f"player {self.player} can't activate that ability now")
            self.paid = True
            payment: list[Event] = []
            for cost in ability.cost:
                payment += cost.payment(state, self.source, self.player)
            return Push((ApplyEvents(tuple(payment)), self))
        return Push((ApplyEvents(ability.effect.events(state, self.source, self.player)),))


def empty_mana_pools(state: GameState) -> tuple[Event, ...]:
    """500.5, 703.4q: every player's unspent mana that empties does so, in APNAP order
    (``defaults.mana_that_empties``: all of it); nothing for a player with none to empty."""
    events: list[Event] = []
    for player in apnap_order(state):
        emptying = defaults.mana_that_empties(state, player)
        if not emptying:
            continue
        kept = list(state.player(player).mana_pool)
        for unit in emptying:
            kept.remove(unit)
        events.append(
            ManaPoolEmptied(
                player=player, mana=emptying, kept=tuple(kept), rules=("500.5", "703.4q", "106.4")
            )
        )
    return tuple(events)


@dataclass(slots=True)
class EmptyManaPools(Task):
    """As a step or phase ends, unspent mana empties from every pool (500.5, 703.4q)."""

    def run(self, state: GameState) -> TaskResult:
        events = empty_mana_pools(state)
        return Push((ApplyEvents(events),)) if events else Done()
