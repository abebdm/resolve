"""Taking turns: phases, steps and their turn-based actions (500-514, 103.8).

``TakeTurn`` runs one player's turn through the segments the rules give it
(``defaults.turn_structure``, 500.1), kept as data in ``TurnState.segments``, and then starts the
next turn (``defaults.next_turn``: extra turns first, 500.7, then the next player in turn order,
103.1). It stays on the task stack for the whole turn, so it is the turn's frame: removing every
task above it and the remaining segments cuts the rest of the turn short (724,
``turn_frame_index``).
Each segment is a ``RunStep``:

1. the step (or main phase) begins: ``StepBegan`` (500.4 and 500.6 happen here);
2. its turn-based actions (703);
3. a round of priority, in every step but untap and cleanup (117.3a, 502.4, 514.3);
4. it ends: effects lasting until its end would expire (none exist yet), then unspent mana
   empties from every pool (500.5, 703.4q).

Skipped steps (500.11) don't begin at all (``defaults.is_skipped``):

- 103.8a: in a two-player game, the starting player skips the draw step of their first turn.
  In a game that began with more than two players nobody does (103.8c).
- 508.8: with no creature declared as an attacker this combat, the declare blockers and combat
  damage steps are skipped.

The turn-based actions implemented:

- untap step: 502.1 (phasing) and 502.2 (day and night) can't apply, since nothing has phasing
  and it is never day or night; 502.3: the active player untaps their permanents at once, those
  ``defaults.permanents_that_untap`` names (all of them).
- draw step: the active player draws ``defaults.draw_step_draws`` cards, one (504.1).
- the combat phase: as its first step begins, the combat state is created (``CombatBegan``) with
  its defending players: in a two-player game the nonactive player (506.2); every multiplayer
  game uses the attack multiple players option, so all the active player's opponents (802.2,
  docs/decisions.md). 507.1 then has no choice to make. Declaring attackers (508.1), whether a
  block is possible (509.1, M3.3) and combat damage (510.1-510.2) are the tasks of
  ``resolve.engine.combat``. As the end of combat step ends, ``CombatEnded`` removes everything
  from combat (511.3).
- cleanup: the active player discards down to their maximum hand size, seven (514.1, 402.2,
  ``defaults.maximum_hand_size``);
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

from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import (
    AnswerValue,
    ChooseOrder,
    ChooseSubset,
    ObjectOption,
    Order,
    PickMany,
)
from resolve.engine.combat import CombatDamage, DeclareAttackers, DeclareBlockers
from resolve.engine.drawing import DrawCards
from resolve.engine.mana import EmptyManaPools
from resolve.engine.priority import PriorityRound, current_turn
from resolve.engine.sba import state_based_actions
from resolve.errors import EngineError
from resolve.events.base import Event
from resolve.events.cards import CardDiscarded
from resolve.events.combat import CombatBegan, CombatEnded
from resolve.events.permanents import DamageRemoved, PermanentsUntapped
from resolve.events.pipeline import ApplyEvents
from resolve.events.turn import StepBegan, TurnBegan
from resolve.rules import defaults
from resolve.rules.combat import defending_players
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.turn import Phase, Step, gives_priority
from resolve.tasks import Done, NeedDecision, Push, Task, TaskResult

if TYPE_CHECKING:
    from resolve.decisions.request import DecisionRequest
    from resolve.state.game import GameState


@dataclass(slots=True)
class FirstTurn(Task):
    """103.8: the starting player takes the first turn."""

    def run(self, state: GameState) -> TaskResult:
        if state.starting_player is None:
            raise EngineError("the first turn needs a starting player (103.1)")
        return Push((TakeTurn(state.starting_player),))


@dataclass(slots=True)
class TakeTurn(Task):
    """``player``'s turn, and the frame of the task stack that holds everything the turn does.

    - ``extra``: this turn is one of ``GameState.extra_turns`` (500.7), taken after ``regular``.
    - ``regular``: the player whose regular turn the turn order is at (``None``: ``player``).
      The turn that follows an extra turn is the one after this player's, not the extra turn's
      player's (500.7: extra turns are added directly after the specified turn).
    - ``started``: the turn has begun (``TurnBegan``).
    """

    player: PlayerId
    extra: bool = False
    regular: PlayerId | None = None
    started: bool = False

    def run(self, state: GameState) -> TaskResult:
        after = self.player if self.regular is None else self.regular
        if not self.started:
            if self.extra:
                state.extra_turns.pop()  # 500.7: taken now (or lost, 800.4k)
            if state.player(self.player).left_game:
                # 800.4k: a player who left the game doesn't begin a turn.
                return Push((self._next(state, after),))
            self.started = True
            number = 1 if state.turn is None else state.turn.number + 1
            began = TurnBegan(player=self.player, number=number, rules=("500.1",))
            return Push((ApplyEvents((began,)), self))
        turn = current_turn(state)
        while turn.segments:
            segment = turn.segments.pop(0)
            if not defaults.is_skipped(state, segment):
                return Push((RunStep(*segment), self))
        # The turn is over; the next one begins (500.7, 103.1, 500.1).
        return Push((self._next(state, after),))

    def _next(self, state: GameState, after: PlayerId) -> TakeTurn:
        following = defaults.next_turn(state, after)
        if following.extra:
            return TakeTurn(following.player, extra=True, regular=after)
        return TakeTurn(following.player)


def turn_frame_index(state: GameState) -> int:
    """The index in ``state.tasks`` of the turn in progress's frame, its ``TakeTurn`` (724).

    Every task above it belongs to the turn; ending the turn removes them and the remaining
    segments (``TurnState.segments``) that the turn skips. ``EngineError`` outside a turn.
    """
    for index in range(len(state.tasks) - 1, -1, -1):
        if isinstance(state.tasks[index], TakeTurn):
            return index
    raise EngineError("there is no turn in progress, so there is no turn frame (724)")


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
                events: tuple[Event, ...] = (began,)
                if self.phase is Phase.COMBAT and turn.combat is None:
                    # 506.2, 802.2: the combat phase begins with its defending players.
                    defending = defending_players(state)
                    events += (CombatBegan(defending_players=defending, rules=("506.2", "802.2")),)
                return Push((ApplyEvents(events), self))
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
                if self.step is Step.END_OF_COMBAT and turn.combat is not None:
                    tasks.append(ApplyEvents((CombatEnded(rules=("511.3",)),)))
                if self.priority_given:
                    # 514.3a: once the stack is empty and all pass, another cleanup step begins.
                    tasks.append(RunStep(self.phase, Step.CLEANUP))
                return Push(tuple(tasks))

    def _turn_based_actions(self, state: GameState, active: PlayerId) -> tuple[Task, ...]:
        match self.step:
            case Step.UNTAP:
                # 502.3: the active player untaps their permanents at once.
                tapped = tuple(
                    obj
                    for obj in defaults.permanents_that_untap(state, active)
                    if state.objects[obj].tapped
                )
                if not tapped:
                    return ()
                untap = PermanentsUntapped(objs=tapped, rules=("502.3", "701.26b"))
                return (ApplyEvents((untap,)),)
            case Step.DRAW:
                if state.player(active).left_game:
                    return ()  # 800.4j: the turn goes on without an active player to draw
                draws = defaults.draw_step_draws(state, active)
                return (DrawCards(active, draws, ("504.1",)),) if draws > 0 else ()
            case Step.DECLARE_ATTACKERS:
                return (DeclareAttackers(),)
            case Step.DECLARE_BLOCKERS:
                return (DeclareBlockers(),)
            case Step.COMBAT_DAMAGE:
                return (CombatDamage(),)
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
        maximum = defaults.maximum_hand_size(state, self.player)
        if maximum is None or len(hand) <= maximum:
            return Done()  # 402.2: no maximum hand size, or the hand is within it
        excess = len(hand) - maximum
        return NeedDecision(
            player=self.player,
            kind=DecisionKind.DISCARD,
            space=ChooseSubset(tuple(ObjectOption(obj) for obj in hand), excess, excess),
            prompt=f"Discard {excess} card(s) down to your maximum hand size of {maximum}.",
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
