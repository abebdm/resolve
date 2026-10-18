"""103: starting the game (and 903.6-903.7 for Commander).

M0 implements 103.1 to 103.4. The game then stops at ``NotImplementedRule("103.5: ...")``.
"""

from __future__ import annotations

import copy

import pytest

from resolve.decisions.kinds import DecisionKind
from resolve.decisions.request import DecisionAnswer
from resolve.decisions.spaces import ChooseOne, Number, Pick, PlayerOption
from resolve.engine.api import new_game, submit
from resolve.engine.deck import Deck
from resolve.errors import InvalidAnswer
from resolve.events.game import LibraryShuffled, StartingPlayerChosen
from resolve.state.config import GameConfig
from resolve.state.game import turn_order
from resolve.state.ids import PlayerId
from resolve.state.zones import ZoneKind
from tests.game_fixtures import (
    DAYBREAKER,
    answer,
    choose_starting_player,
    deck,
    request_of,
    start,
)


@pytest.mark.parametrize("players", [2, 3, 4])
def test_103_1_a_player_chooses_who_takes_the_first_turn_among_all_players(players: int) -> None:
    state = start(players)
    request = request_of(state)
    assert request.kind is DecisionKind.CHOOSE_STARTING_PLAYER
    assert request.rules == ("103.1",)
    assert 0 <= request.player < players
    assert request.space == ChooseOne(tuple(PlayerOption(PlayerId(p)) for p in range(players)))


def test_103_1_the_chooser_is_picked_at_random_from_the_game_seed() -> None:
    """103.1 leaves the method to the players; the engine uses the game's RNG, uniformly."""
    choosers = {request_of(start(4, seed)).player for seed in range(60)}
    assert choosers == {0, 1, 2, 3}
    assert request_of(start(4, 5)).player == request_of(start(4, 5)).player


@pytest.mark.parametrize("chosen", [0, 1, 2])
def test_103_1_the_chosen_player_starts_and_turn_order_proceeds_clockwise(chosen: int) -> None:
    state = start(3)
    chooser = request_of(state).player
    choose_starting_player(state, chosen)
    assert state.starting_player == chosen
    assert turn_order(state) == tuple(PlayerId((chosen + i) % 3) for i in range(3))
    event = state.event_log[1].record
    assert event == StartingPlayerChosen(
        chooser=chooser, starting_player=PlayerId(chosen), rules=("103.1",)
    )


def test_103_1_the_chooser_may_choose_themselves_or_anyone_else() -> None:
    for index in range(2):
        state = start(2, seed=3)
        choose_starting_player(state, index)
        assert state.starting_player == index


def test_103_1_illegal_answers_are_rejected() -> None:
    state = start(3)
    request = request_of(state)
    before = copy.deepcopy(state)
    other = PlayerId((request.player + 1) % 3)
    for bad in (
        answer(state, Pick(3)),
        answer(state, Pick(-1)),
        answer(state, Number(0)),
        DecisionAnswer(request.id, other, Pick(0)),
    ):
        with pytest.raises(InvalidAnswer):
            submit(state, bad)
        assert state == before


def test_103_3_each_library_is_shuffled_in_turn_order_from_the_starting_player() -> None:
    state = start(3, seed=11)
    choose_starting_player(state, 1)
    shuffles = [e.record for e in state.event_log if isinstance(e.record, LibraryShuffled)]
    assert [event.player for event in shuffles] == [1, 2, 0]
    assert all(event.rules == ("103.3", "701.24a") for event in shuffles)


def test_103_3_each_library_becomes_a_random_permutation_of_its_deck() -> None:
    orders: set[tuple[int, ...]] = set()
    for seed in range(20):
        state = start(2, seed)
        initial = list(state.players[0].library)
        choose_starting_player(state, 0)
        library = state.players[0].library
        assert sorted(library) == sorted(initial)
        orders.add(tuple(library))
    assert len(orders) > 15, "different seeds give different orders"


def test_103_3_the_shuffle_is_determined_by_the_seed() -> None:
    first, second = start(2, seed=9), start(2, seed=9)
    choose_starting_player(first, 1)
    choose_starting_player(second, 1)
    assert first.players[0].library == second.players[0].library
    assert first == second


def test_103_3_an_empty_library_can_be_shuffled() -> None:
    state = new_game(GameConfig.standard(), [Deck(()), deck()], seed=2)
    choose_starting_player(state, 0)
    assert state.players[0].library == []


def test_103_4_each_player_starts_at_20_life() -> None:
    state = start(4)
    assert [player.life for player in state.players] == [20, 20, 20, 20]


def test_103_4c_in_commander_each_player_starts_at_40_life() -> None:
    commander_decks = [deck(commanders=[DAYBREAKER]) for _ in range(4)]
    state = new_game(GameConfig.commander_game(), commander_decks, seed=1)
    assert [player.life for player in state.players] == [40, 40, 40, 40]


def test_903_6_commanders_start_face_up_in_the_command_zone_not_the_library() -> None:
    commander_decks = [deck(3, 0, commanders=[DAYBREAKER]) for _ in range(2)]
    state = new_game(GameConfig.commander_game(), commander_decks, seed=1)
    assert len(state.command) == 2
    for obj_id, owner in zip(state.command, (0, 1), strict=True):
        obj = state.objects[obj_id]
        assert obj.owner == owner
        assert obj.zone.kind is ZoneKind.COMMAND
        assert obj.zone.kind.is_public  # face up: everyone sees it (400.2)
        assert obj.card is not None
        assert state.cards[obj.card].data.name == "Test Daybreaker // Test Nightfall"
    assert all(len(player.library) == 3 for player in state.players)


def test_103_5_opening_hands_are_not_implemented_yet_and_stop_the_game_loudly() -> None:
    state = start(2)
    gap = choose_starting_player(state, 0)
    assert gap.rule == "103.5"
    assert all(player.hand == [] for player in state.players)
    # The libraries were shuffled before the gap was reached.
    assert len([e for e in state.event_log if isinstance(e.record, LibraryShuffled)]) == 2
