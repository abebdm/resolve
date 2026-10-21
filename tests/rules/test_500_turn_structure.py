"""500-514: the turn structure, and 103.8: the first turn.

Expected values are worked from the pinned CR:

- 103.8: the starting player takes the first turn; then turns proceed in turn order (103.1).
- 500.1: five phases, in order; 501.1, 506.1, 512.1: the steps of the beginning, combat and
  ending phases. 505.2: a main phase has no steps.
- 508.8: with no attackers declared, the declare blockers and combat damage steps are skipped.
  No creature can attack in these tests (nobody controls a creature).
- 103.8a: in a two-player game the starting player skips the draw step of their first turn;
  103.8c: in other multiplayer games no player does.
- 502.4, 514.3: no player receives priority in the untap step, nor normally in cleanup.
- 504.1: the active player draws a card in their draw step.
"""

from __future__ import annotations

import copy
import pickle
from collections.abc import Callable

import pytest

from resolve.decisions.kinds import DecisionKind
from resolve.errors import NotImplementedRule
from resolve.events.turn import StepBegan, TurnBegan
from resolve.state.config import GameConfig
from resolve.state.game import GameState
from resolve.state.ids import PlayerId
from resolve.state.invariants import invariant_violations, state_impurities
from resolve.state.turn import TURN_SEQUENCE, Phase, Step
from tests.game_fixtures import Passer, deck, pass_until, request_of, started_game
from tests.scenario import Scenario

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)

FULL_TURN: list[tuple[Phase, Step | None]] = [
    (Phase.BEGINNING, Step.UNTAP),
    (Phase.BEGINNING, Step.UPKEEP),
    (Phase.BEGINNING, Step.DRAW),
    (Phase.PRECOMBAT_MAIN, None),
    (Phase.COMBAT, Step.BEGINNING_OF_COMBAT),
    (Phase.COMBAT, Step.DECLARE_ATTACKERS),
    (Phase.COMBAT, Step.END_OF_COMBAT),
    (Phase.POSTCOMBAT_MAIN, None),
    (Phase.ENDING, Step.END),
    (Phase.ENDING, Step.CLEANUP),
]


def steps_of_turn(state: GameState, number: int) -> list[tuple[Phase, Step | None]]:
    """The (phase, step) of every ``StepBegan`` logged during turn ``number``."""
    steps: list[tuple[Phase, Step | None]] = []
    current = 0
    for entry in state.event_log:
        record = entry.record
        if isinstance(record, TurnBegan):
            current = record.number
        elif isinstance(record, StepBegan) and current == number:
            steps.append((record.phase, record.step))
    return steps


def in_turn(number: int, phase: Phase, step: Step | None = None) -> Callable[[GameState], bool]:
    """Whether the turn has reached turn ``number``'s ``phase`` and ``step``."""

    def done(state: GameState) -> bool:
        turn = state.turn
        return turn is not None and (turn.number, turn.phase, turn.step) == (number, phase, step)

    return done


@pytest.mark.parametrize("starting", [0, 1])
def test_103_8_the_starting_player_takes_the_first_turn(starting: int) -> None:
    state = started_game(2, starting=starting)
    turn = state.turn
    assert turn is not None
    assert turn.number == 1
    assert turn.active_player == starting
    # The first decision of the turn is the starting player's priority in the upkeep (503.1).
    assert (turn.phase, turn.step) == (Phase.BEGINNING, Step.UPKEEP)
    request = request_of(state)
    assert request.kind is DecisionKind.PRIORITY_ACTION
    assert request.player == starting
    assert turn.priority == starting
    began = [e.record for e in state.event_log if isinstance(e.record, TurnBegan)]
    assert [(b.player, b.number) for b in began] == [(starting, 1)]


def test_500_1_the_steps_of_a_turn_in_order() -> None:
    """Turn 2 (no draw skip): every step and main phase, blockers and damage skipped (508.8)."""
    state = started_game(2)
    pass_until(state, in_turn(3, Phase.BEGINNING, Step.UPKEEP))
    assert steps_of_turn(state, 2) == FULL_TURN


def test_103_1_turns_proceed_in_turn_order() -> None:
    state = started_game(3, starting=1)
    pass_until(state, in_turn(5, Phase.BEGINNING, Step.UPKEEP))
    began = [e.record for e in state.event_log if isinstance(e.record, TurnBegan)]
    assert [(b.number, b.player) for b in began] == [(1, 1), (2, 2), (3, 0), (4, 1), (5, 2)]


def test_103_8a_the_starting_player_skips_their_first_draw_in_a_two_player_game() -> None:
    state = started_game(2, starting=1)
    assert steps_of_turn(state, 1)[:2] == FULL_TURN[:2]
    pass_until(state, in_turn(1, Phase.PRECOMBAT_MAIN))
    assert (Phase.BEGINNING, Step.DRAW) not in steps_of_turn(state, 1)
    assert len(state.player(P1).hand) == 7  # no draw on turn 1
    pass_until(state, in_turn(2, Phase.PRECOMBAT_MAIN))
    assert (Phase.BEGINNING, Step.DRAW) in steps_of_turn(state, 2)
    assert len(state.player(P0).hand) == 8  # 504.1: player 0 drew in turn 2's draw step
    assert steps_of_turn(state, 1) == [s for s in FULL_TURN if s[1] is not Step.DRAW]


def test_103_8a_a_two_player_commander_game_also_skips_the_first_draw() -> None:
    state = started_game(2, starting=0, config=GameConfig.commander_game())
    pass_until(state, in_turn(1, Phase.PRECOMBAT_MAIN))
    assert (Phase.BEGINNING, Step.DRAW) not in steps_of_turn(state, 1)
    assert len(state.player(P0).hand) == 7


