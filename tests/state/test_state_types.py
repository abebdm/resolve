"""GameConfig, game results and the GameState accessors (design.md §4, §10)."""

from __future__ import annotations

import pytest

from resolve.errors import EngineError
from resolve.state.config import CommanderRules, GameConfig
from resolve.state.game import GameResult, turn_order
from resolve.state.ids import ObjectId, PlayerId
from tests.game_fixtures import start


def test_103_4_and_103_5_the_standard_game_has_20_life_and_seven_card_hands() -> None:
    config = GameConfig.standard()
    assert (config.starting_life, config.starting_hand_size, config.commander) == (20, 7, None)


def test_103_4c_and_903_10a_the_commander_game_has_40_life_and_a_21_damage_threshold() -> None:
    config = GameConfig.commander_game()
    assert config.starting_life == 40
    assert config.commander == CommanderRules(damage_threshold=21)


@pytest.mark.parametrize(("life", "hand"), [(0, 7), (-5, 7), (20, -1)])
def test_impossible_configs_are_refused(life: int, hand: int) -> None:
    with pytest.raises(ValueError, match="starting"):
        GameConfig(starting_life=life, starting_hand_size=hand)


def test_a_zero_card_starting_hand_and_a_one_damage_threshold_are_allowed() -> None:
    assert GameConfig(starting_hand_size=0).starting_hand_size == 0
    assert CommanderRules(1).damage_threshold == 1
    with pytest.raises(ValueError, match="damage_threshold"):
        CommanderRules(0)


def test_104_4a_a_result_without_winners_is_a_draw() -> None:
    assert GameResult(()).is_draw
    assert not GameResult((PlayerId(0),)).is_draw


def test_turn_order_is_undefined_before_the_starting_player_is_chosen() -> None:
    with pytest.raises(EngineError, match=r"\(103\.1\)"):
        turn_order(start(2))


def test_state_accessors_refuse_unknown_ids() -> None:
    state = start(2)
    assert state.player(PlayerId(1)).id == 1
    with pytest.raises(EngineError, match="no player -1"):
        state.player(PlayerId(-1))
    with pytest.raises(EngineError, match="no object 999"):
        state.object(ObjectId(999))
    obj = state.object(ObjectId(1))
    assert state.card_of(obj).id == obj.card
