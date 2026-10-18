"""Starting the game (103).

``StartGame`` runs the start-of-game procedure in order:

1. 103.1: a player, picked at random with the game's RNG (the "mutually agreeable method" of a
   single game), chooses who takes the first turn.
2. 103.2c / 903.6: commanders are already in the command zone (``initial_state``).
3. 103.3: each player's library is shuffled, in turn order. The optional extra shuffle or cut by
   opponents is left out: a uniformly random order stays uniformly random.
4. 103.4: life totals were set by ``initial_state``.
5. 103.5: opening hands and mulligans, which are not implemented yet (roadmap M1).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import AnswerValue, ChooseOne, Pick, PlayerOption
from resolve.errors import EngineError, NotImplementedRule
from resolve.events.game import LibraryShuffled, StartingPlayerChosen
from resolve.events.pipeline import ApplyEvents
from resolve.state.game import turn_order
from resolve.state.ids import PlayerId
from resolve.tasks import NeedDecision, Push, Task, TaskResult

if TYPE_CHECKING:
    from resolve.decisions.request import DecisionRequest
    from resolve.state.game import GameState


@dataclass(slots=True)
class StartGame(Task):
    """The start-of-game procedure (103). ``chooser`` is set once it has been picked."""

    chooser: PlayerId | None = None

    def run(self, state: GameState) -> TaskResult:
        # 103.1: determine which player chooses who takes the first turn.
        self.chooser = PlayerId(state.rng.randbelow(len(state.players)))
        return NeedDecision(
            player=self.chooser,
            kind=DecisionKind.CHOOSE_STARTING_PLAYER,
            space=ChooseOne(tuple(PlayerOption(player.id) for player in state.players)),
            prompt="Choose which player takes the first turn.",
            rules=("103.1",),
        )

    def resume(self, state: GameState, request: DecisionRequest, answer: AnswerValue) -> TaskResult:
        if self.chooser is None or not isinstance(request.space, ChooseOne):
            raise EngineError("StartGame resumed without having asked")
        if not isinstance(answer, Pick):
            raise EngineError(f"StartGame got an unvalidated answer {answer!r}")
        option = request.space.chosen(answer)
        assert isinstance(option, PlayerOption)
        chosen = StartingPlayerChosen(
            chooser=self.chooser, starting_player=option.player, rules=("103.1",)
        )
        return Push((ApplyEvents((chosen,)), ShuffleLibraries(), OpeningHands()))


@dataclass(slots=True)
class ShuffleLibraries(Task):
    """103.3 (and 903.6): each player shuffles their library, in turn order."""

    def run(self, state: GameState) -> TaskResult:
        shuffles = tuple(
            LibraryShuffled(player=player, rules=("103.3", "701.24a"))
            for player in turn_order(state)
        )
        return Push((ApplyEvents(shuffles),))


@dataclass(slots=True)
class OpeningHands(Task):
    """103.5: opening hands and mulligans."""

    def run(self, state: GameState) -> TaskResult:
        raise NotImplementedRule("103.5: opening hands and mulligans (roadmap M1)")
