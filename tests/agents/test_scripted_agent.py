"""ScriptedAgent: answers from a script, checked against what the game asks (design.md §14)."""

from __future__ import annotations

import pytest

from resolve.agents.driver import play
from resolve.agents.scripted import Choose, ScriptedAgent, ScriptError, Step, choose
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import (
    ChooseNumber,
    ChooseOne,
    ChooseOrder,
    ChooseSubset,
    Number,
    ObjectOption,
    Order,
    Pick,
    PickMany,
    PlayerOption,
)
from resolve.engine.api import new_game, view_for
from resolve.state.config import GameConfig
from resolve.state.ids import ObjectId, PlayerId
from tests.engine_support import AskTwice, markers, running
from tests.game_fixtures import decks, request_of, start

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)
OPTIONS = (PlayerOption(P0), ObjectOption(ObjectId(5)), PlayerOption(P2))


def test_steps_answer_decisions_in_order() -> None:
    state = running(AskTwice(P0))
    script = ScriptedAgent([Step(Number(2)), Step(Number(4))])
    assert play(state, script, max_answers=2) == 2
    assert markers(state) == ["got (2, 4)"]
    assert script.remaining == 0
    script.check_finished()


def test_a_step_checks_the_expected_player_and_kind() -> None:
    state = running(AskTwice(P1))
    request = request_of(state)
    view = view_for(state, P1)
    with pytest.raises(ScriptError, match="expects player 0"):
        ScriptedAgent([Step(Number(2), player=P0)]).decide(view, request)
    with pytest.raises(ScriptError, match="expects mulligan"):
        ScriptedAgent([Step(Number(2), kind=DecisionKind.MULLIGAN)]).decide(view, request)
    answer = ScriptedAgent([Step(Number(2), P1, DecisionKind.CHOOSE_X)]).decide(view, request)
    assert (answer.request_id, answer.player, answer.value) == (request.id, P1, Number(2))


def test_a_mismatched_step_is_not_used_up() -> None:
    state = running(AskTwice(P1))
    script = ScriptedAgent([Step(Number(2), player=P0)])
    with pytest.raises(ScriptError):
        script.decide(view_for(state, P1), request_of(state))
    assert script.remaining == 1


def test_running_out_of_script_is_an_error_naming_the_question() -> None:
    state = running(AskTwice(P0))
    with pytest.raises(ScriptError, match=r"ran out after 0 steps.*player 0.*choose_x"):
        play(state, ScriptedAgent([]))


def test_unused_steps_are_reported() -> None:
    script = ScriptedAgent([Step(Number(1)), Step(Number(2))])
    with pytest.raises(ScriptError, match="2 of 2 script steps were unused"):
        script.check_finished()


def test_choose_resolves_one_option_to_its_index() -> None:
    assert choose(PlayerOption(P2)).resolve(ChooseOne(OPTIONS)) == Pick(2)
    assert choose(ObjectOption(ObjectId(5))).resolve(ChooseOne(OPTIONS)) == Pick(1)


def test_choose_resolves_a_subset_to_increasing_indices() -> None:
    step = choose(PlayerOption(P2), PlayerOption(P0))
    assert step.resolve(ChooseSubset(OPTIONS, 0, 3)) == PickMany((0, 2))
    assert choose().resolve(ChooseSubset(OPTIONS, 0, 3)) == PickMany(())


def test_choose_resolves_an_order_in_the_given_order() -> None:
    step = choose(PlayerOption(P2), PlayerOption(P0), ObjectOption(ObjectId(5)))
    assert step.resolve(ChooseOrder(OPTIONS)) == Order((2, 0, 1))


@pytest.mark.parametrize(
    ("step", "space", "message"),
    [
        (choose(PlayerOption(P1)), ChooseOne(OPTIONS), "isn't offered"),
        (choose(PlayerOption(P0), PlayerOption(P2)), ChooseOne(OPTIONS), "choose one option"),
        (choose(), ChooseOne(OPTIONS), "choose one option"),
        (choose(PlayerOption(P0), PlayerOption(P0)), ChooseSubset(OPTIONS, 0, 3), "twice"),
        (choose(PlayerOption(P0)), ChooseNumber(0, 3), "can't be chosen"),
        (
            choose(PlayerOption(P0)),
            ChooseOne((PlayerOption(P0), PlayerOption(P0))),
            "more than once",
        ),
    ],
)
def test_choose_refuses_options_that_dont_fit(
    step: Choose, space: ChooseOne | ChooseSubset | ChooseNumber, message: str
) -> None:
    with pytest.raises(ScriptError, match=message):
        step.resolve(space)


def test_choose_drives_the_starting_player_decision() -> None:
    """103.1: the chooser names the player who takes the first turn."""
    state = start(3)
    chooser = request_of(state).player
    script = ScriptedAgent(
        [choose(PlayerOption(P2), player=chooser, kind=DecisionKind.CHOOSE_STARTING_PLAYER)]
    )
    assert play(state, script, max_answers=1) == 1
    assert state.starting_player == P2


def test_from_log_replays_a_game_to_the_same_state() -> None:
    """design.md §12: a game is a function of config, decks, seed and the answers."""
    state = running(AskTwice(P1), AskTwice(P0))
    play(state, ScriptedAgent([Step(Number(n)) for n in (2, 4, 6, 8)]), max_answers=4)
    replay = ScriptedAgent.from_log(state.event_log)
    assert replay.steps == [
        Step(Number(2), P1, DecisionKind.CHOOSE_X),
        Step(Number(4), P1, DecisionKind.CHOOSE_X),
        Step(Number(6), P0, DecisionKind.CHOOSE_X),
        Step(Number(8), P0, DecisionKind.CHOOSE_X),
    ]
    again = running(AskTwice(P1), AskTwice(P0))
    play(again, replay, max_answers=4)
    assert again == state


def test_from_log_replays_a_real_game_start() -> None:
    config = GameConfig.standard()
    state = new_game(config, decks(4), seed=9)
    play(state, ScriptedAgent([choose(PlayerOption(PlayerId(3)))]), max_answers=1)
    again = new_game(config, decks(4), seed=9)
    play(again, ScriptedAgent.from_log(state.event_log), max_answers=1)
    assert again == state


def test_a_choose_step_checks_the_expected_player_and_kind() -> None:
    state = start(3)
    request = request_of(state)
    view = view_for(state, request.player)
    other = PlayerId((request.player + 1) % 3)
    with pytest.raises(ScriptError, match=f"expects player {other}"):
        ScriptedAgent([choose(PlayerOption(P0), player=other)]).decide(view, request)
    with pytest.raises(ScriptError, match="expects choose_x"):
        ScriptedAgent([choose(PlayerOption(P0), kind=DecisionKind.CHOOSE_X)]).decide(view, request)


def test_a_replay_of_another_game_stops_at_the_first_mismatch() -> None:
    """design.md §12: a replay checks who is asked, so replaying against a game with another
    seed (and so, here, another chooser, 103.1) fails at once."""
    config = GameConfig.standard()
    original = new_game(config, decks(4), seed=1)
    play(original, ScriptedAgent([choose(PlayerOption(P0))]), max_answers=1)
    chooser = request_of(new_game(config, decks(4), seed=1)).player
    other_seed = next(
        seed
        for seed in range(2, 50)
        if request_of(new_game(config, decks(4), seed)).player != chooser
    )
    with pytest.raises(ScriptError, match=f"step 1 expects player {chooser}"):
        play(new_game(config, decks(4), other_seed), ScriptedAgent.from_log(original.event_log))
