"""Casting a spell during a resolution (608.2g), without paying its mana cost (118.9, 107.3b).

Rishkar's Expertise ("... You may cast a spell with mana value 5 or less from your hand without
paying its mana cost.") is the effect used throughout. From the pinned CR:

- 608.2g: an effect that allows a player to cast a spell during resolution has them follow
  601.2a-i, "except no player receives priority after it's cast". The spell becomes the topmost
  object on the stack and the resolving spell goes on resolving. No other spells can be cast
  during resolution.
- 118.9: "without paying its mana cost" is an alternative cost; 118.9a: only one; 118.9c: the
  mana cost itself is unchanged; 118.9d: additional costs, increases and reductions apply to it.
- 107.3b: with neither the mana cost nor an alternative cost that includes X paid, X is 0.
- 118.6a: an alternative cost may be applied to an unpayable cost (no mana cost).
- 733.1-733.2: an illegal cast is reversed; "the player may redo the reversed action in a legal
  way or take any other action allowed by the rules". During a resolution nobody has priority,
  so the player is asked again whether (and what) to cast (docs/decisions.md, 2026-10-28).
"""

from __future__ import annotations

import pytest

from resolve.data.mana_cost import parse_mana_cost
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import CastSpellOption
from resolve.effects.characteristics import characteristics
from resolve.engine.casting import DECLINE
from resolve.errors import NotImplementedRule
from resolve.events.spells import (
    ActionReversed,
    SpellCast,
    SpellDidNotResolve,
    SpellResolved,
    XAnnounced,
)
from resolve.rules import defaults, legality
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import ManaType
from resolve.state.spell import (
    FROM_HAND,
    NORMAL,
    AlternativeCost,
    CastPermission,
    CastTiming,
    Half,
    TargetObject,
)
from resolve.state.turn import Phase
from resolve.state.zones import BATTLEFIELD, STACK, Zone, ZoneKind
from tests.casting_support import (
    activate,
    answered,
    cast_during_resolution,
    decline,
    options,
    pass_,
    records,
)
from tests.game_fixtures import request_of
from tests.scenario import Scenario, names, run_script

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)


def free(expertise: ObjectId) -> CastPermission:
    """The permission Rishkar's Expertise gives while it resolves (608.2g, 118.9)."""
    return CastPermission(
        "608.2g",
        ZoneKind.HAND,
        CastTiming.DURING_RESOLUTION,
        source=expertise,
        alternative_cost=AlternativeCost.WITHOUT_PAYING_MANA_COST,
        mana_value_at_most=5,
    )


def resolving(
    scenario: Scenario, hand: list[str], *, creatures: tuple[str, ...] = ()
) -> tuple[ObjectId, list[ObjectId]]:
    """P0's Rishkar's Expertise on the stack in P0's main phase, P0 holding ``hand`` (and with
    ``creatures``), five Forests in P0's library. Returns the spell and the hand."""
    (expertise,) = scenario.stack(P0, ["Rishkar's Expertise"])
    held = scenario.hand(P0, hand)
    scenario.battlefield(P0, list(creatures))
    scenario.library(P0, ["Forest"] * 5)
    scenario.at(Phase.PRECOMBAT_MAIN)
    return expertise, held


def resolve(state: GameState, players: int = 2) -> None:
    """Every player passes, so the Expertise resolves."""
    run_script(state, *(pass_(PlayerId(p)) for p in range(players)))


def test_608_2g_offers_only_spells_of_mana_value_5_or_less() -> None:
    """Chandra's Ignition (mana value 5) may be cast; another Rishkar's Expertise (6) can't; a
    Forest is never cast (305.9; the ruling "Effects that allow you to 'cast' a card don't allow
    you to play a land card"). Declining comes first."""
    scenario = Scenario(2)
    expertise, (ignition, _, _) = resolving(
        scenario,
        ["Chandra's Ignition", "Rishkar's Expertise", "Forest"],
        creatures=("Grizzly Bears",),
    )
    state = scenario.build()
    resolve(state)
    request = request_of(state)
    assert (request.kind, request.player) == (DecisionKind.CAST_DURING_RESOLUTION, P0)
    assert "608.2g" in request.rules
    assert options(state) == (DECLINE, CastSpellOption(ignition, NORMAL, free(expertise)))


