"""Opening hands and mulligans (103.5).

``OpeningHands`` runs the whole procedure:

1. Each player draws their starting hand size, the starting player first and then the others in
   turn order (103.5, 121.2c; 101.4e makes the starting player the active player).
2. The starting player, then each other player in turn order, declares whether they take a
   mulligan (``MULLIGAN``). Declarations are public (101.4b). A player who keeps may not
   mulligan again.
3. Once everyone has declared, all the players who chose to mulligan do so at the same time:
   their hands go back into their libraries, which are shuffled, and they draw new hands
   (121.2c order). Then each, in APNAP order (101.4), chooses as many cards as the mulligans
   they have taken to put on the bottom (``PUT_ON_BOTTOM``) and their order (``ORDER_CARDS``,
   listed top to bottom), and the cards go to the bottom together.
4. Steps 2 and 3 repeat until no player takes a mulligan.

Players who leave the game during the procedure (800.4a) are no longer asked or dealt with; a
task asking a player who left asks the next one instead (800.4h).

In a game that begins with more than two players (100.1b) the first mulligan a player takes
doesn't count toward the cards they put on the bottom or the mulligans they may take (103.5c).

"A player can take mulligans until their opening hand would be zero cards, after which they may
not take further mulligans" (103.5): a player may take another mulligan while their hand holds at
least one card, so the mulligan that leaves zero cards is allowed and the player then keeps
without being asked. With seven-card hands that allows seven mulligans (eight with 103.5c); a
short library reaches zero cards sooner, and an empty one at once (docs/decisions.md). A question
with a single possible answer isn't asked: putting every card of the hand on the bottom asks only
for their order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import (
    AnswerValue,
    ChooseOne,
    ChooseOrder,
    ChooseSubset,
    ObjectOption,
    Order,
    Pick,
    PickMany,
)
from resolve.engine.drawing import DrawCards
from resolve.errors import EngineError
from resolve.events.cards import CardsPutOnBottom, HandShuffledIntoLibrary
from resolve.events.game import MulliganDeclared
from resolve.events.pipeline import ApplyEvents
from resolve.rules import defaults
from resolve.rules.defaults import KEEP, MULLIGAN
from resolve.state.game import is_multiplayer, players_in_game, turn_order
from resolve.state.ids import ObjectId, PlayerId
from resolve.tasks import Done, NeedDecision, Push, Task, TaskResult

if TYPE_CHECKING:
    from resolve.decisions.request import DecisionRequest
    from resolve.state.game import GameState

__all__ = ["KEEP", "MULLIGAN", "OpeningHands", "Stage", "counted_mulligans"]


class Stage(Enum):
    """Where ``OpeningHands`` is in the procedure."""

    DRAW = "draw"
    DECLARE = "declare"
    BOTTOM = "bottom"


def counted_mulligans(state: GameState, taken: int) -> int:
    """How many of ``taken`` mulligans count toward cards on the bottom and the limit (103.5c)."""
    if is_multiplayer(state) and taken > 0:
        return taken - 1
    return taken


@dataclass(slots=True)
class OpeningHands(Task):
    """103.5: opening hands and mulligans.

    - ``taken``: mulligans each player has taken.
    - ``kept``: players who kept their hand, in the order they did.
    - ``declared``: this round's declarations (``True``: mulligan).
    - ``chosen``: this round's cards to put on the bottom, top to bottom, per player.
    - ``choosing``: the cards the player being asked chose, while their order is asked.
    """

    stage: Stage = Stage.DRAW
    taken: dict[PlayerId, int] = field(default_factory=dict[PlayerId, int])
    kept: list[PlayerId] = field(default_factory=list[PlayerId])
    declared: dict[PlayerId, bool] = field(default_factory=dict[PlayerId, bool])
    chosen: dict[PlayerId, tuple[ObjectId, ...]] = field(
        default_factory=dict[PlayerId, tuple[ObjectId, ...]]
    )
    choosing: tuple[ObjectId, ...] = ()

    def run(self, state: GameState) -> TaskResult:
        match self.stage:
            case Stage.DRAW:
                self.stage = Stage.DECLARE
                return Push((*self._draws(state, turn_order(state)), self))
            case Stage.DECLARE:
                return self._declare(state)
            case Stage.BOTTOM:
                return self._bottom(state)

    def _draws(self, state: GameState, players: tuple[PlayerId, ...]) -> tuple[Task, ...]:
        sizes = {player: defaults.starting_hand_size(state, player) for player in players}
        return tuple(
            DrawCards(player, size, ("103.5", "121.2c")) for player, size in sizes.items() if size
        )

    def _declare(self, state: GameState) -> TaskResult:
        for player in players_in_game(state):
            if player in self.kept or player in self.declared:
                continue
            choices = defaults.mulligan_options(state, player)
            if choices == (KEEP,):
                # 103.5: no further mulligans once the opening hand would be zero cards; a
                # question with a single possible answer isn't asked.
                self.kept.append(player)
                self.declared[player] = False
                continue
            return NeedDecision(
                player=player,
                kind=DecisionKind.MULLIGAN,
                space=ChooseOne(choices),
                prompt="Keep this hand, or take a mulligan?",
                rules=("103.5",),
            )
        mulliganing = tuple(p for p in players_in_game(state) if self.declared.get(p))
        if not mulliganing:
            return Done()
        for player in mulliganing:
            self.taken[player] = self.taken.get(player, 0) + 1
        self.stage = Stage.BOTTOM
        shuffles = tuple(
            HandShuffledIntoLibrary(
                player=player, cards=tuple(state.player(player).hand), rules=("103.5", "701.24a")
            )
            for player in mulliganing
        )
        return Push((ApplyEvents(shuffles), *self._draws(state, mulliganing), self))

    def _bottom(self, state: GameState) -> TaskResult:
        if any(obj not in state.objects for obj in self.choosing):
            self.choosing = ()  # the player choosing an order left the game (800.4a)
        for player in players_in_game(state):
            if not self.declared.get(player) or player in self.chosen:
                continue
            hand = state.player(player).hand
            count = min(counted_mulligans(state, self.taken[player]), len(hand))
            if not self.choosing:
                if count == 0:
                    self.chosen[player] = ()
                    continue
                if count < len(hand):
                    return NeedDecision(
                        player=player,
                        kind=DecisionKind.PUT_ON_BOTTOM,
                        space=ChooseSubset(tuple(ObjectOption(o) for o in hand), count, count),
                        prompt=f"Choose {count} card(s) to put on the bottom of your library.",
                        rules=("103.5",),
                    )
                self.choosing = tuple(hand)  # every card goes: only their order is a choice
            if len(self.choosing) == 1:
                self.chosen[player], self.choosing = self.choosing, ()
                continue
            return NeedDecision(
                player=player,
                kind=DecisionKind.ORDER_CARDS,
                space=ChooseOrder(tuple(ObjectOption(o) for o in self.choosing)),
                prompt="Order the cards you put on the bottom, from top to bottom.",
                rules=("103.5",),
            )
        events = tuple(
            CardsPutOnBottom(player=player, cards=cards, count=len(cards), rules=("103.5",))
            for player in players_in_game(state)
            if (cards := self.chosen.get(player, ()))
        )
        self.declared.clear()
        self.chosen.clear()
        self.stage = Stage.DECLARE
        if not events:
            return self._declare(state)
        return Push((ApplyEvents(events), self))

    def resume(self, state: GameState, request: DecisionRequest, answer: AnswerValue) -> TaskResult:
        player = request.for_player
        match request.kind, request.space, answer:
            case DecisionKind.MULLIGAN, ChooseOne(), Pick():
                take = request.space.chosen(answer) == MULLIGAN
                self.declared[player] = take
                if not take:
                    self.kept.append(player)
                declared = MulliganDeclared(player=player, mulligan=take, rules=("103.5",))
                return Push((ApplyEvents((declared,)), self))
            case DecisionKind.PUT_ON_BOTTOM, ChooseSubset(), PickMany():
                self.choosing = tuple(_object(o) for o in request.space.chosen(answer))
                return self._bottom(state)
            case DecisionKind.ORDER_CARDS, ChooseOrder(), Order():
                self.chosen[player] = tuple(_object(o) for o in request.space.chosen(answer))
                self.choosing = ()
                return self._bottom(state)
            case _:
                raise EngineError(f"OpeningHands can't resume {request.kind} with {answer!r}")


def _object(option: object) -> ObjectId:
    if not isinstance(option, ObjectOption):
        raise EngineError(f"expected an object option, got {option!r}")
    return option.object
