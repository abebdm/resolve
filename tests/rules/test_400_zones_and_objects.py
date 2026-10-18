"""Zones (400), objects and their owners and controllers (108, 109), timestamps (613.7d)."""

from __future__ import annotations

import copy

import pytest

from resolve.engine.api import new_game
from resolve.errors import EngineError, NotImplementedRule
from resolve.state.config import GameConfig
from resolve.state.game import create_object, move_object, zone_list
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


def test_400_3_an_object_put_into_another_players_graveyard_goes_to_its_owners() -> None:
    state = start(2)
    obj = create_object(state, card=None, owner=PlayerId(0), zone=Zone.graveyard(PlayerId(1)))
    assert obj.zone == Zone.graveyard(PlayerId(0))
    assert state.players[0].graveyard == [obj.id]
    assert state.players[1].graveyard == []


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


def test_109_4c_controlled_objects_in_the_command_zone_are_not_implemented_yet() -> None:
    """109.4c: an emblem is controlled by the player who puts it into the command zone."""
    state = start(2)
    with pytest.raises(NotImplementedRule) as gap:
        create_object(state, card=None, owner=PlayerId(0), zone=COMMAND, controller=PlayerId(0))
    assert gap.value.rule == "109.4c"


def test_400_7_an_object_that_changes_zones_becomes_a_new_object() -> None:
    state = start(2)
    old_id = state.players[1].library[-1]
    old = state.objects[old_id]
    new = move_object(state, old_id, COMMAND)
    assert new.id == ObjectId(21), "a new ID, never a reused one"
    assert old_id not in state.objects
    assert old_id not in state.players[1].library
    assert state.command == [new.id]
    assert (new.card, new.owner, new.zone, new.controller) == (old.card, 1, COMMAND, None)
    assert new.timestamp == 21, "613.7d: a new timestamp on entering the zone"
    assert new.known_to == ()
    assert invariant_violations(state) == []


def test_400_3_a_moved_object_goes_to_its_owners_hand_library_or_graveyard() -> None:
    """For example, a card its owner doesn't control put "into your hand" goes to its owner's."""
    state = start(2)
    for kind in (Zone.hand, Zone.graveyard, Zone.library):
        old_id = state.players[0].library[0]
        new = move_object(state, old_id, kind(PlayerId(1)))
        assert new.zone == kind(PlayerId(0))
        assert new.id in zone_list(state, kind(PlayerId(0)))
        assert new.id not in zone_list(state, kind(PlayerId(1)))
    assert invariant_violations(state) == []


def test_a_move_that_is_not_allowed_changes_nothing() -> None:
    state = start(2)
    obj = state.players[0].library[0]
    before = copy.deepcopy(state)
    with pytest.raises(EngineError, match="no object 999"):
        move_object(state, ObjectId(999), EXILE)
    with pytest.raises(EngineError, match="need controller"):
        move_object(state, obj, BATTLEFIELD)
    with pytest.raises(EngineError, match="have no controller"):
        move_object(state, obj, EXILE, controller=PlayerId(0))
    with pytest.raises(NotImplementedRule) as gap:
        move_object(state, obj, COMMAND, controller=PlayerId(0))
    assert gap.value.rule == "109.4c"
    assert state == before


def test_400_7_knowledge_of_the_old_object_does_not_carry_over() -> None:
    """The new object has no memory of the old one. Events that move a card players saw (a
    revealed card put back on the library, say) record that knowledge themselves (M1)."""
    state = start(2)
    old_id = state.players[0].library[0]
    state.objects[old_id].known_to = (PlayerId(0), PlayerId(1))
    new = move_object(state, old_id, Zone.hand(PlayerId(0)))
    assert new.known_to == ()


def test_109_4_an_object_leaving_the_stack_loses_its_controller() -> None:
    state = start(2)
    spell = create_object(state, card=None, owner=PlayerId(0), zone=STACK, controller=PlayerId(1))
    exiled = move_object(state, spell.id, EXILE)
    assert exiled.controller is None
    assert spell.id not in state.objects
    assert state.stack == []
    assert state.exile == [exiled.id]


def test_110_2_an_object_put_onto_the_battlefield_gets_the_given_controller() -> None:
    state = start(2)
    obj_id = state.players[0].library[0]
    permanent = move_object(state, obj_id, BATTLEFIELD, controller=PlayerId(1))
    assert (permanent.owner, permanent.controller) == (0, 1)
    assert state.battlefield == [permanent.id]


def test_400_10_an_object_put_from_the_command_zone_into_it_becomes_a_new_object() -> None:
    state = start(2)
    first = create_object(state, card=None, owner=PlayerId(1), zone=COMMAND)
    second = move_object(state, first.id, COMMAND)
    assert second.id != first.id
    assert second.timestamp > first.timestamp
    assert state.command == [second.id]
    assert first.id not in state.objects


def test_400_7_an_object_moved_to_the_bottom_of_a_pile_is_a_new_object_at_the_bottom() -> None:
    """Some moves put a card on the bottom of a library (103.5); the last element is the top."""
    state = new_game(GameConfig.standard(), [deck(2, 1), deck(2, 1)], seed=1)
    library = state.players[0].library
    top = library[-1]
    moved = move_object(state, top, Zone.library(PlayerId(0)), bottom=True)
    assert moved.id != top and top not in state.objects
    assert library[0] == moved.id and len(library) == 3
    assert invariant_violations(state) == []
