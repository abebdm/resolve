"""The rule-default functions (CLAUDE.md rule 12, design.md §17.1) return the CR's defaults.

Each function is the one place effects plug into a value or procedure the CR gives a default.
The expected values are worked from the pinned CR:

- 305.2: a player can normally play one land during their turn; 305.1: from their hand;
  117.1a, 307.1: sorcery timing is the player's own main phase with an empty stack;
  601.3, 903.8: a spell is cast from the hand, a commander also from the command zone.
- 402.2: the maximum hand size is seven. 504.1: the draw step draws one card.
- 500.1: the turn's phases and steps; 103.8a: the starting player skips the first draw step in
  a two-player game; 508.8: no attackers means no declare blockers or combat damage step.
- 500.7: extra turns come before the normal turn order (none here); 103.1: turn order proceeds
  clockwise.
- 502.3: the active player untaps all their permanents. 500.5: all unspent mana empties.
- 104.3: a player loses by the usual means. 302.6: summoning sickness (M2.4 builds the check).
- 723.5: nobody decides for another player by default; 723.4, 400.2, 402.3: who knows what.
- 103.4, 103.5, 903.10a: the game configuration. 103.6: no actions from opening hands by
  default. 702.11c, 702.18a: no player has hexproof or shroud by default.

The seam tests in the other files of this folder check that the engine obeys each function.
"""

from __future__ import annotations

import pytest

from resolve.citations import cited_rules
from resolve.data.types import CardType
from resolve.decisions.spaces import CastSpellOption
from resolve.errors import NotImplementedRule
from resolve.rules import defaults
from resolve.state.config import GameConfig
from resolve.state.ids import PlayerId
from resolve.state.mana import Mana, ManaType
from resolve.state.spell import COMMANDER, FROM_HAND, NORMAL, CastPermission, CastTiming
from resolve.state.turn import TURN_SEQUENCE, Phase, Step
from resolve.state.zones import ZoneKind
from tests.scenario import Scenario

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)

# Every function, with the CR rules its docstring must cite.
CITATIONS = {
    "land_plays_allowed": ["305.2"],
    "land_play_options": ["305.1"],
    "cast_permissions": ["601.3", "903.8"],
    "cast_options": ["601.3", "117.1a"],
    "has_sorcery_timing": ["117.1a", "307.1"],
    "may_cast_now": ["117.1a"],
    "resolved_spell_destination": ["608.2n"],
    "maximum_hand_size": ["402.2"],
    "draw_step_draws": ["504.1"],
    "turn_structure": ["500.1"],
    "is_skipped": ["500.11", "103.8a", "508.8"],
    "next_turn": ["500.7", "103.1", "800.4k"],
    "permanents_that_untap": ["502.3"],
    "mana_that_empties": ["500.5"],
    "can_lose_game": ["104.3"],
    "deciding_player": ["723.5"],
    "knows_identity": ["400.2", "402.3", "723.4"],
    "can_tap_for_cost": ["302.6"],
    "player_abilities": ["702.11c", "702.18a"],
    "opening_hand_actions": ["103.6"],
    "mulligan_options": ["103.5"],
    "starting_life": ["103.4"],
    "starting_hand_size": ["103.5"],
    "commander_damage_threshold": ["903.10a"],
}


@pytest.mark.parametrize(("name", "rules"), CITATIONS.items())
def test_every_rule_default_function_cites_its_rules(name: str, rules: list[str]) -> None:
    """CLAUDE.md rule 12: each function cites its CR rule in its docstring."""
    doc = getattr(defaults, name).__doc__ or ""
    cited = cited_rules(doc)
    assert all(rule in cited for rule in rules), (name, rules, cited)


def main_phase(lands_played: int = 0) -> Scenario:
    scenario = Scenario(2)
    scenario.at(Phase.PRECOMBAT_MAIN, lands_played=lands_played)
    return scenario


def test_305_2_the_default_is_one_land_per_turn() -> None:
    state = Scenario(3).build()
    assert [defaults.land_plays_allowed(state, p) for p in (P0, P1, P2)] == [1, 1, 1]


def test_305_1_land_play_options_are_the_lands_in_the_hand_during_the_players_main_phase() -> None:
    scenario = main_phase()
    forest, _bears, _shock, second = scenario.hand(
        P0, ["Forest", "Grizzly Bears", "Test Shock", "Forest"]
    )
    (opponents,) = scenario.hand(P1, ["Forest"])
    scenario.graveyard(P0, ["Forest"])
    state = scenario.build()
    assert defaults.land_play_options(state, P0) == (forest, second)
    assert defaults.land_play_options(state, P1) == ()  # 305.3: not on another player's turn
    assert opponents not in defaults.land_play_options(state, P0)


