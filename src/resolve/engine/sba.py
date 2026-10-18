"""State-based actions (704) and the end of the game they can bring (104).

``state_based_actions(state)`` lists the state-based actions that would be performed right now,
as events. ``CheckStateBasedActions`` performs them all at once, as a single event (704.3), then
checks again, until a check performs nothing. The state-based actions implemented so far:

- 704.5a: a player with 0 or less life loses the game.
- 704.5b: a player who attempted to draw from an empty library since the last check loses.

A player who loses leaves the game (104.5). ``EndCheck`` then ends the game if at most one
player is left: the last player in the game wins (104.2a), and if none is left the game is a
draw (104.4a). A game that continues after a player leaves (800.4) is not implemented yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.errors import NotImplementedRule
from resolve.events.base import Event
from resolve.events.game import GameEnded, PlayerLost
from resolve.events.pipeline import ApplyEvents
from resolve.state.game import players_in_game
from resolve.tasks import Done, Push, Task, TaskResult

if TYPE_CHECKING:
    from resolve.state.game import GameState


def state_based_actions(state: GameState) -> tuple[Event, ...]:
    """The state-based actions to perform now, in APNAP order of the players affected (704.3).

    Every condition is checked before anything is performed, so they happen simultaneously.
    """
    events: list[Event] = []
    for player_id in players_in_game(state):
        player = state.player(player_id)
        if player.life <= 0:
            events.append(PlayerLost(player=player_id, rules=("704.5a", "704.3")))
        elif player.drew_from_empty_library:
            events.append(PlayerLost(player=player_id, rules=("704.5b", "121.4", "704.3")))
    return tuple(events)


@dataclass(slots=True)
class CheckStateBasedActions(Task):
    """704.3: perform every applicable state-based action as one event; repeat until none apply.

    Triggered abilities waiting to be put on the stack would go on it between checks (704.3);
    none can exist until M4.
    """

    def run(self, state: GameState) -> TaskResult:
        events = state_based_actions(state)
        if not events:
            return Done()
        tasks: list[Task] = [ApplyEvents(events)]
        if any(isinstance(event, PlayerLost) for event in events):
            tasks.append(EndCheck())
        return Push((*tasks, self))


@dataclass(slots=True)
class EndCheck(Task):
    """After players lose (104.5): end the game if at most one player is still in it."""

    def run(self, state: GameState) -> TaskResult:
        remaining = players_in_game(state)
        if len(remaining) == 1:
            return Push((ApplyEvents((GameEnded(winners=remaining, rules=("104.2a",)),)),))
        if not remaining:
            return Push((ApplyEvents((GameEnded(winners=(), rules=("104.4a",)),)),))
        raise NotImplementedRule(
            "800.4a: a player leaving a game that other players continue (roadmap M1.5)"
        )
