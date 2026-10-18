"""Effects (609): what an ability or spell does when it resolves."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.events.mana import ManaAdded
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import Mana, ManaType
from resolve.values import Immutable

if TYPE_CHECKING:
    from resolve.events.base import Event
    from resolve.state.game import GameState


@dataclass(frozen=True)
class AddMana(Immutable):
    """ "Add [mana]": the controller adds this mana to their mana pool (106.3, 106.4).

    The mana's source is the object whose ability produced it (106.3).
    """

    mana: tuple[ManaType, ...]

    def __post_init__(self) -> None:
        if not self.mana:
            raise ValueError("AddMana needs at least one mana")

    def events(self, state: GameState, source: ObjectId, player: PlayerId) -> tuple[Event, ...]:
        """The events of this effect, for ``player`` resolving ``source``'s ability."""
        added = tuple(Mana(mana_type, source) for mana_type in self.mana)
        return (ManaAdded(player=player, mana=added, rules=("106.3", "106.4")),)

    @property
    def text(self) -> str:
        """The effect as printed, such as ``"Add {G}."``."""
        return "Add " + "".join(mana_type.symbol for mana_type in self.mana) + "."
