"""The public API: new_game, pending_decision, view_for, submit (design.md §3, §9)."""

from __future__ import annotations

import pytest

from resolve.decisions.kinds import DecisionKind
from resolve.decisions.request import DecisionAnswer
from resolve.decisions.spaces import Number, Pick
from resolve.engine.api import new_game, pending_decision, submit, view_for
from resolve.engine.deck import Deck
from resolve.engine.view import WaitingFor
from resolve.errors import DeckError, EngineError, NotImplementedRule
from resolve.events.base import append_log
from resolve.state.config import GameConfig
from resolve.state.ids import PlayerId
from resolve.state.zones import Zone
from tests.engine_support import AskTwice, GapOnAnswer, Marker, running
from tests.game_fixtures import (
    DAYBREAKER,
    answer,
    choose_starting_player,
    deck,
    decks,
    request_of,
    start,
)


def test_new_game_runs_to_the_first_decision() -> None:
    state = start(2)
    request = pending_decision(state)
    assert request is not None
    assert request.id == 1
    assert state.pending is request


@pytest.mark.parametrize("count", [0, 1])
def test_new_game_needs_at_least_two_players(count: int) -> None:
    """100.1: the rules apply to games with two or more players."""
    with pytest.raises(DeckError, match="at least two players"):
        new_game(GameConfig.standard(), decks(count), seed=1)


def test_new_game_refuses_commanders_without_the_commander_rules() -> None:
    with pytest.raises(DeckError, match="no Commander rules"):
        new_game(GameConfig.standard(), [deck(commanders=[DAYBREAKER]), deck()], seed=1)


@pytest.mark.parametrize("seed", [-1, 2**64])
def test_new_game_refuses_seeds_out_of_range(seed: int) -> None:
    with pytest.raises(ValueError, match="seed"):
        new_game(GameConfig.standard(), decks(2), seed)


def test_new_game_accepts_the_largest_seed_and_empty_decks() -> None:
    state = new_game(GameConfig.standard(), [Deck(()), Deck(())], seed=2**64 - 1)
    assert pending_decision(state) is not None
    assert state.objects == {}


def test_view_shows_libraries_only_as_counts() -> None:
    """Library IDs survive shuffles (400.7), so views never show them (design.md §9)."""
    state = start(2)
    view = view_for(state, PlayerId(0))
    assert [summary.library_size for summary in view.players] == [10, 10]
    assert not hasattr(view.players[0], "library")


def test_view_shows_hands_to_their_owner_only() -> None:
    """402.3: a player may look at their own hand and count other players' hands."""
    state = running(AskTwice(PlayerId(0)))
    for player in state.players:
        obj_id = player.library.pop()
        obj = state.objects[obj_id]
        obj.zone = Zone.hand(player.id)
        player.hand.append(obj_id)
    view = view_for(state, PlayerId(0))
    own, other = view.players[0].hand, view.players[1].hand
    assert own[0].name == "Llanowar Elves"
    assert len(other) == 1
    assert other[0].name is None
    assert other[0].id == state.players[1].hand[0], "placeholders keep stable IDs"


def test_view_shows_public_zones_to_everyone() -> None:
    commander_decks = [deck(commanders=[DAYBREAKER]) for _ in range(2)]
    state = new_game(GameConfig.commander_game(), commander_decks, seed=1)
    choose_starting_player(state, 0)  # commanders enter the command zone after 103.1 (103.2c)
    for viewer in (PlayerId(0), PlayerId(1)):
        names = [obj.name for obj in view_for(state, viewer).command]
        assert names == ["Test Daybreaker // Test Nightfall"] * 2


def test_view_gives_the_request_only_to_the_deciding_player() -> None:
    state = running(AskTwice(PlayerId(1)))
    decider, other = view_for(state, PlayerId(1)), view_for(state, PlayerId(0))
    assert decider.request is state.pending
    assert other.request is None
    for view in (decider, other):
        assert view.waiting_for is not None
        assert view.waiting_for.player == 1
        assert view.waiting_for.kind is DecisionKind.CHOOSE_X


def test_view_filters_the_log_by_visibility() -> None:
    state = running(AskTwice(PlayerId(1)))
    submit(state, answer(state, Number(2)))  # the answer is logged for player 1 only
    append_log(state, Marker(label="public", rules=("117.1",)), None)
    append_log(state, Marker(label="secret", rules=("117.1",)), (PlayerId(0),))
    seen_by_0 = [entry.index for entry in view_for(state, PlayerId(0)).log]
    seen_by_1 = [entry.index for entry in view_for(state, PlayerId(1)).log]
    assert seen_by_0 == [1, 2]
    assert seen_by_1 == [0, 1]


def test_a_view_is_a_snapshot_unaffected_by_later_changes() -> None:
    state = start(2)
    view = view_for(state, PlayerId(0))
    state.players[0].life = 7
    state.players[0].library.clear()
    assert view.players[0].life == 20
    assert view.players[0].library_size == 10


def test_view_for_an_unknown_player_is_an_error() -> None:
    with pytest.raises(EngineError, match="no player 2"):
        view_for(start(2), PlayerId(2))


def test_after_a_rules_gap_the_state_is_not_waiting_for_anything() -> None:
    state = running(GapOnAnswer("601.2"))
    with pytest.raises(NotImplementedRule, match=r"^601\.2: "):
        submit(state, answer(state, Number(0)))
    with pytest.raises(EngineError, match="isn't waiting"):
        pending_decision(state)
    with pytest.raises(EngineError):
        submit(state, DecisionAnswer(1, PlayerId(0), Pick(0)))


def test_views_during_and_after_the_103_1_choice() -> None:
    """Only the chooser gets the request and sees their answer; the outcome is public."""
    state = start(3, seed=2)
    chooser = request_of(state).player
    others = [PlayerId(p) for p in range(3) if p != chooser]
    assert view_for(state, chooser).request is state.pending
    for other in others:
        view = view_for(state, other)
        assert view.request is None
        assert view.waiting_for == WaitingFor(chooser, DecisionKind.CHOOSE_STARTING_PLAYER)
    choose_starting_player(state, 1)
    # Then the opening hands are drawn (103.5): 21 draws, the starting player's first.
    public = [type(e.record).__name__ for e in view_for(state, others[0]).log]
    assert public == ["StartingPlayerChosen"] + ["LibraryShuffled"] * 3 + ["CardDrawn"] * 21
    own = [type(e.record).__name__ for e in view_for(state, chooser).log]
    assert (
        own
        == ["AnswerRecord", "StartingPlayerChosen"] + ["LibraryShuffled"] * 3 + ["CardDrawn"] * 21
    )
    assert all(view_for(state, PlayerId(p)).starting_player == 1 for p in range(3))
