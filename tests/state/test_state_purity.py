"""The game state is pure data: deepcopy and pickle round-trips, determinism, invariants.

CLAUDE.md rules 5 and 6 and design.md §4, §12. The fuzz harness (later in M0) will run these
checks after every decision of random games; here they run at each kind of pause point.
"""

from __future__ import annotations

import copy
import pickle
import random
from collections.abc import Callable

import pytest

from resolve.decisions.spaces import Number
from resolve.engine.api import submit
from resolve.errors import EngineError
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.invariants import (
    check_invariants,
    check_pure_data,
    invariant_violations,
    state_impurities,
)
from resolve.state.zones import EXILE, Zone
from tests.engine_support import (
    AskTwice,
    HoldsValue,
    LooseTask,
    Parent,
    a_function,
    holds_object,
    running,
)
from tests.game_fixtures import answer, choose_starting_player, start


def paused_states() -> dict[str, GameState]:
    """States paused at each kind of point the engine can pause at."""
    mid_task = running(AskTwice(PlayerId(1)), Parent())
    submit(mid_task, answer(mid_task, Number(2)))  # AskTwice has received one of two answers
    after_gap = start(3, seed=4)
    choose_starting_player(after_gap, 2)
    return {
        "new game": start(3, seed=4),
        "middle of a multi-step task": mid_task,
        "stopped at the 103.5 gap": after_gap,
    }


STATES = paused_states()


@pytest.mark.parametrize("name", STATES)
def test_states_are_pure_data_and_consistent(name: str) -> None:
    state = STATES[name]
    assert state_impurities(state) == []
    assert invariant_violations(state) == []
    check_pure_data(state)
    check_invariants(state)


@pytest.mark.parametrize("name", STATES)
def test_states_survive_deepcopy_and_pickle(name: str) -> None:
    state = STATES[name]
    assert copy.deepcopy(state) == state
    assert pickle.loads(pickle.dumps(state)) == state
    assert pickle.loads(pickle.dumps(copy.deepcopy(state))) == state


def pickled(state: GameState) -> GameState:
    return pickle.loads(pickle.dumps(state))


@pytest.mark.parametrize("clone", [copy.deepcopy, pickled])
def test_a_copy_paused_mid_task_resumes_exactly_like_the_original(
    clone: Callable[[GameState], GameState],
) -> None:
    original = running(AskTwice(PlayerId(1)), Parent())
    submit(original, answer(original, Number(2)))
    copied = clone(original)
    for state in (original, copied):
        submit(state, answer(state, Number(4)))
    assert copied == original
    assert copied.event_log[-1] == original.event_log[-1]


def test_copies_are_independent() -> None:
    original = running(AskTwice(PlayerId(1)))
    before = copy.deepcopy(original)
    copied = copy.deepcopy(original)
    submit(copied, answer(copied, Number(8)))
    copied.players[0].life = 3
    copied.objects[ObjectId(1)].known_to = (PlayerId(0),)
    assert original == before
    submit(original, answer(original, Number(0)))  # the original still takes its own answers
    assert original != copied


def test_the_same_seed_and_answers_give_the_identical_game() -> None:
    """design.md §12: a game is a pure function of config, decks, seed and answers."""
    games = [start(4, seed=123) for _ in range(2)]
    for state in games:
        choose_starting_player(state, 3)
    assert games[0] == games[1]
    assert games[0].event_log == games[1].event_log


def test_the_game_does_not_depend_on_pythons_global_random_state() -> None:
    random.seed(1)
    first = start(3, seed=5)
    random.seed(2)
    second = start(3, seed=5)
    choose_starting_player(first, 0)
    choose_starting_player(second, 0)
    assert first == second


def test_different_seeds_give_different_games() -> None:
    games = [start(2, seed=seed) for seed in (1, 2)]
    for state in games:
        choose_starting_player(state, 0)
    assert games[0].players[0].library != games[1].players[0].library