def test_608_2g_mana_value_is_the_printed_cost_not_what_is_paid() -> None:
    """The ruling: mana value comes only from the printed mana cost (202.3), ignoring cost
    reductions. Emerald Medallion would make another Expertise cost {3}{G}{G}, but its mana value
    is still 6: not offered. Hill Giant ({3}{R}, 4) is."""
    scenario = Scenario(2)
    expertise, (_, giant) = resolving(scenario, ["Rishkar's Expertise", "Hill Giant"])
    scenario.battlefield(P0, ["Emerald Medallion"])
    state = scenario.build()
    resolve(state)
    assert options(state) == (DECLINE, CastSpellOption(giant, NORMAL, free(expertise)))


def test_608_2g_a_sorcery_can_be_cast_while_the_expertise_resolves() -> None:
    """Test Ponder is a sorcery, and the stack isn't empty (the Expertise is on it), so 117.1a
    wouldn't allow it; 608.2g's permission ignores that timing. It becomes the topmost object of
    the stack while the Expertise is still under it."""
    scenario = Scenario(2)
    expertise, (ponder,) = resolving(scenario, ["Test Ponder"])
    state = scenario.build()
    resolve(state)
    assert CastSpellOption(ponder, NORMAL, free(expertise)) in options(state)
    run_script(state, cast_during_resolution(ponder, free(expertise)))
    (cast,) = records(state, SpellCast)
    (done,) = records(state, SpellResolved)
    assert done.spell == expertise
    cast_index = next(e.index for e in state.event_log if isinstance(e.record, SpellCast))
    done_index = next(e.index for e in state.event_log if isinstance(e.record, SpellResolved))
    assert cast_index < done_index  # 608.2g: cast while the Expertise was still resolving
    assert state.stack == [cast.spell]
    assert names(state, STACK) == ["Test Ponder"]


def test_608_2g_an_instant_and_a_flash_creature_are_offered_too() -> None:
    """The permission allows any spell type with mana value 5 or less: Test Shock (an instant)
    and Ashcoat Bear (flash) as well as Hill Giant."""
    scenario = Scenario(2)
    expertise, (shock, bear, giant) = resolving(
        scenario, ["Test Shock", "Ashcoat Bear", "Hill Giant"]
    )
    state = scenario.build()
    resolve(state)
    permission = free(expertise)
    assert options(state) == (
        DECLINE,
        CastSpellOption(shock, NORMAL, permission),
        CastSpellOption(bear, NORMAL, permission),
        CastSpellOption(giant, NORMAL, permission),
    )


def test_608_2g_no_priority_after_the_free_spell_is_cast() -> None:
    """Three players. P0 casts Grizzly Bears during the resolution: nobody receives priority
    until the Expertise has finished resolving and gone to the graveyard (608.2g, 608.2n); then
    the active player receives priority (117.3b) with the Bears on the stack. P1's Ashcoat Bear
    (flash) is never offered: nobody can cast spells during resolution but as the effect
    allows (608.2g)."""
    scenario = Scenario(3)
    expertise, (bears,) = resolving(scenario, ["Grizzly Bears"])
    scenario.hand(P1, ["Ashcoat Bear"])
    state = scenario.build()
    resolve(state, players=3)
    priorities = answered(state, DecisionKind.PRIORITY_ACTION)
    run_script(state, cast_during_resolution(bears, free(expertise)))
    assert answered(state, DecisionKind.PRIORITY_ACTION) == priorities
    assert answered(state, DecisionKind.CAST_DURING_RESOLUTION) == 1  # one spell only
    request = request_of(state)
    assert (request.kind, request.player) == (DecisionKind.PRIORITY_ACTION, P0)
    assert names(state, STACK) == ["Grizzly Bears"]
    assert names(state, Zone.graveyard(P0)) == ["Rishkar's Expertise"]
    assert names(state, Zone.hand(P1)) == ["Ashcoat Bear"]


def test_608_2g_the_free_spell_resolves_after_the_expertise_like_any_other() -> None:
    """Once the Expertise is gone, the Bears is an ordinary spell on the stack: when all players
    pass, it resolves (608.3a)."""
    scenario = Scenario(2)
    expertise, (bears,) = resolving(scenario, ["Grizzly Bears"])
    state = scenario.build()
    resolve(state)
    run_script(state, cast_during_resolution(bears, free(expertise)), pass_(P0), pass_(P1))
    assert names(state, BATTLEFIELD) == ["Grizzly Bears"]
    assert state.stack == []


