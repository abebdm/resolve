"""103: starting the game (and 903.6-903.7 for Commander).

Opening hands and mulligans (103.5) are in ``test_103_5_mulligans.py``. Tests here that look at
the libraries right after the 103.3 shuffle use a starting hand size of 0 (``NO_HANDS``), so no
card is drawn before they look.
"""

from __future__ import annotations

import copy

import pytest

from resolve.decisions.kinds import DecisionKind
from resolve.decisions.request import DecisionAnswer
from resolve.decisions.spaces import ChooseOne, Number, Pick, PlayerOption
from resolve.engine.api import new_game, submit, view_for
from resolve.engine.deck import Deck
from resolve.errors import InvalidAnswer
from resolve.events.game import (
    CommanderPutIntoCommandZone,
    LibraryShuffled,
    StartingPlayerChosen,
)
from resolve.state.config import CommanderRules, GameConfig
from resolve.state.game import GameState, turn_order
from resolve.state.ids import CardId, ObjectId, PlayerId
from resolve.state.invariants import invariant_violations
from tests.game_fixtures import (
    DAYBREAKER,
    answer,
    choose_starting_player,
    deck,
    decks,
    request_of,
    start,
)

NO_HANDS = GameConfig(starting_hand_size=0)


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


def test_103_3_no_library_is_shuffled_before_the_starting_player_is_chosen() -> None:
    state = start(3)
    for player in state.players:
        assert player.library == sorted(player.library), "still in deck order"
    assert not any(isinstance(entry.record, LibraryShuffled) for entry in state.event_log)


def test_103_3_every_players_library_is_shuffled() -> None:
    orders: dict[int, set[tuple[int, ...]]] = {0: set(), 1: set(), 2: set()}
    for seed in range(20):
        state = start(3, seed, NO_HANDS)
        initial = [list(player.library) for player in state.players]
        choose_starting_player(state, seed % 3)
        for player in state.players:
            assert sorted(player.library) == sorted(initial[player.id])
            orders[player.id].add(tuple(player.library))
    assert all(len(seen) > 15 for seen in orders.values()), "each library's order varies"


def test_103_3_each_library_becomes_a_random_permutation_of_its_deck() -> None:
    orders: set[tuple[int, ...]] = set()
    for seed in range(20):
        state = start(2, seed, NO_HANDS)
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


def test_103_4_starting_life_comes_from_the_config() -> None:
    """103.4: some variants set other starting life totals (103.4b-e)."""
    state = new_game(GameConfig(starting_life=30), decks(3), seed=1)
    assert [player.life for player in state.players] == [30, 30, 30]


def test_103_4c_in_commander_each_player_starts_at_40_life() -> None:
    commander_decks = [deck(commanders=[DAYBREAKER]) for _ in range(4)]
    state = new_game(GameConfig.commander_game(), commander_decks, seed=1)
    assert [player.life for player in state.players] == [40, 40, 40, 40]
    choose_starting_player(state, 0)
    assert [player.life for player in state.players] == [40, 40, 40, 40], "903.7, after 103.1"


def test_903_3_a_commander_game_with_a_deck_without_commander_is_not_refused_until_m7() -> None:
    """903.3 (each deck has a commander) is deck validation, deferred to M7 (decisions.md)."""
    decks_ = [deck(3, 0, commanders=[DAYBREAKER]), deck(3, 0)]
    state = new_game(GameConfig.commander_game(), decks_, seed=1)
    choose_starting_player(state, 1)
    assert [state.objects[obj].owner for obj in state.command] == [0]
    assert state.players[1].commanders == ()


COMMANDER_NAME = "Test Daybreaker // Test Nightfall"


def commander_game(players: int = 3, seed: int = 1, *, hand_size: int = 7) -> GameState:
    """A Commander game whose decks are three Forests and Test Daybreaker as commander."""
    commander_decks = [deck(3, 0, commanders=[DAYBREAKER]) for _ in range(players)]
    config = GameConfig(starting_life=40, starting_hand_size=hand_size, commander=CommanderRules())
    return new_game(config, commander_decks, seed)


def name_of(state: GameState, obj_id: ObjectId) -> str:
    card = state.objects[obj_id].card
    assert card is not None
    return state.cards[card].data.name


