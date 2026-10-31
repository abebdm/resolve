"""Combat rules that read the game state (506-511; design.md §17.18).

M3.1 has only who the defending players are; declaring attackers and blockers, combat damage
and leaving combat arrive in M3.2 to M3.7.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from resolve.errors import EngineError
from resolve.state.game import apnap_order
from resolve.state.ids import PlayerId

if TYPE_CHECKING:
    from resolve.state.game import GameState


def defending_players(state: GameState) -> tuple[PlayerId, ...]:
    """The defending players as the combat phase begins, in APNAP order (101.4).

    506.2: in a two-player game, the nonactive player. 802.2: in a multiplayer game, every
    opponent of the attacking player (the attack multiple players option, Commander's default,
    903.2). That every opponent defends is a deliberate non-parameter, not a rule default
    (docs/decisions.md 2026-10-18): the "attack left/right" options (803) would change the
    procedure, not a value. Players who have left the game aren't opponents in it (800.4a).
    """
    turn = state.turn
    if turn is None:
        raise EngineError("defending players exist only during a turn's combat phase (506.2)")
    return tuple(player for player in apnap_order(state) if player != turn.active_player)