def test_118_9_without_paying_its_mana_cost_pays_nothing() -> None:
    """Hill Giant ({3}{R}) cast with no mana available: no payment is asked, nothing is spent,
    and the total cost locked in is {0} (601.2f: the alternative cost is nothing, so the total
    is {0}). 118.9c: its mana cost is still {3}{R}, and its mana value 4, on the stack."""
    scenario = Scenario(2)
    expertise, (giant,) = resolving(scenario, ["Hill Giant"])
    state = scenario.build()
    resolve(state)
    run_script(state, cast_during_resolution(giant, free(expertise)))
    (cast,) = records(state, SpellCast)
    assert cast.total_cost == parse_mana_cost("{0}")
    assert cast.mana_spent == ()
    assert answered(state, DecisionKind.ACTIVATE_MANA_ABILITIES) == 0
    assert answered(state, DecisionKind.PAY_COSTS) == 0
    chars = characteristics(state, cast.spell)
    assert chars.mana_cost == parse_mana_cost("{3}{R}")
    assert chars.mana_value == 4
    record = state.objects[cast.spell].spell
    assert record is not None and record.permission == free(expertise)
    assert record.cast_from == Zone.hand(P0)


def test_118_9_lands_and_pool_are_untouched() -> None:
    """P0 has two untapped Mountains and {R} in their pool: casting Hill Giant without paying its
    mana cost taps nothing and spends nothing."""
    scenario = Scenario(2)
    expertise, (giant,) = resolving(scenario, ["Hill Giant"])
    mountains = scenario.battlefield(P0, ["Mountain", "Mountain"])
    scenario.mana(P0, ManaType.RED)
    state = scenario.build()
    resolve(state)
    run_script(state, cast_during_resolution(giant, free(expertise)))
    assert not any(state.objects[m].tapped for m in mountains)
    assert [m.type for m in state.player(P0).mana_pool] == [ManaType.RED]


def test_107_3b_x_must_be_0() -> None:
    """Test Growth ({X}{G}, mana value 1) cast without paying its mana cost: X isn't asked, it is
    announced as 0 (107.3b; the ruling "you must choose 0 as the value of X"), and the total cost
    is {0}."""
    scenario = Scenario(2)
    expertise, (growth,) = resolving(scenario, ["Test Growth"])
    state = scenario.build()
    resolve(state)
    run_script(state, cast_during_resolution(growth, free(expertise)))
    assert answered(state, DecisionKind.CHOOSE_X) == 0
    (announced,) = records(state, XAnnounced)
    assert announced.x == 0
    assert "107.3b" in announced.rules
    (cast,) = records(state, SpellCast)
    assert cast.total_cost == parse_mana_cost("{0}")
    record = state.objects[cast.spell].spell
    assert record is not None and record.x == 0
    assert characteristics(state, cast.spell).mana_value == 1  # 202.3e: X is 0


def test_601_2b_no_hybrid_announcement_when_the_mana_cost_isnt_paid() -> None:
    """601.2b asks for the nonhybrid equivalent only of "a cost that will be paid as the spell
    is being cast". Test Two-Tone ({1}{W/U}{W/U}) cast without paying its mana cost has nothing
    to announce, so the hybrid gap (M9) isn't reached."""
    scenario = Scenario(2)
    expertise, (two_tone,) = resolving(scenario, ["Test Two-Tone"])
    state = scenario.build()
    resolve(state)
    run_script(state, cast_during_resolution(two_tone, free(expertise)))
    (cast,) = records(state, SpellCast)
    assert cast.total_cost == parse_mana_cost("{0}")


def test_118_6a_a_card_with_no_mana_cost_can_be_cast_without_paying_it() -> None:
    """Test Insight has no mana cost (an unpayable cost, 118.6), so its mana value is 0 (202.3a)
    and the permission allows it; "if an alternative cost is applied to an unpayable cost,
    including an effect that allows a player to cast a spell without paying its mana cost, the
    alternative cost may be paid" (118.6a): it is cast."""
    scenario = Scenario(2)
    expertise, (insight,) = resolving(scenario, ["Test Insight"])
    state = scenario.build()
    resolve(state)
    run_script(state, cast_during_resolution(insight, free(expertise)))
    (cast,) = records(state, SpellCast)
    assert cast.total_cost == parse_mana_cost("{0}")
    assert names(state, STACK) == ["Test Insight"]
    assert not records(state, ActionReversed)


