"""The turn state (500.1, 117) and its invariants; turn order among players still in the game."""

from __future__ import annotations

import copy
import pickle

import pytest

from resolve.decisions.kinds import DecisionKind
from resolve.decisions.request import DecisionRequest
from resolve.decisions.spaces import ChooseOne, PassOption
from resolve.errors import EngineError
from resolve.state.game import GameState, apnap_order, next_in_turn_order, players_in_game
from resolve.state.ids import PlayerId
from resolve.state.invariants import invariant_violations, state_impurities
from resolve.state.turn import (
    TURN_SEQUENCE,
    Phase,
    Step,
    TurnState,
    gives_priority,
    segment_of,
)
from tests.scenario import Scenario

P0, P1, P2, P3 = PlayerId(0), PlayerId(1), PlayerId(2), PlayerId(3)


def test_500_1_the_turn_sequence_has_five_phases_in_order() -> None:
    phases = list(dict.fromkeys(phase for phase, _ in TURN_SEQUENCE))
    assert phases == [
        Phase.BEGINNING,
        Phase.PRECOMBAT_MAIN,
        Phase.COMBAT,
        Phase.POSTCOMBAT_MAIN,
        Phase.ENDING,
    ]
    assert [s for p, s in TURN_SEQUENCE if p is Phase.BEGINNING] == [
        Step.UNTAP,
        Step.UPKEEP,
        Step.DRAW,
    ]  # 501.1
    assert [s for p, s in TURN_SEQUENCE if p is Phase.COMBAT] == [
        Step.BEGINNING_OF_COMBAT,
        Step.DECLARE_ATTACKERS,
        Step.DECLARE_BLOCKERS,
        Step.COMBAT_DAMAGE,
        Step.END_OF_COMBAT,
    ]  # 506.1
    assert [s for p, s in TURN_SEQUENCE if p is Phase.ENDING] == [Step.END, Step.CLEANUP]
    assert [s for p, s in TURN_SEQUENCE if p in (Phase.PRECOMBAT_MAIN, Phase.POSTCOMBAT_MAIN)] == [
        None,
        None,
    ]  # 505.2: a main phase has no steps


def test_segment_of_names_a_step_or_a_main_phase() -> None:
    assert segment_of(Step.DRAW) == (Phase.BEGINNING, Step.DRAW)
    assert segment_of(Phase.POSTCOMBAT_MAIN) == (Phase.POSTCOMBAT_MAIN, None)
    with pytest.raises(ValueError, match="has steps"):
        segment_of(Phase.COMBAT)


def test_117_3a_502_4_514_3_which_steps_give_priority() -> None:
    assert not gives_priority(Step.UNTAP)
    assert not gives_priority(Step.CLEANUP)
    assert gives_priority(None)
    assert all(gives_priority(step) for _, step in TURN_SEQUENCE[1:-1])


def test_a_turn_state_survives_copy_and_pickle() -> None:
    turn = TurnState(3, P1, Phase.COMBAT, Step.END_OF_COMBAT, P2, [P1], 1)
    assert copy.deepcopy(turn) == turn
    assert pickle.loads(pickle.dumps(turn)) == turn


def test_players_in_game_and_next_in_turn_order_skip_players_who_lost() -> None:
    state = Scenario(4, starting_player=2).build()
    assert players_in_game(state) == (P2, P3, P0, P1)
    assert next_in_turn_order(state, P3) == P0
    state.player(P0).lost = True
    assert players_in_game(state) == (P2, P3, P1)
    assert next_in_turn_order(state, P3) == P1
    assert next_in_turn_order(state, P0) == P1  # from a player who left, too
    for player in (P1, P2, P3):
        state.player(player).lost = True
    with pytest.raises(EngineError, match="still in the game"):
        next_in_turn_order(state, P0)


def at_upkeep() -> GameState:
    scenario = Scenario(3)
    scenario.at(Step.UPKEEP, active=P1, number=2)
    return scenario.build()


def test_a_game_paused_at_priority_is_consistent() -> None:
    state = at_upkeep()
    assert invariant_violations(state) == []
    assert state_impurities(state) == []


@pytest.mark.parametrize(
    ("field", "value", "problem"),
    [
        ("number", 0, "turn number 0 isn't positive"),
        ("active_player", PlayerId(7), "active player 7 isn't a player"),
        ("step", Step.END, "isn't a step of a turn"),
        ("phase", Phase.COMBAT, "isn't a step of a turn"),
        ("priority", PlayerId(5), "priority holder 5 isn't a player"),
        ("passed", [P2, P2], "aren't distinct players"),
        ("passed", [PlayerId(4)], "aren't distinct players"),
        ("passed", [P1], "already passed"),
        ("lands_played", -1, "lands played this turn is negative"),
        ("priority", P2, "holds priority"),
    ],
)
def test_turn_invariants_catch_bad_bookkeeping(field: str, value: object, problem: str) -> None:
    state = at_upkeep()
    assert state.turn is not None
    setattr(state.turn, field, value)
    problems = invariant_violations(state)
    assert any(problem in p for p in problems), problems


def test_a_priority_holder_who_left_the_game_is_caught() -> None:
    state = at_upkeep()
    state.player(P1).lost = True
    assert any("has left the game" in p for p in invariant_violations(state))


def test_priority_asked_outside_a_turn_or_in_the_untap_step_is_caught() -> None:
    state = at_upkeep()
    turn = state.turn
    assert turn is not None
    turn.step = Step.UNTAP
    assert any("502.4" in p for p in invariant_violations(state))
    state.turn = None
    assert "priority is asked outside a turn" in invariant_violations(state)


def test_a_turn_without_a_starting_player_is_caught() -> None:
    state = Scenario(2, starting_player=None).build()
    state.turn = TurnState(1, P0)
    assert any("no starting player" in p for p in invariant_violations(state))


def test_the_check_reads_the_pending_request() -> None:
    state = at_upkeep()
    assert state.pending is not None
    state.pending = DecisionRequest(
        state.pending.id,
        P0,
        DecisionKind.PRIORITY_ACTION,
        ChooseOne((PassOption(),)),
        "?",
        ("117.1",),
    )
    assert any("is asked for a priority action" in p for p in invariant_violations(state))


def test_101_4_apnap_order_starts_with_the_active_player() -> None:
    scenario = Scenario(4, starting_player=1)
    state = scenario.build()
    assert apnap_order(state) == (P1, P2, P3, P0)  # 101.4e: before the first turn
    state.turn = TurnState(3, P3)
    assert apnap_order(state) == (P3, P0, P1, P2)
    state.player(P0).lost = True
    assert apnap_order(state) == (P3, P1, P2)
    state.player(P3).lost = True  # 800.4j: the turn goes on without its active player
    assert apnap_order(state) == (P1, P2)
