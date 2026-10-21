"""Events of the turn structure: turns and steps beginning, and passing priority (500, 117)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.errors import EngineError
from resolve.events.base import Event
from resolve.state.ids import PlayerId
from resolve.state.mana import Mana
from resolve.state.turn import Phase, Segment, Step, TurnState

if TYPE_CHECKING:
    from resolve.state.game import GameState


@dataclass(frozen=True, kw_only=True)
class TurnBegan(Event):
    """``player``'s turn ``number`` began (103.8, 500.1); they are the active player (102.1).

    The turn begins with its untap step (501.1), which ``StepBegan`` then records.
    ``segments`` is the turn's structure (500.1, ``defaults.turn_structure``); the turn keeps
    the segments still to come as data (``TurnState.segments``).
    """

    player: PlayerId
    number: int
    segments: tuple[Segment, ...] = ()

    def apply(self, state: GameState) -> None:
        state.player(self.player)  # validates the ID
        previous = 0 if state.turn is None else state.turn.number
        if self.number != previous + 1:
            raise EngineError(f"turn {self.number} can't follow turn {previous}")
        state.turn = TurnState(
            number=self.number, active_player=self.player, segments=list(self.segments)
        )


@dataclass(frozen=True, kw_only=True)
class StepBegan(Event):
    """A step began, or a main phase (``step`` is ``None``: it has no steps, 505.2).

    "At the beginning of" abilities will trigger on this event (500.6, M4). As a step or phase
    begins, effects lasting until it expire (500.4); none can exist yet. No player has priority
    as it begins (117.3a).
    """

    phase: Phase
    step: Step | None

    def apply(self, state: GameState) -> None:
        turn = state.turn
        if turn is None:
            raise EngineError("a step began outside a turn")
        turn.phase = self.phase
        turn.step = self.step
        turn.priority = None
        turn.passed.clear()


@dataclass(frozen=True, kw_only=True)
class PriorityPassed(Event):
    """``player`` passed priority, taking no action (117.3d).

    The record of the pass; the priority task then gives priority to the next player or ends
    the step (117.4). ``mana_in_pool`` is the unspent mana the player announces (117.3d,
    106.4b).
    """

    player: PlayerId
    mana_in_pool: tuple[Mana, ...] = ()

    def apply(self, state: GameState) -> None:
        state.player(self.player)  # validates the ID