def test_118_9d_a_cost_increase_applies_to_the_alternative_cost() -> None:
    """118.9d: Test Thorn ("Spells cost {1} more to cast", here P1's) increases the alternative
    cost: the free Bears costs {1}, paid with P0's Forest."""
    scenario = Scenario(2)
    expertise, (bears,) = resolving(scenario, ["Grizzly Bears"])
    (forest,) = scenario.battlefield(P0, ["Forest"])
    scenario.battlefield(P1, ["Test Thorn"])
    state = scenario.build()
    resolve(state)
    run_script(state, cast_during_resolution(bears, free(expertise)), activate(forest))
    (cast,) = records(state, SpellCast)
    assert cast.total_cost == parse_mana_cost("{1}")
    assert state.objects[forest].tapped
    assert names(state, Zone.graveyard(P0)) == ["Rishkar's Expertise"]


def test_118_9d_a_reduction_finds_nothing_to_reduce() -> None:
    """118.9d, 601.2f: Emerald Medallion reduces the free Test Raptor's ({1}{G}) total cost, but
    the alternative cost has no generic mana: the total stays {0}."""
    scenario = Scenario(2)
    expertise, (raptor,) = resolving(scenario, ["Test Raptor"])
    scenario.battlefield(P0, ["Emerald Medallion"])
    state = scenario.build()
    resolve(state)
    run_script(state, cast_during_resolution(raptor, free(expertise)))
    (cast,) = records(state, SpellCast)
    assert cast.total_cost == parse_mana_cost("{0}")


def test_733_2_a_reversed_free_cast_can_be_chosen_again() -> None:
    """With Test Thorn, the free Bears costs {1} and P0 has no mana: the cast can't be paid and
    is reversed (733.1; the Bears is back in hand with its old ID). 733.2: P0 may redo the action
    or do something else; with nobody holding priority during the resolution, that is the same
    question again, with the same options (the Raptor too). P0 declines; the Expertise
    finishes."""
    scenario = Scenario(2)
    expertise, (bears, raptor) = resolving(scenario, ["Grizzly Bears", "Test Raptor"])
    scenario.battlefield(P1, ["Test Thorn"])
    state = scenario.build()
    resolve(state)
    permission = free(expertise)
    before = (
        DECLINE,
        CastSpellOption(bears, NORMAL, permission),
        CastSpellOption(raptor, NORMAL, permission),
    )
    assert options(state) == before
    run_script(state, cast_during_resolution(bears, permission))
    assert len(records(state, ActionReversed)) == 1
    request = request_of(state)
    assert (request.kind, request.player) == (DecisionKind.CAST_DURING_RESOLUTION, P0)
    assert options(state) == before
    assert names(state, Zone.hand(P0)) == ["Grizzly Bears", "Test Raptor"]
    assert state.stack == [expertise]
    run_script(state, decline())
    assert not records(state, SpellCast)
    assert names(state, Zone.graveyard(P0)) == ["Rishkar's Expertise"]
    assert names(state, Zone.hand(P0)) == ["Grizzly Bears", "Test Raptor"]


def test_608_2g_declining_casts_nothing() -> None:
    scenario = Scenario(2)
    _, (bears,) = resolving(scenario, ["Grizzly Bears"])
    state = scenario.build()
    resolve(state)
    run_script(state, decline())
    assert not records(state, SpellCast)
    assert state.stack == []
    assert names(state, Zone.graveyard(P0)) == ["Rishkar's Expertise"]
    assert bears in state.player(P0).hand
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION


def test_608_2g_nothing_is_asked_when_nothing_can_be_cast() -> None:
    """With only a land and a spell of mana value 6 in hand, the only answer would be to
    decline: nothing is asked."""
    scenario = Scenario(2)
    resolving(scenario, ["Forest", "Rishkar's Expertise"])
    state = scenario.build()
    resolve(state)
    assert answered(state, DecisionKind.CAST_DURING_RESOLUTION) == 0
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION
    assert names(state, Zone.graveyard(P0)) == ["Rishkar's Expertise"]


def test_608_2g_the_permission_ends_with_the_resolution() -> None:
    """Afterwards, with priority, the Bears may be cast only the normal way (601.3), paying its
    mana cost: the permission was for that resolution only."""
    scenario = Scenario(2)
    _, (bears,) = resolving(scenario, ["Grizzly Bears"])
    state = scenario.build()
    resolve(state)
    run_script(state, decline())
    assert state.cast_grants == []
    assert defaults.cast_permissions(state, P0, bears) == (FROM_HAND,)
    assert CastSpellOption(bears, NORMAL, FROM_HAND) in options(state)


