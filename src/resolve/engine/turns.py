"""Taking turns: phases, steps and their turn-based actions (500-514, 103.8).

``TakeTurn`` runs one player's turn through ``TURN_SEQUENCE`` (500.1) and then starts the next
player's turn in turn order (103.1). Each segment is a ``RunStep``:

1. the step (or main phase) begins: ``StepBegan`` (500.4 and 500.6 happen here);
2. its turn-based actions (703);
3. a round of priority, in every step but untap and cleanup (117.3a, 502.4, 514.3);
4. it ends: effects lasting until its end would expire (none exist yet), then unspent mana
   empties from every pool (500.5, 703.4q).

Skipped steps (500.11) don't begin at all:

- 103.8a: in a two-player game, the starting player skips the draw step of their first turn.
  In a game that began with more than two players nobody does (103.8c).
- 508.8: with no attackers declared, the declare blockers and combat damage steps are skipped.
  No creature can be declared as an attacker yet (508.1 raises ``NotImplementedRule`` whenever
  the active player controls a creature), so they are always skipped.

The turn-based actions implemented:

- untap step: 502.1 (phasing) and 502.2 (day and night) can't apply, since nothing has phasing
  and it is never day or night; 502.3: the active player untaps all their permanents at once.
- draw step: the active player draws a card (504.1).
- beginning of combat: 507.1 has no choice to make. In a two-player game the nonactive player
  is the defending player (506.2); every multiplayer game uses the attack multiple players
  option, so all the active player's opponents are defending players (802.2, docs/decisions.md).
- declare attackers: with no creature to attack with, the declaration is empty (508.1).
- cleanup: the active player discards down to their maximum hand size of seven (514.1, 402.2);
  514.2 removes all damage from permanents (and would end "until end of turn" effects, none of
  which can exist yet); then
  514.3a: if state-based actions would be performed (or triggers are waiting), they are, the
  active player receives priority, and another cleanup step follows.

The precombat main phase's turn-based actions (505.3-505.5: schemes, Sagas, Attractions) can't
apply, since none of those exist in the game.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from resolve.data.types import CardType
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import (
    AnswerValue,
    ChooseOrder,
    ChooseSubset,
    ObjectOption,
    Order,
    PickMany,
)
from resolve.effects.characteristics import characteristics
from resolve.engine.drawing import DrawCards
from resolve.engine.mana import EmptyManaPools
from resolve.engine.mulligans import is_multiplayer
from resolve.engine.priority import PriorityRound, current_turn
from resolve.engine.sba import state_based_actions
from resolve.errors import EngineError, NotImplementedRule
from resolve.events.cards import CardDiscarded
from resolve.events.permanents import DamageRemoved, PermanentsUntapped
from resolve.events.pipeline import ApplyEvents
from resolve.events.turn import StepBegan, TurnBegan
from resolve.state.game import next_in_turn_order
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.turn import TURN_SEQUENCE, Phase, Segment, Step, gives_priority
from resolve.tasks import Done, NeedDecision, Push, Task, TaskResult

if TYPE_CHECKING:
    from resolve.decisions.request import DecisionRequest
    from resolve.state.game import GameState

# 402.2: a player's maximum hand size is normally seven. No effect can change it yet.
MAXIMUM_HAND_SIZE = 7


@dataclass(slots=True)
class FirstTurn(Task):
    """103.8: the starting player takes the first turn."""

    def run(self, state: GameState) -> TaskResult:
        if state.starting_player is None:
            raise EngineError("the first turn needs a starting player (103.1)")
        return Push((TakeTurn(state.starting_player),))


@dataclass(slots=True)
class TakeTurn(Task):
    """``player``'s turn. ``position`` is the index in ``TURN_SEQUENCE`` of the next segment."""

    player: PlayerId
    position: int = 0
    started: bool = False

    def run(self, state: GameState) -> TaskResult:
        if not self.started and state.player(self.player).left_game:
            # 800.4k: a player who left the game doesn't begin a turn.
            return Push((TakeTurn(next_in_turn_order(state, self.player)),))
        if not self.started:
            self.started = True
            number = 1 if state.turn is None else state.turn.number + 1
            began = TurnBegan(player=self.player, number=number, rules=("500.1",))
            return Push((ApplyEvents((began,)), self))
        while self.position < len(TURN_SEQUENCE):
            segment = TURN_SEQUENCE[self.position]
            self.position += 1
            if not _skipped(state, segment):
                return Push((RunStep(*segment), self))
        # The turn is over; the next player in turn order takes the next turn (103.1, 500.1).
        return Push((TakeTurn(next_in_turn_order(state, self.player)),))


