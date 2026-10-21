"""The rule-default functions (rule 12, design.md §17.1) return the CR's defaults.

Each test names the rule the default comes from. The seam tests, which replace a function and
check the engine obeys it, are in ``tests/rules/test_rule_default_seams.py``.
"""

from __future__ import annotations

import pytest

from resolve.engine import defaults
from resolve.engine.defaults import KEEP, MULLIGAN, LossReason
from resolve.errors import NotImplementedRule
from resolve.state.config import GameConfig
from resolve.state.ids import PlayerId
from resolve.state.mana import Mana, ManaType
from resolve.state.turn import TURN_SEQUENCE, Phase, Step
from tests.scenario import Scenario

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)


def test_305_2_one_land_play_per_turn() -> None:
    state = Scenario(2).build()
    assert defaults.land_plays_allowed(state, P0) == 1
    assert defaults.land_plays_allowed(state, P1) == 1


def test_117_1a_sorcery_timing_is_the_own_main_phase_with_an_empty_stack() -> None:
    scenario = Scenario(3)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    assert defaults.has_sorcery_timing(state, P0)
    assert not defaults.has_sorcery_timing(state, P1)  # not their turn
    assert not defaults.has_sorcery_timing(state, P2)


def test_117_1a_sorcery_timing_needs_the_stack_empty() -> None:
    scenario = Scenario(2)
    scenario.stack(P1, ["Test Shock"])
    scenario.at(Phase.POSTCOMBAT_MAIN)
    state = scenario.build()
    assert not defaults.has_sorcery_timing(state, P0)


@pytest.mark.parametrize("step", [Step.UPKEEP, Step.DRAW, Step.END_OF_COMBAT, Step.END])
def test_117_1a_sorcery_timing_isnt_in_a_step(step: Step) -> None:
    scenario = Scenario(2)
    scenario.at(step)
    state = scenario.build()
    assert not defaults.has_sorcery_timing(state, P0)


