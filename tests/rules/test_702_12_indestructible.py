"""702.12: indestructible.

From the pinned CR:

- 702.12b: a permanent with indestructible can't be destroyed. Such permanents aren't destroyed
  by lethal damage, and they ignore the state-based action that checks for lethal damage
  (704.5g).
- 704.5f: a creature with toughness 0 or less is put into its owner's graveyard; that isn't
  destruction (701.8b), so indestructible doesn't stop it.
- 701.13a: exiling isn't destroying either.
- 514.2: damage stays marked until the cleanup step.
- Indestructible doesn't stop a permanent from being targeted (only 702.11, 702.16, 702.18 do).
"""

from __future__ import annotations

from resolve.decisions.spaces import ObjectOption
from resolve.events.damage import DamageDealt
from resolve.events.permanents import ObjectExiled, PermanentDestroyed, PutIntoGraveyard
from resolve.events.spells import SpellResolved
from resolve.rules import legality
from resolve.state.ids import PlayerId
from resolve.state.mana import ManaType
from resolve.state.spell import TargetObject
from resolve.state.turn import Phase, Step
from resolve.state.zones import EXILE, Zone
from tests.casting_support import cast, choose_modes, pass_, records, target_choices
from tests.scenario import Scenario, names, run_script

P0, P1 = PlayerId(0), PlayerId(1)
W, R = ManaType.WHITE, ManaType.RED


def test_702_12b_destroy_does_nothing() -> None:
    """P1's Fiery Confluence, modes (2 damage to each opponent, twice; destroy target artifact)
    targeting P0's Darksteel Relic: the target is legal, so the spell resolves (P0 takes 4), but
    the Relic isn't destroyed (702.12b)."""
    scenario = Scenario(2)
    (confluence,) = scenario.stack(P1, ["Fiery Confluence"])
    (relic,) = scenario.battlefield(P0, ["Darksteel Relic"])
    scenario.modes(confluence, 1, 1, 2).targets(confluence, [TargetObject(relic)])
    scenario.at(Phase.PRECOMBAT_MAIN, active=P1)
    state = scenario.build()
    life = state.player(P0).life
    run_script(state, pass_(P1), pass_(P0))
    (resolved,) = records(state, SpellResolved)
    assert resolved.spell == confluence
    assert records(state, PermanentDestroyed) == []
    assert state.battlefield == [relic] and state.player(P0).life == life - 4
    verdict = legality.allowed(state, legality.DestroyAction(P1, relic))
    assert not verdict.allowed and verdict.rules == ("101.2", "702.12b")


def test_702_12b_lethal_damage_doesnt_destroy() -> None:
    """Darksteel Myr (0/1) with 1 damage marked stays on the battlefield through state-based
    actions (702.12b, 704.5g); Test Shock's 2 more damage doesn't destroy it either. The damage
    stays until the cleanup step removes it (514.2)."""
    scenario = Scenario(2)
    (myr,) = scenario.battlefield(P0, ["Darksteel Myr"])
    (shock,) = scenario.stack(P1, ["Test Shock"])
    scenario.targets(shock, [TargetObject(myr)])
    scenario.damage(myr, 1)
    scenario.at(Step.END)
    state = scenario.build()
    assert state.battlefield == [myr] and state.objects[myr].damage == 1
    run_script(state, pass_(P0), pass_(P1))
    (damage,) = records(state, DamageDealt)
    assert damage.to_objects == ((myr, 2),)
    assert state.battlefield == [myr] and state.objects[myr].damage == 3
    run_script(state, pass_(P0), pass_(P1))  # the end step ends; cleanup (514.2)
    assert state.turn is not None and state.turn.active_player == P1
    assert state.battlefield == [myr] and state.objects[myr].damage == 0
    assert records(state, PermanentDestroyed) == []


def test_704_5f_zero_toughness_still_puts_it_in_the_graveyard() -> None:
    """Test Indestructible Wisp (1/0, indestructible) is put into its owner's graveyard by
    704.5f: that isn't destroying it (701.8b), so indestructible doesn't help."""
    scenario = Scenario(2)
    (wisp,) = scenario.battlefield(P0, ["Test Indestructible Wisp"])
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    (moved,) = records(state, PutIntoGraveyard)
    assert moved.obj == wisp and moved.rules[0] == "704.5f"
    assert names(state, Zone.graveyard(P0)) == ["Test Indestructible Wisp"]


def test_702_12_exile_still_works() -> None:
    """P1's Swords to Plowshares exiles P0's Darksteel Myr (701.13a: exile isn't destroy); P0
    gains 0 life, its power (119.10: no life gain event)."""
    scenario = Scenario(2)
    (swords,) = scenario.stack(P1, ["Swords to Plowshares"])
    (myr,) = scenario.battlefield(P0, ["Darksteel Myr"])
    scenario.targets(swords, [TargetObject(myr)])
    scenario.at(Phase.PRECOMBAT_MAIN, active=P1)
    state = scenario.build()
    run_script(state, pass_(P1), pass_(P0))
    (exiled,) = records(state, ObjectExiled)
    assert exiled.obj == myr and names(state, EXILE) == ["Darksteel Myr"]
    assert state.battlefield == []


def test_702_12_indestructible_doesnt_stop_targeting() -> None:
    """Test Shatter offers Darksteel Relic; Swords to Plowshares offers Darksteel Myr; Fiery
    Confluence's "destroy target artifact" mode is offered with only the Relic as an artifact."""
    scenario = Scenario(2)
    (relic,) = scenario.battlefield(P0, ["Darksteel Relic"])
    (shatter,) = scenario.hand(P1, ["Test Shatter"])
    scenario.mana(P1, R, R)
    scenario.at(Phase.PRECOMBAT_MAIN, active=P1)
    state = scenario.build()
    run_script(state, cast(shatter, P1))
    assert target_choices(state) == (ObjectOption(relic),)

    scenario = Scenario(2)
    (myr,) = scenario.battlefield(P0, ["Darksteel Myr"])
    (swords,) = scenario.hand(P1, ["Swords to Plowshares"])
    scenario.mana(P1, W)
    scenario.at(Phase.PRECOMBAT_MAIN, active=P1)
    state = scenario.build()
    run_script(state, cast(swords, P1))
    assert target_choices(state) == (ObjectOption(myr),)

    scenario = Scenario(2)
    (relic,) = scenario.battlefield(P0, ["Darksteel Relic"])
    (confluence,) = scenario.hand(P1, ["Fiery Confluence"])
    scenario.mana(P1, R, R, R, R)
    scenario.at(Phase.PRECOMBAT_MAIN, active=P1)
    state = scenario.build()
    run_script(state, cast(confluence, P1), choose_modes(2, 2, 2))
    assert target_choices(state) == (ObjectOption(relic),)
