"""Zones (400), objects and their owners and controllers (108, 109), timestamps (613.7d)."""

from __future__ import annotations

import pytest

from resolve.engine.api import new_game
from resolve.errors import EngineError
from resolve.state.config import GameConfig
from resolve.state.game import create_object, zone_list
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.invariants import invariant_violations
from resolve.state.zones import BATTLEFIELD, COMMAND, EXILE, STACK, Zone, ZoneKind
from tests.game_fixtures import DAYBREAKER, deck, start


def test_400_1_there_are_seven_zones_three_of_them_per_player() -> None:
    assert len(ZoneKind) == 7
    per_player = {kind for kind in ZoneKind if kind.is_per_player}
    assert per_player == {ZoneKind.LIBRARY, ZoneKind.HAND, ZoneKind.GRAVEYARD}


def test_400_1_per_player_zones_need_an_owner_and_shared_zones_have_none() -> None:
    assert Zone.library(PlayerId(1)).owner == 1
    with pytest.raises(ValueError, match="needs owner"):
        Zone(ZoneKind.HAND)
    with pytest.raises(ValueError, match="has no owner"):
        Zone(ZoneKind.EXILE, PlayerId(0))


def test_400_2_library_and_hand_are_hidden_and_the_rest_are_public() -> None:
    hidden = {kind for kind in ZoneKind if not kind.is_public}
    assert hidden == {ZoneKind.LIBRARY, ZoneKind.HAND}


def test_401_1_each_players_deck_becomes_their_library() -> None:
    state = start(3)
    for player in state.players:
        assert len(player.library) == 10
        for obj_id in player.library:
            obj = state.objects[obj_id]
            assert obj.zone == Zone.library(player.id)
            assert obj.owner == player.id


def test_108_3_the_owner_is_the_player_who_started_with_the_card() -> None:
    state = start(2)
    for obj in state.objects.values():
        assert obj.card is not None
        assert state.cards[obj.card].owner == obj.owner


def test_109_4_objects_outside_the_battlefield_and_stack_have_no_controller() -> None:
    state = new_game(GameConfig.commander_game(), [deck(commanders=[DAYBREAKER])] * 2, seed=1)
    assert all(obj.controller is None for obj in state.objects.values())


def test_109_4_objects_on_the_battlefield_or_stack_need_a_controller() -> None:
    state = start(2)
    for zone in (BATTLEFIELD, STACK):
        with pytest.raises(EngineError, match="need controller"):
            create_object(state, card=None, owner=PlayerId(0), zone=zone)
    obj = create_object(state, card=None, owner=PlayerId(0), zone=STACK, controller=PlayerId(1))
    assert state.stack[-1] == obj.id, "a new object goes on top of the stack (405.2)"
    with pytest.raises(EngineError, match="have no controller"):
        create_object(state, card=None, owner=PlayerId(0), zone=EXILE, controller=PlayerId(0))


def test_400_3_an_object_can_only_be_in_its_owners_library_hand_or_graveyard() -> None:
    state = start(2)
    with pytest.raises(EngineError, match="owned by player 0"):
        create_object(state, card=None, owner=PlayerId(0), zone=Zone.graveyard(PlayerId(1)))


def test_object_and_card_ids_are_unique_and_never_reused() -> None:
    """400.7: each object has its own ObjectId; each physical card its own CardId."""
    state = new_game(GameConfig.commander_game(), [deck(commanders=[DAYBREAKER])] * 3, seed=1)
    assert sorted(state.objects) == list(range(1, 34))
    assert sorted(state.cards) == list(range(1, 34))
    assert len({obj.card for obj in state.objects.values()}) == 33
    obj = create_object(state, card=None, owner=PlayerId(0), zone=EXILE)
    assert obj.id == ObjectId(34)


def test_card_ids_follow_seat_order_with_commanders_first() -> None:
    state = new_game(GameConfig.commander_game(), [deck(2, 0, commanders=[DAYBREAKER])] * 2, 1)
    names = [(card.owner, card.data.name) for card in state.cards.values()]
    assert names == [
        (0, "Test Daybreaker // Test Nightfall"),
        (0, "Forest"),
        (0, "Forest"),
        (1, "Test Daybreaker // Test Nightfall"),
        (1, "Forest"),
        (1, "Forest"),
    ]


def test_613_7d_objects_receive_increasing_timestamps_as_they_enter_zones() -> None:
    state = start(2)
    timestamps = [state.objects[obj].timestamp for obj in sorted(state.objects)]
    assert timestamps == sorted(timestamps)
    assert len(set(timestamps)) == len(timestamps)
    obj = create_object(state, card=None, owner=PlayerId(1), zone=COMMAND)
    assert obj.timestamp == max(timestamps) + 1


def test_new_objects_go_on_top_of_ordered_zones() -> None:
    """In every pile the last element is the top (404.1, 405.2)."""
    state = start(2)
    graveyard = Zone.graveyard(PlayerId(0))
    first = create_object(state, card=None, owner=PlayerId(0), zone=graveyard)
    second = create_object(state, card=None, owner=PlayerId(0), zone=graveyard)
    assert zone_list(state, graveyard) == [first.id, second.id]
    assert invariant_violations(state) == []
