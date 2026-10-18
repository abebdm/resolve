"""The task loop: Done / Push / NeedDecision, pausing and resuming (design.md §5)."""

from __future__ import annotations

import copy

import pytest

from resolve.decisions.request import DecisionAnswer
from resolve.decisions.spaces import Number, Pick
from resolve.engine import loop
from resolve.engine.api import pending_decision, submit
from resolve.errors import EngineError, InvalidAnswer
from resolve.state.ids import PlayerId
from tests.engine_support import (
    AskNobody,
    AskTwice,
    EndGame,
    Forever,
    Mark,
    Meddler,
    Parent,
    holding,
    markers,
    running,
)
from tests.game_fixtures import answer, request_of


def test_done_pops_and_push_runs_tasks_in_order() -> None:
    """Push((a, b, c)) runs a, then b, then c."""
    state = running(Mark("a"), Mark("b"), Mark("c"))
    assert markers(state) == ["a", "b", "c"]
    assert holding(state)


def test_a_task_continues_after_its_children_by_pushing_itself_last() -> None:
    state = running(Parent(), Mark("after"))
    assert markers(state) == ["child a", "child b", "parent continued", "after"]


def test_need_decision_pauses_with_the_task_still_on_top() -> None:
    state = running(AskTwice(PlayerId(1)), Mark("after"))
    request = request_of(state)
    assert request.player == 1
    assert request.rules == ("107.3a",)
    assert isinstance(state.tasks[-1], AskTwice)
    assert markers(state) == []


def test_resume_receives_each_answer_and_tasks_can_ask_several_times() -> None:
    state = running(AskTwice(PlayerId(1)), Mark("after"))
    first = request_of(state)
    submit(state, answer(state, Number(4)))
    second = request_of(state)
    assert second.id == first.id + 1, "each request gets a new id"
    submit(state, answer(state, Number(6)))
    assert markers(state) == ["got (4, 6)", "after"]
    assert holding(state)


def test_check_answer_rejection_leaves_the_state_unchanged() -> None:
    """Rules legality beyond the answer space is the task's check (the space allows 3)."""
    state = running(AskTwice(PlayerId(0)))
    before = copy.deepcopy(state)
    with pytest.raises(InvalidAnswer, match="even"):
        submit(state, answer(state, Number(3)))
    assert state == before
    submit(state, answer(state, Number(2)))  # the same decision can still be answered
    assert len(state.tasks[-1].received) == 1  # type: ignore[attr-defined]


def test_space_rejection_leaves_the_state_unchanged() -> None:
    state = running(AskTwice(PlayerId(0)))
    before = copy.deepcopy(state)
    for bad in (Number(12), Number(-2), Pick(0)):
        with pytest.raises(InvalidAnswer):
            submit(state, answer(state, bad))
        assert state == before


def test_answers_for_another_request_or_from_another_player_are_rejected() -> None:
    state = running(AskTwice(PlayerId(0)))
    request = request_of(state)
    before = copy.deepcopy(state)
    with pytest.raises(InvalidAnswer, match="request"):
        submit(state, DecisionAnswer(request.id + 1, request.player, Number(2)))
    with pytest.raises(InvalidAnswer, match="player"):
        submit(state, DecisionAnswer(request.id, PlayerId(1), Number(2)))
    assert state == before


def test_the_answer_is_logged_for_the_deciding_player_only() -> None:
    state = running(AskTwice(PlayerId(1)))
    submit(state, answer(state, Number(2)))
    entry = state.event_log[0]
    assert entry.visible_to == (1,)
    assert entry.rules == ("107.3a",)


def test_the_loop_stops_when_the_game_ends() -> None:
    """104.1: the game ends immediately; pending_decision then returns None."""
    state = running(EndGame((PlayerId(1),)), Mark("never"))
    assert state.result is not None
    assert state.result.winners == (1,)
    assert pending_decision(state) is None
    assert markers(state) == []
    with pytest.raises(InvalidAnswer, match="over"):
        submit(state, DecisionAnswer(1, PlayerId(0), Number(0)))


def test_an_empty_task_stack_during_a_game_is_an_engine_error() -> None:
    state = running(Mark("a"))
    state.pending = None
    state.tasks.clear()
    with pytest.raises(EngineError, match="empty"):
        loop.run(state)


def test_a_task_that_changes_the_task_stack_itself_is_an_engine_error() -> None:
    with pytest.raises(EngineError, match="Meddler changed the task stack"):
        running(Meddler())


def test_the_runaway_guard_stops_a_task_that_never_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """This guards against engine bugs; game loops are 104.4b (M7)."""
    monkeypatch.setattr(loop, "MAX_TASKS_PER_RUN", 50)
    with pytest.raises(EngineError, match="more than 50 tasks"):
        running(Forever())


def test_asking_a_player_who_does_not_exist_is_an_engine_error() -> None:
    with pytest.raises(EngineError, match="no player 99"):
        running(AskNobody())


def test_run_refuses_while_a_decision_is_pending() -> None:
    state = running(AskTwice(PlayerId(0)))
    with pytest.raises(EngineError, match="pending"):
        loop.run(state)


def test_submit_on_a_stopped_engine_is_an_engine_error() -> None:
    """After NotImplementedRule or EngineError the state isn't waiting for anything."""
    state = running(AskTwice(PlayerId(0)))
    state.pending = None
    with pytest.raises(EngineError, match="no decision is pending"):
        submit(state, DecisionAnswer(1, PlayerId(0), Number(2)))
    with pytest.raises(EngineError):
        pending_decision(state)


def test_a_task_that_asks_for_no_decisions_cannot_be_resumed() -> None:
    state = running(AskTwice(PlayerId(0)))
    request = request_of(state)
    with pytest.raises(EngineError, match="doesn't ask for decisions"):
        Mark("x").resume(state, request, Number(2))