def test_103_2c_commanders_stay_in_their_decks_until_the_starting_player_is_chosen() -> None:
    """103.2: the additional steps, including 103.2c, come after the starting player is chosen.

    Before 103.3 a player's deck is represented by their library, in deck order (hidden, 400.2),
    so the player choosing who goes first doesn't see the other players' commanders.
    """
    state = commander_game()
    assert state.command == []
    for player in state.players:
        names = sorted(name_of(state, obj) for obj in player.library)
        assert names == ["Forest", "Forest", "Forest", COMMANDER_NAME]
    for viewer in range(3):
        assert view_for(state, PlayerId(viewer)).command == ()


def test_903_6_after_the_choice_each_commander_is_put_face_up_into_the_command_zone() -> None:
    state = commander_game()
    library_ids = {
        obj: player.id
        for player in state.players
        for obj in player.library
        if name_of(state, obj) == COMMANDER_NAME
    }
    library_cards: dict[ObjectId, CardId] = {}
    for obj in library_ids:
        card = state.objects[obj].card
        assert card is not None
        library_cards[obj] = card
    library_ids_by_owner = {owner: obj for obj, owner in library_ids.items()}
    choose_starting_player(state, 1)
    assert [state.objects[obj].owner for obj in state.command] == [1, 2, 0]
    for obj_id in state.command:
        obj = state.objects[obj_id]
        assert name_of(state, obj_id) == COMMANDER_NAME
        assert obj.controller is None
        assert obj.zone.kind.is_public  # face up: every player sees it (400.2)
    for viewer in range(3):
        assert [o.name for o in view_for(state, PlayerId(viewer)).command] == [COMMANDER_NAME] * 3
    # 400.7: a commander that changes zones is a new object.
    for old_id in library_ids:
        assert old_id not in state.objects
        assert old_id not in state.command
    # 903.3: it is still the same physical card, and still that player's commander.
    for obj_id in state.command:
        obj = state.objects[obj_id]
        assert obj.card is not None
        assert obj.card == library_cards[library_ids_by_owner[obj.owner]]
        assert state.players[obj.owner].commanders == (obj.card,)
        assert state.cards[obj.card].owner == obj.owner
    # 903.6: the commanders are face up, so every player sees them enter in the log.
    for viewer in range(3):
        log = view_for(state, PlayerId(viewer)).log
        moved = [e.record for e in log if isinstance(e.record, CommanderPutIntoCommandZone)]
        assert [event.player for event in moved] == [1, 2, 0]
    assert invariant_violations(state) == []


def test_903_6_the_remaining_cards_are_shuffled_and_no_commander_is_left_in_a_library() -> None:
    state = commander_game(hand_size=0)
    choose_starting_player(state, 0)
    for player in state.players:
        assert len(player.library) == 3
        assert all(name_of(state, obj) == "Forest" for obj in player.library)
    kinds = [type(entry.record).__name__ for entry in state.event_log[1:]]
    assert (
        kinds
        == ["StartingPlayerChosen"] + ["CommanderPutIntoCommandZone"] * 3 + ["LibraryShuffled"] * 3
    ), "103.2c comes after 103.1 and before the 103.3 shuffle"


def test_613_7m_commanders_entering_together_get_timestamps_in_apnap_order() -> None:
    """101.4e: while starting the game the starting player counts as the active player."""
    state = commander_game()
    setup_max = max(obj.timestamp for obj in state.objects.values())
    choose_starting_player(state, 2)
    owners_by_timestamp = sorted(state.command, key=lambda obj: state.objects[obj].timestamp)
    assert [state.objects[obj].owner for obj in owners_by_timestamp] == [2, 0, 1]
    assert all(state.objects[obj].timestamp > setup_max for obj in state.command)


def test_613_7m_a_player_with_two_commanders_chooses_their_order_which_is_not_implemented() -> None:
    """Partner commanders entering together: their controller-less owner orders them (613.7m)."""
    decks_ = [deck(3, 0, commanders=[DAYBREAKER, DAYBREAKER]), deck(3, 0, commanders=[DAYBREAKER])]
    state = new_game(GameConfig.commander_game(), decks_, seed=1)
    gap = choose_starting_player(state, 0)
    assert gap is not None and gap.rule == "613.7m"
