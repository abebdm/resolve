"""Starting the game (103).

``StartGame`` runs the start-of-game procedure in order:

1. 103.1: a player, picked at random with the game's RNG (the "mutually agreeable method" of a
   single game), chooses who takes the first turn.
2. 103.2c / 903.6: in a Commander game, each player puts their commander from their deck face up
   into the command zone. They do so simultaneously, so the new objects get timestamps in APNAP
   order from the starting player (613.7m, 101.4e).
3. 103.3: each player's library is shuffled, in turn order. The optional extra shuffle or cut by
   opponents is left out: a uniformly random order stays uniformly random.
4. 103.4: life totals were set by ``initial_state``.
5. 103.5: opening hands and mulligans (``resolve.engine.mulligans.OpeningHands``).
6. 103.6: actions from opening hands. No card definition can have such an ability yet, so there
   is nothing to do.
7. 103.8: the starting player takes their first turn (``resolve.engine.turns``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import AnswerValue, ChooseOne, Pick, PlayerOption
from resolve.engine.mulligans import OpeningHands
from resolve.engine.turns import FirstTurn
from resolve.errors import EngineError, NotImplementedRule
from resolve.events.game import (
    CommanderPutIntoCommandZone,
    LibraryShuffled,
    StartingPlayerChosen,
)
from resolve.events.pipeline import ApplyEvents
from resolve.state.game import turn_order
from resolve.state.ids import PlayerId
from resolve.tasks import Done, NeedDecision, Push, Task, TaskResult

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
        next_steps: tuple[Task, ...] = (ShuffleLibraries(), OpeningHands(), FirstTurn())
        if state.config.commander is not None:
            next_steps = (PutCommandersIntoCommandZone(), *next_steps)
        return Push((ApplyEvents((chosen,)), *next_steps))


@dataclass(slots=True)
class PutCommandersIntoCommandZone(Task):
    """103.2c / 903.6: each player puts their commander face up into the command zone."""

    def run(self, state: GameState) -> TaskResult:
        events: list[CommanderPutIntoCommandZone] = []
        for player_id in turn_order(state):
            player = state.player(player_id)
            if len(player.commanders) > 1:
                raise NotImplementedRule(
                    "613.7m: a player ordering the timestamps of their commanders entering "
                    "the command zone together"
                )
            for obj in player.library:
                if state.objects[obj].card in player.commanders:
                    events.append(
                        CommanderPutIntoCommandZone(
                            player=player_id, obj=obj, rules=("103.2c", "903.6", "613.7m")
                        )
                    )
        if not events:
            return Done()
        return Push((ApplyEvents(tuple(events)),))


@dataclass(slots=True)
class ShuffleLibraries(Task):
    """103.3 (and 903.6): each player shuffles their library, in turn order."""

    def run(self, state: GameState) -> TaskResult:
        shuffles = tuple(
            LibraryShuffled(player=player, rules=("103.3", "701.24a"))
            for player in turn_order(state)
        )
        return Push((ApplyEvents(shuffles),))

