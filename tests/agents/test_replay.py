"""Replays from recorded inputs: answers and concessions (design.md §12)."""

from __future__ import annotations

import pytest

from resolve.agents.replay import ReplayDiverged, inputs, replay
from resolve.decisions.request import DecisionAnswer
from resolve.decisions.spaces import Pick
from resolve.engine import concede
from resolve.engine.api import new_game, submit
from resolve.events.base import AnswerRecord
from resolve.events.game import Conceded
from resolve.state.config import GameConfig
from resolve.state.ids import PlayerId
from tests.game_fixtures import deck, request_of

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)


def test_inputs_are_the_answers_and_concessions_in_order() -> None:
    state = new_game(GameConfig.standard(), [deck(5, 0)] * 3, seed=4)
    request = request_of(state)
    submit(state, DecisionAnswer(request.id, request.player, Pick(0)))
    concede(state, P2)
    recorded = inputs(state.event_log)
    assert [type(r) for r in recorded] == [AnswerRecord, Conceded]
    again = new_game(GameConfig.standard(), [deck(5, 0)] * 3, seed=4)
    assert replay(again, state.event_log) == 2
    assert again == state


def test_a_replay_on_another_game_diverges() -> None:
    state = new_game(GameConfig.standard(), [deck(5, 0)] * 3, seed=4)
    request = request_of(state)
    submit(state, DecisionAnswer(request.id, request.player, Pick(0)))
    other = new_game(GameConfig.standard(), [deck(5, 0)] * 3, seed=7)
    assert (request.player, request_of(other).player) == (P2, P0)  # seeds 4 and 7 differ
    with pytest.raises(ReplayDiverged, match="input 1 expects player"):
        replay(other, state.event_log)


def test_a_replay_past_the_end_of_the_game_diverges() -> None:
    state = new_game(GameConfig.standard(), [deck(5, 0)] * 2, seed=4)
    request = request_of(state)
    submit(state, DecisionAnswer(request.id, request.player, Pick(0)))
    ended = new_game(GameConfig.standard(), [deck(5, 0)] * 2, seed=4)
    concede(ended, P0)
    with pytest.raises(ReplayDiverged, match="ended before input 1"):
        replay(ended, state.event_log)


def test_a_replayed_concession_by_a_player_who_already_left_diverges() -> None:
    state = new_game(GameConfig.standard(), [deck(5, 0)] * 3, seed=7)
    request = request_of(state)
    assert request.player == P0
    submit(state, DecisionAnswer(request.id, request.player, Pick(0)))
    concede(state, P2)
    other = new_game(GameConfig.standard(), [deck(5, 0)] * 3, seed=7)
    concede(other, P2)
    with pytest.raises(ReplayDiverged, match="input 2: player 2 has already left the game"):
        replay(other, state.event_log)


def test_a_replayed_concession_after_the_end_of_the_game_diverges() -> None:
    state = new_game(GameConfig.standard(), [deck(5, 0)] * 2, seed=4)
    concede(state, P0)
    ended = new_game(GameConfig.standard(), [deck(5, 0)] * 2, seed=4)
    concede(ended, P1)
    with pytest.raises(ReplayDiverged, match="the game ended before input 1"):
        replay(ended, state.event_log)