def _skipped(state: GameState, segment: Segment) -> bool:
    _, step = segment
    if step is Step.DRAW:
        # 103.8a: the starting player's first draw step, in a two-player game (103.8c).
        return current_turn(state).number == 1 and not is_multiplayer(state)
    # 508.8: no attackers can have been declared (see the module docstring).
    return step in (Step.DECLARE_BLOCKERS, Step.COMBAT_DAMAGE)


class StepStage(Enum):
    """Where ``RunStep`` is in its step."""

    BEGIN = "begin"
    ACTIONS = "actions"
    PRIORITY = "priority"
    END = "end"


@dataclass(slots=True)
class RunStep(Task):
    """One step of the turn, or a main phase (``step`` is ``None``), from beginning to end.

    ``priority_given`` records, in a cleanup step, that the active player received priority
    (514.3a), so another cleanup step follows this one.
    """

    phase: Phase
    step: Step | None
    stage: StepStage = StepStage.BEGIN
    priority_given: bool = False

    def run(self, state: GameState) -> TaskResult:
        turn = current_turn(state)
        match self.stage:
            case StepStage.BEGIN:
                self.stage = StepStage.ACTIONS
                began = StepBegan(phase=self.phase, step=self.step, rules=_begin_rules(self.step))
                return Push((ApplyEvents((began,)), self))
            case StepStage.ACTIONS:
                self.stage = StepStage.PRIORITY
                actions = self._turn_based_actions(state, turn.active_player)
                return Push((*actions, self)) if actions else self.run(state)
            case StepStage.PRIORITY:
                self.stage = StepStage.END
                if gives_priority(self.step):
                    return Push((PriorityRound(), self))
                if self.step is Step.CLEANUP and state_based_actions(state):
                    # 514.3a: state-based actions would be performed (no triggers can exist
                    # yet), so they are, and the active player receives priority.
                    self.priority_given = True
                    return Push((PriorityRound(), self))
                return self.run(state)
            case StepStage.END:
                # 500.5: effects lasting until the end of the step would expire (none exist
                # yet); then unspent mana empties.
                tasks: list[Task] = [EmptyManaPools()]
                if self.priority_given:
                    # 514.3a: once the stack is empty and all pass, another cleanup step begins.
                    tasks.append(RunStep(self.phase, Step.CLEANUP))
                return Push(tuple(tasks))

    def _turn_based_actions(self, state: GameState, active: PlayerId) -> tuple[Task, ...]:
        match self.step:
            case Step.UNTAP:
                # 502.3: the active player untaps all their permanents at once (no effect can
                # keep one from untapping yet).
                tapped = tuple(
                    obj
                    for obj in state.battlefield
                    if state.objects[obj].controller == active and state.objects[obj].tapped
                )
                if not tapped:
                    return ()
                untap = PermanentsUntapped(objs=tapped, rules=("502.3", "701.26b"))
                return (ApplyEvents((untap,)),)
            case Step.DRAW:
                if state.player(active).left_game:
                    return ()  # 800.4j: the turn goes on without an active player to draw
                return (DrawCards(active, 1, ("504.1",)),)
            case Step.DECLARE_ATTACKERS:
                for obj in state.battlefield:
                    permanent = state.objects[obj]
                    if permanent.controller == active and characteristics(state, obj).is_a(
                        CardType.CREATURE
                    ):
                        raise NotImplementedRule("508.1: declaring attackers (roadmap M3)")
                return ()  # 508.1: the active player controls no creature, so none attack
            case Step.CLEANUP:
                return (DiscardToHandSize(active), RemoveDamage())
            case _:
                return ()


