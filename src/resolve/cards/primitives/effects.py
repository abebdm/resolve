"""Effects (609): what an ability or spell does when it resolves."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.data.types import Color
from resolve.events.mana import ManaAdded
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import Mana, ManaRestriction, ManaType
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


@dataclass(frozen=True)
class AddManaOfAnyColor(Immutable):
    """ "Add one mana of any color" (106.1a, 106.3), with the color chosen as the ability resolves.

    - ``commander_identity``: "... of any color in your commander's color identity" (903.4): only
      the colors of the identity of the controller's commanders (combined, if they have two). With
      no commander that quality is undefined (903.4f), and a commander whose identity has no
      color gives no color to choose: either way the ability adds no mana (106.5; Command Tower's
      and Arcane Signet's rulings), but it is still activated and its costs still paid.
    - ``restriction``: what the mana may be spent on (106.6), such as Ixalli's Lorekeeper's.

    ``colors`` lists the colors the controller may choose, in WUBRG order (105.1); the engine asks
    only when there are two or more (``CHOOSE_COLOR``).
    """

    commander_identity: bool = False
    restriction: ManaRestriction | None = None

    def colors(self, state: GameState, source: ObjectId, player: PlayerId) -> tuple[Color, ...]:
        """The colors ``player`` may choose for this mana now (903.4, 903.4f)."""
        if not self.commander_identity:
            return tuple(Color)
        from resolve.rules.commander import commander_color_identity

        return commander_color_identity(state, player) or ()  # 903.4f: undefined, no color

    def events(
        self, state: GameState, source: ObjectId, player: PlayerId, color: Color | None
    ) -> tuple[Event, ...]:
        """The events of this effect with ``color`` chosen; none if no color could be (106.5)."""
        if color is None:
            return ()
        mana = Mana(ManaType(color.value), source, self.restriction)
        return (ManaAdded(player=player, mana=(mana,), rules=("106.1a", "106.3", "106.4")),)

    @property
    def text(self) -> str:
        """The effect as printed, such as ``"Add one mana of any color."``."""
        text = "Add one mana of any color"
        text += " in your commander's color identity." if self.commander_identity else "."
        return text if self.restriction is None else f"{text} {self.restriction.text}"


ManaEffect = AddMana | AddManaOfAnyColor
"""What a mana ability's effect can be (605.1a)."""