def test_608_2g_a_spell_without_legal_targets_isnt_offered() -> None:
    """601.2c, as with priority: Chandra's Ignition needs a creature P0 controls; with none it
    isn't offered, so nothing is asked."""
    scenario = Scenario(2)
    resolving(scenario, ["Chandra's Ignition"])
    state = scenario.build()
    resolve(state)
    assert answered(state, DecisionKind.CAST_DURING_RESOLUTION) == 0


def test_608_2g_the_free_spell_may_target_the_resolving_expertise() -> None:
    """The ruling: the free spell "can target the Expertise spell on the stack, but the Expertise
    spell will become an illegal target before the free spell resolves". Cancel targets it (the
    only spell on the stack, so its only possible target, not asked); the Expertise then goes to
    the graveyard (608.2n), and Cancel, its only target gone, doesn't resolve (608.2b)."""
    scenario = Scenario(2)
    expertise, (cancel,) = resolving(scenario, ["Cancel"])
    state = scenario.build()
    resolve(state)
    run_script(state, cast_during_resolution(cancel, free(expertise)))
    spell = state.stack[-1]
    record = state.objects[spell].spell
    assert record is not None and record.targets == ((TargetObject(expertise),),)
    assert names(state, Zone.graveyard(P0)) == ["Rishkar's Expertise"]
    run_script(state, pass_(P0), pass_(P1))
    (failed,) = records(state, SpellDidNotResolve)
    assert failed.spell == spell


def test_608_2g_the_permission_ignores_timing_but_not_variants() -> None:
    """601.3e: the permission is offered for each way a card can be cast, each judged on its own
    characteristics; only the timing is ignored. Ashcoat Bear is offered as itself; Test Spark //
    Test Frost (drawn by the Expertise: a split card in hand is still the 109.3 gap while a
    player has priority) as each half (709.3a: only the half is considered, mana value 2 each),
    and casting a half is still the 709.3 gap (M5)."""
    scenario = Scenario(2)
    (expertise,) = scenario.stack(P0, ["Rishkar's Expertise"])
    scenario.battlefield(P0, ["Grizzly Bears"])
    (bear,) = scenario.hand(P0, ["Ashcoat Bear"])
    scenario.library(P0, ["Test Spark // Test Frost", "Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    resolve(state)
    split = state.player(P0).hand[1]
    permission = free(expertise)
    assert options(state) == (
        DECLINE,
        CastSpellOption(bear, NORMAL, permission),
        CastSpellOption(split, Half(0), permission),
        CastSpellOption(split, Half(1), permission),
    )
    with pytest.raises(NotImplementedRule) as gap:
        run_script(state, cast_during_resolution(split, permission, Half(0)))
    assert gap.value.rule == "709.3"


def test_608_2g_an_adventurer_card_is_still_a_gap() -> None:
    """An adventurer card's characteristics are still the 109.3 gap (715, M4), so an adventurer
    the Expertise draws (Test Adventurer // Test Quest) reaches that gap when the free cast is
    offered, as it would with priority, rather than being offered or refused silently."""
    scenario = Scenario(2)
    scenario.stack(P0, ["Rishkar's Expertise"])
    scenario.battlefield(P0, ["Grizzly Bears"])
    scenario.library(P0, ["Test Adventurer // Test Quest", "Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    with pytest.raises(NotImplementedRule) as gap:
        resolve(state)
    assert gap.value.rule == "109.3"


def test_601_2e_the_permission_is_checked_again_for_the_proposed_spell() -> None:
    """The free spell is checked again once proposed (601.2e) under the same permission: the
    grant is still there while it is cast, so the cast completes."""
    scenario = Scenario(2)
    expertise, (giant,) = resolving(scenario, ["Hill Giant"])
    state = scenario.build()
    resolve(state)
    assert [g.permission for g in state.cast_grants] == [free(expertise)]
    run_script(state, cast_during_resolution(giant, free(expertise)))
    assert len(records(state, SpellCast)) == 1


def test_601_3_the_permission_refuses_a_spell_above_its_mana_value() -> None:
    """``legality.allowed`` judges the permission's mana value limit on the card's
    characteristics (601.3, 601.3e): with the grant in place, Hill Giant (4) is allowed and a
    second Rishkar's Expertise (6) isn't."""
    scenario = Scenario(2)
    expertise, (giant, second) = resolving(scenario, ["Hill Giant", "Rishkar's Expertise"])
    state = scenario.build()
    resolve(state)
    permission = free(expertise)
    assert legality.allowed(state, legality.CastAction(P0, giant, NORMAL, permission)).allowed
    verdict = legality.allowed(state, legality.CastAction(P0, second, NORMAL, permission))
    assert not verdict.allowed
