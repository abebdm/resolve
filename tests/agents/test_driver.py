"""The driver loop ``play`` (design.md §3)."""

from __future__ import annotations

import copy

import pytest

from resolve.agents.driver import MAX_ATTEMPTS, agent_for, play
from resolve.agents.random_agent import RandomAgent
from resolve.agents.scripted import ScriptedAgent, Step
from resolve.decisions.request import DecisionAnswer, DecisionRequest
from resolve.decisions.spaces import Number
from resolve.engine.view import PlayerView
from resolve.errors import EngineError, InvalidAnswer, NotImplementedRule
from resolve.state.ids import PlayerId
from tests.engine_support import AskTwice, EndGame, holding, markers, running
from tests.game_fixtures import start

P0, P1 = PlayerId(0), PlayerId(1)


class Recorder:
    """Answers with fixed numbers and records the views and requests it was given."""

    def __init__(self, *numbers: int) -> None:
        self.numbers = list(numbers)
        self.seen: list[tuple[PlayerView, DecisionRequest]] = []

    def decide(self, view: PlayerView, request: DecisionRequest) -> DecisionAnswer:
        self.seen.append((view, request))
        return DecisionAnswer(request.id, request.player, Number(self.numbers.pop(0)))


def test_play_runs_until_the_game_is_over() -> None:
    state = running(AskTwice(P0), EndGame((P1,)))
    assert play(state, Recorder(2, 4)) == 2
    assert state.result is not None and state.result.winners == (P1,)


def test_play_stops_after_max_answers() -> None:
    state = running(AskTwice(P0), AskTwice(P1))
    assert play(state, Recorder(2, 4, 6), max_answers=3) == 3
    assert markers(state) == ["got (2, 4)"]
    assert state.pending is not None and state.pending.player == P1
    assert play(state, Recorder(), max_answers=0) == 0


def test_play_refuses_a_negative_max_answers() -> None:
    with pytest.raises(ValueError, match="max_answers"):
        play(running(AskTwice(P0)), Recorder(), max_answers=-1)


def test_each_seat_is_asked_through_its_own_agent_and_sees_its_own_view() -> None:
    """Agents only see the deciding player's view (design.md §9)."""
    state = running(AskTwice(P1), AskTwice(P0))
    zero, one = Recorder(6, 8), Recorder(2, 4)
    play(state, [zero, one], max_answers=4)
    assert [view.viewer for view, _ in one.seen] == [P1, P1]
    assert [view.viewer for view, _ in zero.seen] == [P0, P0]
    assert all(view.request == request for view, request in zero.seen + one.seen)
    assert holding(state)


def test_a_missing_agent_is_an_engine_error() -> None:
    with pytest.raises(EngineError, match="no agent for player 1"):
        agent_for([Recorder()], 1)


def test_a_rejected_answer_raises_by_default_and_changes_nothing() -> None:
    state = running(AskTwice(P0))
    before = copy.deepcopy(state)
    with pytest.raises(InvalidAnswer, match="even"):
        play(state, Recorder(3))
    assert state == before


def test_with_on_invalid_the_agent_is_asked_again() -> None:
    state = running(AskTwice(P0))
    errors: list[InvalidAnswer] = []
    agent = Recorder(3, 2, 5, 4)
    assert play(state, agent, max_answers=2, on_invalid=errors.append) == 2
    assert [str(error) for error in errors] == ["the number must be even"] * 2
    assert markers(state) == ["got (2, 4)"]
    assert len(agent.seen) == 4


def test_a_decision_that_rejects_every_answer_gives_up_after_max_attempts() -> None:
    state = running(AskTwice(P0))
    errors: list[InvalidAnswer] = []
    with pytest.raises(InvalidAnswer):
        play(state, Recorder(*[1] * MAX_ATTEMPTS), on_invalid=errors.append)
    assert len(errors) == MAX_ATTEMPTS - 1


def test_not_implemented_rules_propagate() -> None:
    """M0 games stop at 103.5 (roadmap)."""
    state = start(2)
    with pytest.raises(NotImplementedRule, match=r"^103\.5: "):
        play(state, RandomAgent(1))


def test_a_scripted_agent_shared_by_all_players() -> None:
    state = running(AskTwice(P1), AskTwice(P0))
    play(state, ScriptedAgent([Step(Number(n)) for n in (2, 4, 6, 8)]), max_answers=4)
    assert markers(state) == ["got (2, 4)", "got (6, 8)"]