def test_103_8c_no_player_skips_their_first_draw_in_a_multiplayer_game() -> None:
    state = started_game(3, starting=2)
    pass_until(state, in_turn(1, Phase.PRECOMBAT_MAIN))
    assert (Phase.BEGINNING, Step.DRAW) in steps_of_turn(state, 1)
    assert len(state.player(P2).hand) == 8
    assert [len(state.player(p).hand) for p in (P0, P1)] == [7, 7]


def test_504_1_the_active_player_draws_the_top_card_of_their_library() -> None:
    scenario = Scenario(2)
    top, _ = scenario.library(P1, ["Forest", "Llanowar Elves"])
    top_card = scenario.card_of(top)
    scenario.at(Step.DRAW, active=P1, number=2, begin=True)
    state = scenario.build()
    (drawn,) = state.player(P1).hand
    assert state.objects[drawn].card == top_card
    assert top not in state.objects  # 400.7: it became a new object
    assert len(state.player(P1).library) == 1
    assert state.player(P0).hand == []
    assert request_of(state).player == P1  # 504.2: then the active player gets priority


def test_502_4_514_3_no_player_receives_priority_in_the_untap_or_cleanup_step() -> None:
    agent = Passer()
    state = started_game(3)
    agent = pass_until(state, in_turn(5, Phase.BEGINNING, Step.UPKEEP), agent)
    priority_steps = {
        where[2]
        for request, where in agent.requests
        if request.kind is DecisionKind.PRIORITY_ACTION
        if where is not None
    }
    assert Step.UNTAP not in priority_steps
    assert Step.CLEANUP not in priority_steps
    # Every other step (and the main phases, None) does give priority (117.3a).
    assert priority_steps == {
        Step.UPKEEP,
        Step.DRAW,
        None,
        Step.BEGINNING_OF_COMBAT,
        Step.DECLARE_ATTACKERS,
        Step.END_OF_COMBAT,
        Step.END,
    }


def test_508_1_declaring_attackers_with_a_creature_is_a_gap() -> None:
    """Until M3, any creature the active player controls stops the game at 508.1."""
    scenario = Scenario(2)
    scenario.battlefield(P0, ["Llanowar Elves"])
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    with pytest.raises(NotImplementedRule) as gap:
        scenario.build()
    assert gap.value.rule == "508.1"


def test_508_1_an_opponents_creature_doesnt_stop_the_declaration() -> None:
    scenario = Scenario(2)
    scenario.battlefield(P1, ["Llanowar Elves"])
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    turn = state.turn
    assert turn is not None and turn.step is Step.DECLARE_ATTACKERS
    assert request_of(state).player == P0


@pytest.mark.parametrize("players", [2, 3])
def test_the_state_is_pure_and_round_trips_at_every_decision_of_a_turn(players: int) -> None:
    """design.md §4: paused at priority in every kind of step, the state is consistent, pure
    data, and equal after ``copy.deepcopy`` and a pickle round trip."""
    state = started_game(players)
    seen: set[tuple[Phase, Step | None]] = set()

    def check(current: GameState) -> bool:
        turn = current.turn
        assert turn is not None
        seen.add((turn.phase, turn.step))
        assert invariant_violations(current) == []
        assert state_impurities(current) == []
        assert copy.deepcopy(current) == current
        assert pickle.loads(pickle.dumps(current)) == current
        return turn.number == 3

    pass_until(state, check)
    assert seen >= {s for s in FULL_TURN if s[1] not in (Step.UNTAP, Step.CLEANUP)}


def test_a_turn_resumed_by_the_scenario_continues_into_the_next_turn() -> None:
    scenario = Scenario(2)
    scenario.library(P0, ["Forest"] * 3)
    scenario.library(P1, ["Forest"] * 3)
    scenario.at(Step.END, active=P1, number=4)
    state = scenario.build()
    pass_until(state, in_turn(5, Phase.BEGINNING, Step.UPKEEP))
    turn = state.turn
    assert turn is not None and turn.active_player == P0
    records = [e.record for e in state.event_log if isinstance(e.record, StepBegan | TurnBegan)]
    assert records[0] == StepBegan(phase=Phase.ENDING, step=Step.CLEANUP, rules=("514", "500.6"))
    assert records[1] == TurnBegan(player=P0, number=5, segments=TURN_SEQUENCE, rules=("500.1",))


def test_full_two_player_game_ends_by_decking() -> None:
    """704.5b, 121.4: 10-card decks, both players keep and always pass.

    After the opening hands each library holds 3 cards. Player 0 starts and skips their first
    draw (103.8a). Player 1 draws on turns 2, 4, 6 and player 0 on turns 3, 5, 7, emptying both
    libraries. On turn 8 player 1 attempts to draw from an empty library and loses when
    state-based actions are checked, before anyone receives priority in that draw step; player
    0 wins (104.2a). Player 0 discarded one card down to seven at the end of each of their
    three turns with eight cards (514.1); player 1's cards left the game with them (800.4a).
    """
    state = started_game(2, decks=[deck(10, 0), deck(10, 0)])
    assert [len(p.library) for p in state.players] == [3, 3]
    pass_until(state, lambda s: False)
    assert state.result is not None and state.result.winners == (P0,)
    turn = state.turn
    assert turn is not None
    assert (turn.number, turn.active_player, turn.step) == (8, P1, Step.DRAW)
    assert state.player(P1).lost and not state.player(P0).lost
    # Player 1 left the game on losing (104.5), taking every object they owned (800.4a).
    assert state.player(P1).left_game
    assert not any(obj.owner == P1 for obj in state.objects.values())
    assert (len(state.player(P0).graveyard), len(state.player(P0).library)) == (3, 0)
    assert len(state.player(P0).hand) == 7