def test_305_2a_no_land_options_once_the_one_land_is_played() -> None:
    scenario = main_phase(lands_played=1)
    scenario.hand(P0, ["Forest"])
    assert defaults.land_play_options(scenario.build(), P0) == ()


def test_305_1_no_land_options_with_a_spell_on_the_stack_or_outside_a_main_phase() -> None:
    scenario = Scenario(2)
    scenario.hand(P0, ["Forest"])
    scenario.stack(P1, ["Test Shock"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    assert defaults.land_play_options(scenario.build(), P0) == ()
    upkeep = Scenario(2)
    upkeep.hand(P0, ["Forest"])
    upkeep.at(Step.UPKEEP)
    assert defaults.land_play_options(upkeep.build(), P0) == ()


def test_117_1a_sorcery_timing_is_the_active_players_main_phase_with_an_empty_stack() -> None:
    state = main_phase().build()
    assert defaults.has_sorcery_timing(state, P0)
    assert not defaults.has_sorcery_timing(state, P1)
    postcombat = Scenario(2)
    postcombat.at(Phase.POSTCOMBAT_MAIN)
    assert defaults.has_sorcery_timing(postcombat.build(), P0)
    combat = Scenario(2)
    combat.at(Step.BEGINNING_OF_COMBAT)
    assert not defaults.has_sorcery_timing(combat.build(), P0)
    busy = Scenario(2)
    busy.stack(P1, ["Test Shock"])
    busy.at(Phase.PRECOMBAT_MAIN)
    assert not defaults.has_sorcery_timing(busy.build(), P0)


def test_117_1a_an_instant_may_be_cast_whenever_a_sorcery_needs_sorcery_timing() -> None:
    """117.1a: a player may cast an instant whenever they have priority; 307.1, 301.1, 302.1: any
    other spell only with sorcery timing."""
    scenario = Scenario(2)
    shock, ponder, bears, forest = scenario.hand(
        P0, ["Test Shock", "Test Ponder", "Grizzly Bears", "Forest"]
    )
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    assert defaults.may_cast_now(state, P0, shock)
    assert not defaults.may_cast_now(state, P0, ponder)
    assert not defaults.may_cast_now(state, P0, bears)
    assert not defaults.may_cast_now(state, P0, forest)  # 305.9: a land isn't a spell
    main = Scenario(2)
    shock, ponder, bears, forest = main.hand(
        P0, ["Test Shock", "Test Ponder", "Grizzly Bears", "Forest"]
    )
    main.at(Phase.PRECOMBAT_MAIN)
    state = main.build()
    assert [defaults.may_cast_now(state, P0, o) for o in (shock, ponder, bears)] == [True] * 3
    assert not defaults.may_cast_now(state, P0, forest)


def test_601_3_cast_options_are_the_spells_in_hand_then_commanders_in_the_command_zone() -> None:
    """601.3, 903.8: a spell in the hand may be cast when the timing allows; a commander also from
    the command zone. A land never (305.9); a card in the command zone that isn't the player's
    commander never."""
    scenario = Scenario(2, config=GameConfig.commander_game())
    forest, shock, ponder = scenario.hand(P0, ["Forest", "Test Shock", "Test Ponder"])
    commander = scenario.commander(P0, "Grizzly Bears")
    (other,) = scenario.command(P0, ["Test Shock"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    assert defaults.cast_options(state, P0) == (
        CastSpellOption(shock, NORMAL, FROM_HAND),
        CastSpellOption(ponder, NORMAL, FROM_HAND),
        CastSpellOption(commander, NORMAL, COMMANDER),
    )
    offered = [option.object for option in defaults.cast_options(state, P0)]
    assert forest not in offered and other not in offered
    assert defaults.cast_options(state, P1) == ()  # not their turn: nothing has sorcery timing


def test_402_2_the_default_maximum_hand_size_is_seven() -> None:
    state = Scenario(3).build()
    assert [defaults.maximum_hand_size(state, p) for p in (P0, P1, P2)] == [7, 7, 7]


def test_504_1_the_draw_step_draws_one_card() -> None:
    state = Scenario(2).build()
    assert defaults.draw_step_draws(state, P0) == 1


def test_500_1_the_default_turn_structure_is_the_whole_sequence() -> None:
    state = Scenario(2).build()
    assert defaults.turn_structure(state, P0) == TURN_SEQUENCE
    assert TURN_SEQUENCE[0] == (Phase.BEGINNING, Step.UNTAP)
    assert TURN_SEQUENCE[-1] == (Phase.ENDING, Step.CLEANUP)
    assert len(TURN_SEQUENCE) == 12  # 3 beginning + 1 + 5 combat + 1 + 2 ending steps


def test_103_8a_508_8_the_default_skips() -> None:
    """103.8a: the draw step of the starting player's first turn in a two-player game; 103.8c:
    not in a game that began with more players. 508.8: with no attackers, no declare blockers
    or combat damage step. Nothing else is skipped."""
    first = Scenario(2)
    first.at(Step.UPKEEP, number=1)
    state = first.build()
    skipped = [segment for segment in TURN_SEQUENCE if defaults.is_skipped(state, segment)]
    assert skipped == [
        (Phase.BEGINNING, Step.DRAW),
        (Phase.COMBAT, Step.DECLARE_BLOCKERS),
        (Phase.COMBAT, Step.COMBAT_DAMAGE),
    ]
    later = Scenario(2)
    later.at(Step.UPKEEP, number=2)
    state = later.build()
    assert (Phase.BEGINNING, Step.DRAW) not in [
        s for s in TURN_SEQUENCE if defaults.is_skipped(state, s)
    ]
    multi = Scenario(3)
    multi.at(Step.UPKEEP, number=1)
    state = multi.build()
    assert not defaults.is_skipped(state, (Phase.BEGINNING, Step.DRAW))


def test_500_7_103_1_the_next_turn_is_the_next_player_in_turn_order() -> None:
    state = Scenario(3).build()
    assert defaults.next_turn(state, P0) == defaults.NextTurn(P1, extra=False)
    assert defaults.next_turn(state, P2) == defaults.NextTurn(P0, extra=False)


def test_800_4k_the_next_turn_skips_players_who_left() -> None:
    """800.4k: a player who left the game doesn't begin a turn, so the turn goes to the next player
    still in the game."""
    state = Scenario(3).build()
    state.player(P1).left_game = True
    assert defaults.next_turn(state, P0) == defaults.NextTurn(P2, extra=False)


def test_502_3_all_the_active_players_permanents_untap() -> None:
    scenario = Scenario(2)
    mine = scenario.battlefield(P0, ["Forest", "Llanowar Elves"])
    scenario.battlefield(P1, ["Forest"])
    state = scenario.build()
    assert defaults.permanents_that_untap(state, P0) == tuple(mine)


def test_500_5_all_unspent_mana_empties() -> None:
    scenario = Scenario(2)
    scenario.mana(P0, ManaType.GREEN, ManaType.RED)
    state = scenario.build()
    assert defaults.mana_that_empties(state, P0) == (Mana(ManaType.GREEN), Mana(ManaType.RED))
    assert defaults.mana_that_empties(state, P1) == ()


@pytest.mark.parametrize("reason", list(defaults.LossReason))
def test_104_3_a_player_can_lose_the_game_by_default(reason: defaults.LossReason) -> None:
    state = Scenario(2).build()
    assert defaults.can_lose_game(state, P0, reason)


def test_723_5_nobody_decides_for_another_player_by_default() -> None:
    state = Scenario(3).build()
    assert [defaults.deciding_player(state, p) for p in (P0, P1, P2)] == [P0, P1, P2]


def test_302_6_a_tap_cost_on_a_creature_is_still_a_gap_until_m2_4() -> None:
    """The M1 behaviour stays (no behaviour change in M2.1): a permanent that isn't a creature
    can be tapped for a cost if it's untapped (118.3); a creature raises the 302.6 gap."""
    scenario = Scenario(2)
    forest, elves = scenario.battlefield(P0, ["Forest", "Llanowar Elves"])
    scenario.battlefield(P0, ["Test Land Creature"])
    state = scenario.build()
    assert defaults.can_tap_for_cost(state, forest)
    with pytest.raises(NotImplementedRule, match=r"302\.6"):
        defaults.can_tap_for_cost(state, elves)


def test_702_11c_no_player_has_abilities_by_default() -> None:
    state = Scenario(2).build()
    assert defaults.player_abilities(state, P0) == ()


def test_103_6_there_are_no_actions_from_opening_hands_by_default() -> None:
    scenario = Scenario(2)
    scenario.hand(P0, ["Forest", "Test Shock"])
    state = scenario.build()
    assert defaults.opening_hand_actions(state, P0) == ()


def test_103_5_a_player_with_cards_may_keep_or_mulligan() -> None:
    scenario = Scenario(2)
    scenario.hand(P0, ["Forest"])
    state = scenario.build()
    assert defaults.mulligan_options(state, P0) == (defaults.KEEP, defaults.MULLIGAN)


def test_103_5_a_player_with_no_cards_may_only_keep() -> None:
    """103.5: a player can take mulligans until their opening hand would be zero cards, after
    which they may not take further mulligans."""
    state = Scenario(2).build()
    assert defaults.mulligan_options(state, P0) == (defaults.KEEP,)


def test_103_4_103_5_903_10a_the_game_configuration_is_read_through_accessors() -> None:
    """103.4: 20 life, 40 in Commander (103.4c); 103.5: seven cards; 903.10a: 21 damage."""
    standard = Scenario(2).build()
    assert (defaults.starting_life(standard, P0), defaults.starting_hand_size(standard, P0)) == (
        20,
        7,
    )
    commander = Scenario(2, config=GameConfig.commander_game()).build()
    assert defaults.starting_life(commander, P1) == 40
    assert defaults.commander_damage_threshold(commander) == 21


def test_the_card_types_the_defaults_ask_about_are_the_engines() -> None:
    """A guard for the tests above: the fixture cards have the types the tests assume."""
    scenario = Scenario(2)
    shock, ponder, bears = scenario.hand(P0, ["Test Shock", "Test Ponder", "Grizzly Bears"])
    state = scenario.build()
    from resolve.effects.characteristics import characteristics

    assert characteristics(state, shock).is_a(CardType.INSTANT)
    assert characteristics(state, ponder).is_a(CardType.SORCERY)
    assert characteristics(state, bears).is_a(CardType.CREATURE)


def test_601_3_903_8_the_rules_permissions_to_cast() -> None:
    """601.3, 601.2a: a card in its owner's hand may be cast from there; 903.8: a commander from
    the command zone by its owner. Nothing else: not another player's card, not a card in the
    command zone that isn't the player's commander, not a card in a graveyard or library."""
    scenario = Scenario(2, config=GameConfig.commander_game())
    (shock,) = scenario.hand(P0, ["Test Shock"])
    (theirs,) = scenario.hand(P1, ["Test Shock"])
    commander = scenario.commander(P0, "Grizzly Bears")
    their_commander = scenario.commander(P1, "Grizzly Bears")
    (other,) = scenario.command(P0, ["Test Shock"])
    (dead,) = scenario.graveyard(P0, ["Test Shock"])
    (deep,) = scenario.library(P0, ["Test Shock"])
    state = scenario.build()
    assert defaults.cast_permissions(state, P0, shock) == (FROM_HAND,)
    assert defaults.cast_permissions(state, P0, commander) == (COMMANDER,)
    for obj in (theirs, their_commander, other, dead, deep):
        assert defaults.cast_permissions(state, P0, obj) == ()


def test_601_2e_a_proposed_spell_is_judged_from_the_zone_it_came_from() -> None:
    """While its proposal is checked (601.2e), a spell on the stack keeps the permission of the
    zone it was cast from, and it doesn't count against its own sorcery timing."""
    scenario = Scenario(2)
    (spell,) = scenario.stack(P0, ["Grizzly Bears"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    assert defaults.cast_permissions(state, P0, spell) == (FROM_HAND,)
    assert not defaults.has_sorcery_timing(state, P0)
    assert defaults.has_sorcery_timing(state, P0, ignoring=spell)
    assert defaults.may_cast_now(state, P0, spell, NORMAL, FROM_HAND)


def test_117_1a_ignoring_one_spell_still_counts_the_others() -> None:
    scenario = Scenario(2)
    top, below = scenario.stack(P0, ["Grizzly Bears", "Hill Giant"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    assert not defaults.has_sorcery_timing(state, P0, ignoring=top)
    assert not defaults.has_sorcery_timing(state, P0, ignoring=below)


@pytest.mark.parametrize(
    ("timing", "rule"),
    [(CastTiming.AS_THOUGH_FLASH, "601.3b"), (CastTiming.DURING_RESOLUTION, "608.2g")],
)
def test_601_3b_608_2g_other_cast_timings_are_gaps(timing: CastTiming, rule: str) -> None:
    scenario = Scenario(2)
    (bears,) = scenario.hand(P0, ["Grizzly Bears"])
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    permission = CastPermission("601.3", ZoneKind.HAND, timing)
    with pytest.raises(NotImplementedRule) as gap:
        defaults.may_cast_now(state, P0, bears, NORMAL, permission)
    assert gap.value.rule == rule
