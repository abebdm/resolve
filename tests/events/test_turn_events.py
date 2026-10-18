"""The events of the turn structure, losing and discarding: what they change and refuse."""

from __future__ import annotations

import pytest

from resolve.data.types import CardType, Supertype
from resolve.effects.characteristics import Characteristics, characteristics
from resolve.errors import EngineError, NotImplementedRule
from resolve.events.cards import CardDiscarded
from resolve.events.game import PlayerLost
from resolve.events.turn import PriorityPassed, StepBegan, TurnBegan
from resolve.state.config import GameConfig
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.turn import Phase, Step, TurnState
from resolve.state.zones import Zone
from tests.scenario import Scenario

P0, P1 = PlayerId(0), PlayerId(1)


def test_500_1_turn_began_starts_the_next_turn_in_its_untap_step() -> None:
    state = Scenario(2).build()
    TurnBegan(player=P1, number=1, rules=("500.1",)).apply(state)
    turn = state.turn
    assert turn == TurnState(1, P1, Phase.BEGINNING, Step.UNTAP)
    assert turn is not None
    turn.lands_played = 1
    TurnBegan(player=P0, number=2, rules=("500.1",)).apply(state)
    assert state.turn == TurnState(2, P0)  # a new turn: nothing carries over (305.2)


@pytest.mark.parametrize("number", [0, 2, 3])
def test_turn_numbers_follow_each_other(number: int) -> None:
    state = Scenario(2).build()
    with pytest.raises(EngineError, match="can't follow turn 0"):
        TurnBegan(player=P0, number=number, rules=("500.1",)).apply(state)
    assert state.turn is None


def test_step_began_moves_the_turn_and_clears_priority() -> None:
    state = Scenario(2).build()
    state.turn = TurnState(4, P1, Phase.BEGINNING, Step.DRAW, P0, [P1], 1)
    StepBegan(phase=Phase.PRECOMBAT_MAIN, step=None, rules=("505", "500.6")).apply(state)
    assert state.turn == TurnState(4, P1, Phase.PRECOMBAT_MAIN, None, None, [], 1)


def test_step_began_needs_a_turn() -> None:
    state = Scenario(2).build()
    with pytest.raises(EngineError, match="outside a turn"):
        StepBegan(phase=Phase.ENDING, step=Step.END, rules=("513",)).apply(state)


def test_priority_passed_is_a_record_and_changes_nothing() -> None:
    scenario = Scenario(2)
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    turn = state.turn
    assert turn is not None
    before = (turn.priority, list(turn.passed))
    PriorityPassed(player=P0, rules=("117.3d",)).apply(state)
    assert (turn.priority, turn.passed) == before


def test_104_5_player_lost_marks_the_player_and_clears_their_empty_draw() -> None:
    state = Scenario(2).build()
    state.player(P1).drew_from_empty_library = True
    PlayerLost(player=P1, rules=("704.5b",)).apply(state)
    assert state.player(P1).lost and not state.player(P1).drew_from_empty_library
    assert not state.player(P0).lost
    with pytest.raises(EngineError, match="already lost"):
        PlayerLost(player=P1, rules=("704.5a",)).apply(state)


def test_701_9a_card_discarded_moves_the_card_to_its_owners_graveyard() -> None:
    scenario = Scenario(2)
    (card,) = scenario.hand(P0, ["Forest"])
    state = scenario.build()
    applied = CardDiscarded(player=P0, card=card, rules=("701.9a",)).apply(state)
    assert isinstance(applied, CardDiscarded)
    assert applied.discarded is not None and applied.discarded != card  # 400.7
    assert state.player(P0).graveyard == [applied.discarded]
    assert state.objects[applied.discarded].zone == Zone.graveyard(P0)
    assert state.player(P0).hand == []


def test_card_discarded_refuses_a_card_outside_the_hand() -> None:
    scenario = Scenario(2)
    (card,) = scenario.hand(P1, ["Forest"])
    state = scenario.build()
    with pytest.raises(EngineError, match="isn't in player 0's hand"):
        CardDiscarded(player=P0, card=card, rules=("701.9a",)).apply(state)
    with pytest.raises(EngineError, match="proposed without its outcome"):
        CardDiscarded(player=P1, card=card, discarded=ObjectId(99), rules=("701.9a",)).apply(state)
    assert state.player(P1).hand == [card]


# --- Characteristics (109.3; layers arrive in M5) ----------------------------------------------


def test_109_3_characteristics_of_a_single_faced_card_are_its_printed_ones() -> None:
    scenario = Scenario(2)
    forest, elves = scenario.hand(P0, ["Forest", "Llanowar Elves"])
    state = scenario.build()
    assert characteristics(state, forest) == Characteristics(
        "Forest", (Supertype.BASIC,), (CardType.LAND,), ("Forest",)
    )
    elves_chars = characteristics(state, elves)
    assert elves_chars.is_a(CardType.CREATURE) and not elves_chars.is_a(CardType.LAND)
    assert elves_chars.subtypes == ("Elf", "Druid")


def test_712_8a_a_double_faced_card_has_its_front_face_characteristics() -> None:
    scenario = Scenario(2)
    (dfc,) = scenario.hand(P0, ["Test Daybreaker // Test Nightfall"])
    (on_field,) = scenario.battlefield(P0, ["Test Daybreaker // Test Nightfall"])
    state = scenario.build()
    for obj in (dfc, on_field):  # 712.8d: nothing can turn it face down yet
        chars = characteristics(state, obj)
        assert chars.name == "Test Daybreaker" and chars.subtypes == ("Human",)


def test_709_4_split_card_characteristics_are_a_gap() -> None:
    scenario = Scenario(2)
    (split,) = scenario.hand(P0, ["Test Spark // Test Frost"])
    state = scenario.build()
    with pytest.raises(NotImplementedRule) as gap:
        characteristics(state, split)
    assert gap.value.rule == "109.3"


def test_109_3_a_commander_in_the_command_zone_has_its_front_face_characteristics() -> None:
    scenario = Scenario(2, config=GameConfig.commander_game())
    commander = scenario.commander(P0, "Test Daybreaker")
    state = scenario.build()
    chars = characteristics(state, commander)
    assert chars.name == "Test Daybreaker" and chars.is_a(CardType.CREATURE)