def test_305_1_land_plays_come_from_lands_in_the_hand_at_sorcery_timing() -> None:
    scenario = Scenario(2)
    forest, _shock, plains = scenario.hand(P0, ["Forest", "Test Shock", "Plains"])
    scenario.graveyard(P0, ["Forest"])
    scenario.hand(P1, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    assert defaults.land_play_options(state, P0) == (forest, plains)
    assert defaults.land_play_options(state, P1) == ()  # 305.3: not on another player's turn


def test_305_1_no_land_play_outside_sorcery_timing() -> None:
    scenario = Scenario(2)
    scenario.hand(P0, ["Forest"])
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    assert defaults.land_play_options(state, P0) == ()


def test_117_1a_an_instant_may_be_cast_whenever_its_controller_has_priority() -> None:
    scenario = Scenario(2)
    (shock,) = scenario.hand(P0, ["Test Shock"])
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    assert defaults.may_cast_now(state, P0, shock)


def test_117_1a_other_spells_need_sorcery_timing_and_lands_are_never_cast() -> None:
    scenario = Scenario(2)
    ponder, bears, forest = scenario.hand(P0, ["Test Ponder", "Grizzly Bears", "Forest"])
    scenario.at(Step.UPKEEP)
    upkeep = scenario.build()
    assert not defaults.may_cast_now(upkeep, P0, ponder)
    assert not defaults.may_cast_now(upkeep, P0, bears)
    scenario = Scenario(2)
    ponder, bears, forest = scenario.hand(P0, ["Test Ponder", "Grizzly Bears", "Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    main = scenario.build()
    assert defaults.may_cast_now(main, P0, ponder)
    assert defaults.may_cast_now(main, P0, bears)
    assert not defaults.may_cast_now(main, P0, forest)  # 305.9


def test_402_2_the_maximum_hand_size_is_seven() -> None:
    state = Scenario(2).build()
    assert defaults.maximum_hand_size(state, P0) == 7


def test_504_1_the_draw_step_draws_one_card() -> None:
    assert defaults.draw_step_draws(Scenario(2).build(), P0) == 1


def test_500_1_a_turn_has_the_five_phases_in_order() -> None:
    state = Scenario(2).build()
    assert defaults.turn_structure(state, P0) == TURN_SEQUENCE
    assert next(phase for phase, _ in TURN_SEQUENCE) is Phase.BEGINNING


def test_103_8a_the_starting_player_skips_their_first_draw_in_a_two_player_game() -> None:
    scenario = Scenario(2)
    scenario.at(Step.UNTAP, number=1)
    state = scenario.build()
    assert defaults.is_skipped(state, (Phase.BEGINNING, Step.DRAW))
    assert not defaults.is_skipped(state, (Phase.BEGINNING, Step.UPKEEP))


def test_103_8a_only_the_first_turn_skips_its_draw() -> None:
    scenario = Scenario(2)
    scenario.at(Step.UNTAP, number=2, active=P1)
    state = scenario.build()
    assert not defaults.is_skipped(state, (Phase.BEGINNING, Step.DRAW))


def test_103_8c_nobody_skips_the_first_draw_in_a_multiplayer_game() -> None:
    scenario = Scenario(3)
    scenario.at(Step.UNTAP, number=1)
    state = scenario.build()
    assert not defaults.is_skipped(state, (Phase.BEGINNING, Step.DRAW))


def test_508_8_the_blockers_and_damage_steps_are_skipped_with_no_attackers() -> None:
    scenario = Scenario(2)
    scenario.at(Step.UNTAP, number=2)
    state = scenario.build()
    skipped = [segment for segment in TURN_SEQUENCE if defaults.is_skipped(state, segment)]
    assert skipped == [(Phase.COMBAT, Step.DECLARE_BLOCKERS), (Phase.COMBAT, Step.COMBAT_DAMAGE)]


def test_103_1_500_7_the_next_turn_is_the_next_player_in_turn_order() -> None:
    scenario = Scenario(3, starting_player=1)
    scenario.at(Step.UNTAP, active=P1)
    state = scenario.build()
    nxt = defaults.next_turn(state)
    assert (nxt.player, nxt.extra_turns) == (P2, ())


def test_500_7_extra_turns_are_taken_the_last_created_first() -> None:
    scenario = Scenario(3)
    scenario.at(Phase.PRECOMBAT_MAIN, active=P1)
    state = scenario.build()
    state.extra_turns = [P2, P0]
    nxt = defaults.next_turn(state)
    assert (nxt.player, nxt.extra_turns) == (P0, (P2,))


def test_800_4k_an_extra_turn_of_a_player_who_left_is_not_taken() -> None:
    scenario = Scenario(3)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    state.player(P2).left_game = True
    state.extra_turns = [P1, P2]
    nxt = defaults.next_turn(state)
    assert (nxt.player, nxt.extra_turns) == (P1, ())


def test_103_1_turn_order_is_clockwise() -> None:
    assert Scenario(2).build().turn_direction == 1


def test_502_3_all_the_active_players_permanents_untap() -> None:
    scenario = Scenario(2)
    mine = scenario.battlefield(P0, ["Forest", "Grizzly Bears"])
    scenario.battlefield(P1, ["Forest"])
    state = scenario.build()
    assert defaults.permanents_that_untap(state, P0) == tuple(mine)


def test_500_5_all_unspent_mana_empties() -> None:
    scenario = Scenario(2)
    scenario.mana(P0, ManaType.GREEN, ManaType.RED)
    state = scenario.build()
    assert defaults.mana_that_empties(state, P0) == (Mana(ManaType.GREEN), Mana(ManaType.RED))
    assert defaults.mana_that_empties(state, P1) == ()


@pytest.mark.parametrize("reason", list(LossReason))
def test_104_3_a_player_can_lose_the_game(reason: LossReason) -> None:
    assert defaults.can_lose_game(Scenario(2).build(), P0, reason)


def test_loss_reasons_cite_their_rules() -> None:
    assert {r.name: r.value for r in LossReason} == {
        "ZERO_LIFE": "704.5a",
        "EMPTY_LIBRARY": "704.5b",
    }


def test_103_6_no_actions_start_on_opening_hands() -> None:
    assert defaults.opening_hand_actions(Scenario(2).build(), P0) == ()


def test_103_5_a_player_may_keep_or_mulligan() -> None:
    assert defaults.mulligan_options(Scenario(2).build(), P0) == (KEEP, MULLIGAN)


def test_103_4_103_5_903_10a_the_config_values() -> None:
    standard = Scenario(2).build()
    assert defaults.starting_life(standard, P0) == 20
    assert defaults.starting_hand_size(standard, P0) == 7
    assert defaults.commander_damage_threshold(standard, P0) is None
    commander = Scenario(2, config=GameConfig.commander_game()).build()
    assert defaults.starting_life(commander, P1) == 40
    assert defaults.commander_damage_threshold(commander, P1) == 21


def test_302_6_a_noncreature_permanent_may_pay_a_tap_cost() -> None:
    scenario = Scenario(2)
    (forest,) = scenario.battlefield(P0, ["Forest"])
    assert defaults.can_tap_for_cost(scenario.build(), forest)


def test_302_6_a_creatures_tap_cost_is_a_gap_until_summoning_sickness_exists() -> None:
    scenario = Scenario(2)
    (bears,) = scenario.battlefield(P0, ["Grizzly Bears"])
    with pytest.raises(NotImplementedRule, match=r"302\.6"):
        defaults.can_tap_for_cost(scenario.build(), bears)


def test_702_players_have_no_abilities_of_their_own() -> None:
    assert defaults.player_abilities(Scenario(2).build(), P0) == ()


def test_723_a_player_makes_their_own_decisions() -> None:
    state = Scenario(3).build()
    assert [defaults.deciding_player(state, p) for p in (P0, P1, P2)] == [P0, P1, P2]
