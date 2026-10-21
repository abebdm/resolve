"""Commander qualities that rules and effects read (903).

So far: a player's commanders' combined color identity (903.4), for "any color in your
commander's color identity" (Command Tower, Arcane Signet).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from resolve.data.cards import CardData
from resolve.data.types import Color
from resolve.state.ids import PlayerId

if TYPE_CHECKING:
    from resolve.state.game import GameState


def commander_color_identity(state: GameState, player: PlayerId) -> tuple[Color, ...] | None:
    """The combined color identity of ``player``'s commanders, in WUBRG order (903.4, 105.1), or
    ``None`` if they have no commander: the quality is then undefined (903.4f).

    903.4a: the identity is established before the game begins, from the card, so it is read from
    the card data (Scryfall's ``color_identity``, which follows 903.4 and 903.4c-e). A game
    without the Commander rules has no commanders. 903.4b (a color chosen before the game for
    the identity) has no card yet.
    """
    commanders = state.player(player).commanders
    if not commanders:
        return None
    identity = {color for card in commanders for color in _identity(state.cards[card].data)}
    return tuple(color for color in Color if color in identity)


def _identity(data: CardData) -> tuple[Color, ...]:
    return tuple(Color(symbol) for symbol in data.color_identity)
