"""Conceding (104.3a): a player may concede at any time, through ``concede``.

The engine is always paused at a decision (or the game is over), so "any time" means while some
player is being asked something. Conceding:

1. withdraws the pending request: its id goes stale, and an answer to it is refused;
2. logs ``Conceded`` (public), the input a replay re-issues (design.md §12);
3. makes the player lose (``PlayerLost``, 104.3a) and leave the game (104.5, 800.4a), then ends
   the game if at most one player is left (104.2a, 104.4a);
4. runs the game on: the task that was asking runs again and asks anew (with a new request id),
   or, if the player who was asked has left, the decision goes to whoever the rules name now
   (800.4h, 800.4j).

Every task that asks for decisions supports step 4: its ``run`` is safe to call again after it
returned ``NeedDecision`` (design.md §5).
"""

from __future__ import annotations

from resolve.engine.loop import run
from resolve.engine.sba import leave_after_losses
from resolve.errors import EngineError, InvalidAnswer
from resolve.events.game import Conceded, PlayerLost
from resolve.events.pipeline import ApplyEvents
from resolve.state.game import GameState
from resolve.state.ids import PlayerId


def concede(state: GameState, player: PlayerId) -> None:
    """``player`` concedes the game (104.3a).

    Raises ``InvalidAnswer``, changing nothing, if the game is over or the player has already
    left it, and ``EngineError`` for an unknown player or a game stopped by an error.
    """
    conceding = state.player(player)  # validates the ID
    if state.result is not None:
        raise InvalidAnswer("the game is over")
    if conceding.left_game:
        raise InvalidAnswer(f"player {player} has already left the game")
    if state.pending is None:
        raise EngineError("no decision is pending (the engine stopped with an error earlier)")
    state.pending = None
    events = (
        Conceded(player=player, rules=("104.3a",)),
        PlayerLost(player=player, rules=("104.3a",)),
    )
    state.tasks.extend(reversed((ApplyEvents(events), *leave_after_losses(state, (player,)))))
    run(state)
