"""Last known information (608.2h, 113.7a, design.md §17.9).

An object that changes zones becomes a new object (400.7), and the old one is gone from the game
state. Effects that need information about an object that has left the battlefield or the stack
(Swords to Plowshares' "its controller gains life equal to its power", the source of damage that
is gone) use the object as it last existed there: its ``LastKnown`` value.

``move_object`` records one for every object leaving the battlefield or the stack, in
``GameState.last_known`` under the old object's ID. Entries are cleared when a player is about to
receive priority with an empty stack (``PriorityRound``): nothing that could still ask for them
is left by then. Look-back over earlier events ("dealt damage this turn", 603.10, 608.2i) is a
separate history, from M4.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.effects.characteristics import Characteristics, characteristics
from resolve.state.ids import PlayerId
from resolve.state.spell import CastChoices
from resolve.state.zones import Zone
from resolve.values import Immutable

if TYPE_CHECKING:
    from resolve.state.game import GameObject, GameState


@dataclass(frozen=True)
class LastKnown(Immutable):
    """An object as it last existed in the zone it left (608.2h): its characteristics (109.3),
    controller (108.4), owner (108.3), the zone, its tapped status (110.5), the damage marked on
    it (120.6) and, for a spell, its record (601.2)."""

    characteristics: Characteristics
    controller: PlayerId | None
    owner: PlayerId
    zone: Zone
    tapped: bool = False
    damage: int = 0
    spell: CastChoices | None = None


def snapshot(state: GameState, obj: GameObject) -> LastKnown:
    """``obj`` as it is now: what will be its last known information once it leaves its zone."""
    return LastKnown(
        characteristics=characteristics(state, obj.id),
        controller=obj.controller,
        owner=obj.owner,
        zone=obj.zone,
        tapped=obj.tapped,
        damage=obj.damage,
        spell=obj.spell,
    )