def _begin_rules(step: Step | None) -> tuple[str, ...]:
    rules = {
        Step.UNTAP: "502",
        Step.UPKEEP: "503",
        Step.DRAW: "504",
        None: "505",
        Step.BEGINNING_OF_COMBAT: "507",
        Step.DECLARE_ATTACKERS: "508",
        Step.DECLARE_BLOCKERS: "509",
        Step.COMBAT_DAMAGE: "510",
        Step.END_OF_COMBAT: "511",
        Step.END: "513",
        Step.CLEANUP: "514",
    }
    return (rules[step], "500.6")


@dataclass(slots=True)
class RemoveDamage(Task):
    """514.2: all damage marked on permanents is removed, at the same time ("until end of turn"
    and "this turn" effects would end with it; none can exist yet)."""

    def run(self, state: GameState) -> TaskResult:
        damaged = tuple(obj for obj in state.battlefield if state.objects[obj].damage)
        if not damaged:
            return Done()
        return Push((ApplyEvents((DamageRemoved(objs=damaged, rules=("514.2", "120.6")),)),))


@dataclass(slots=True)
class DiscardToHandSize(Task):
    """514.1: ``player`` discards down to their maximum hand size (402.2).

    They choose which cards (701.9b, ``DISCARD``), then, for two or more, the order the cards
    go into their graveyard (404.3, ``ORDER_CARDS``, listed from top to bottom). The cards are
    discarded at the same time, as one set of events.
    """

    player: PlayerId
    chosen: tuple[ObjectId, ...] = ()

    def run(self, state: GameState) -> TaskResult:
        if state.player(self.player).left_game:
            return Done()  # 800.4j: no active player to discard
        if len(self.chosen) > 1:
            return self._ask_order()  # asked again after a concession
        hand = state.player(self.player).hand
        excess = len(hand) - MAXIMUM_HAND_SIZE
        if excess <= 0:
            return Done()
        return NeedDecision(
            player=self.player,
            kind=DecisionKind.DISCARD,
            space=ChooseSubset(tuple(ObjectOption(obj) for obj in hand), excess, excess),
            prompt=f"Discard {excess} card(s) down to your maximum hand size of seven.",
            rules=("514.1", "402.2"),
        )

    def resume(self, state: GameState, request: DecisionRequest, answer: AnswerValue) -> TaskResult:
        match request.space, answer:
            case ChooseSubset(), PickMany():
                self.chosen = tuple(_object(o) for o in request.space.chosen(answer))
                if len(self.chosen) > 1:
                    return self._ask_order()
                return self._discard(self.chosen)
            case ChooseOrder(), Order():
                return self._discard(tuple(_object(o) for o in request.space.chosen(answer)))
            case _:
                raise EngineError(f"DiscardToHandSize can't resume with {answer!r}")

    def _ask_order(self) -> TaskResult:
        return NeedDecision(
            player=self.player,
            kind=DecisionKind.ORDER_CARDS,
            space=ChooseOrder(tuple(ObjectOption(obj) for obj in self.chosen)),
            prompt="Order the discarded cards in your graveyard, from top to bottom.",
            rules=("404.3",),
        )

    def _discard(self, top_to_bottom: tuple[ObjectId, ...]) -> TaskResult:
        # The cards go into the graveyard bottom first, so the first listed ends up on top.
        events = tuple(
            CardDiscarded(player=self.player, card=obj, rules=("514.1", "701.9a"))
            for obj in reversed(top_to_bottom)
        )
        return Push((ApplyEvents(events),))


def _object(option: object) -> ObjectId:
    if not isinstance(option, ObjectOption):
        raise EngineError(f"expected an object option, got {option!r}")
    return option.object
