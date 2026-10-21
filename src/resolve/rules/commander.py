"""Commander qualities that rules and effects read (903).

So far: a player's commanders' combined color identity (903.4), for "any color in your
commander's color identity" (Command Tower, Arcane Signet).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from resolve.data.types import Color
from resolve.errors import NotImplementedRule
from resolve.state.ids import PlayerId

if TYPE_CHECKING:
    from resolve.state.game import GameState


def commander_color_identity(state: GameState, player: PlayerId) -> tuple[Color, ...] | None:
    """The combined color identity of ``player``'s commanders, in WUBRG order (903.4, 105.1), or
    ``None`` if they have no commander: the quality is then undefined (903.4f)."""
    raise NotImplementedRule("903.4: a commander's color identity (M2.4 stub)")