# --- The purity checker catches what isn't pure data -------------------------------------------


@pytest.mark.parametrize(
    ("value", "found"),
    [
        (a_function(), "function isn't pure data"),
        ({1, 2}, "set isn't pure data"),
        (frozenset({1}), "frozenset isn't pure data"),
        ((x for x in range(2)), "generator isn't pure data"),
        (random.Random(1), "Random isn't pure data"),
        (int, "type isn't pure data"),
        ({(1, 2): 3}, "dict key (1, 2)"),
        ([1, [2, {"a": print}]], "builtin_function_or_method isn't pure data"),
    ],
)
def test_impure_values_in_the_state_are_reported(value: object, found: str) -> None:
    state = running(AskTwice(PlayerId(0)), HoldsValue(value))  # HoldsValue waits beneath
    problems = state_impurities(state)
    assert problems, value
    assert found in problems[0]
    assert problems[0].startswith("state.tasks[1].value")
    with pytest.raises(EngineError, match="isn't pure data"):
        check_pure_data(state)


def test_objects_and_players_held_by_reference_are_reported() -> None:
    state = start(2)
    state.tasks.append(HoldsValue(holds_object(state)))
    state.tasks.append(HoldsValue([state.players[1]]))
    problems = state_impurities(state)
    assert "state.tasks[1].value: holds a GameObject by reference" in problems[0]
    assert "state.tasks[2].value[0]: holds a Player by reference" in problems[1]


def test_attributes_outside_the_dataclass_fields_are_reported() -> None:
    state = start(2)
    task = LooseTask()
    task.callback = a_function()  # pyright: ignore[reportAttributeAccessIssue]
    state.tasks.append(task)
    problems = state_impurities(state)
    assert any("attributes outside the dataclass fields: ['callback']" in p for p in problems)


# --- The invariant checker catches broken bookkeeping ------------------------------------------


def test_an_object_in_two_zones_is_reported() -> None:
    state = start(2)
    state.exile.append(state.players[0].library[0])
    assert any(
        "is listed in the library of player 0 and the exile" in p
        for p in invariant_violations(state)
    )


def test_an_object_listed_in_no_zone_or_the_wrong_zone_is_reported() -> None:
    state = start(2)
    obj = state.players[0].library.pop()
    assert f"object {obj} isn't listed in any zone" in invariant_violations(state)
    state.exile.append(obj)
    assert any("says library of player 0" in p for p in invariant_violations(state))


def test_a_missing_object_or_bad_controller_or_foreign_zone_is_reported() -> None:
    state = start(2)
    state.exile.append(ObjectId(999))
    first = state.objects[state.players[0].library[0]]
    first.controller = PlayerId(0)
    second = state.objects[state.players[0].library[1]]
    state.players[0].library.remove(second.id)
    state.players[1].library.append(second.id)
    second.zone = Zone.library(PlayerId(1))
    problems = invariant_violations(state)
    assert "the exile lists object 999, which doesn't exist" in problems
    assert any("controller 0 in the library of player 0" in p for p in problems)
    assert any("not its owner's (400.3)" in p for p in problems)


def test_counters_and_decision_state_are_checked() -> None:
    state = start(2)
    state.next_object_id = 2
    state.next_request_id = 1
    state.objects[ObjectId(1)].known_to = (PlayerId(1), PlayerId(0))
    problems = invariant_violations(state)
    assert any("id isn't below next_object_id" in p for p in problems)
    assert "the pending request's id isn't below next_request_id" in problems
    assert "object 1: known_to isn't sorted and unique" in problems
    state.tasks.clear()
    assert "a decision is pending but the task stack is empty" in invariant_violations(state)


def test_a_consistent_state_with_an_exiled_object_passes() -> None:
    state = start(2)
    obj = state.objects[state.players[0].library.pop()]
    obj.zone = EXILE
    state.exile.append(obj.id)
    assert invariant_violations(state) == []
