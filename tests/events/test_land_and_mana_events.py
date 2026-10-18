"""Events for lands, tapping and mana (305.1, 701.26, 106.4, 500.5): what they change and refuse."""

from __future__ import annotations

import pytest

from resolve.effects.characteristics import characteristics
from resolve.errors import EngineError, NotImplementedRule
from resolve.events.mana import ManaAdded, ManaPoolEmptied
from resolve.events.permanents import (
    DamageRemoved,
    LandPlayed,
    PermanentDestroyed,
    PermanentsUntapped,
    PermanentTapped,
    PutIntoGraveyard,
)
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.invariants import invariant_violations
from resolve.state.mana import Mana, ManaType
from resolve.state.turn import Phase, Step
from resolve.state.zones import BATTLEFIELD
from tests.scenario import Scenario, ScenarioError

P0, P1 = PlayerId(0), PlayerId(1)
G = Mana(ManaType.GREEN)


def test_land_played_moves_the_land_and_counts_it() -> None:
    scenario = Scenario(2)
    (forest,) = scenario.hand(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    applied = LandPlayed(player=P0, card=forest, rules=("305.1",)).apply(state)
    assert isinstance(applied, LandPlayed) and applied.played is not None
    obj = state.objects[applied.played]
    assert obj.zone == BATTLEFIELD and obj.controller == P0 and not obj.tapped
    assert state.turn is not None and state.turn.lands_played == 1


def test_land_played_refuses_impossible_plays() -> None:
    scenario = Scenario(2)
    (theirs,) = scenario.hand(P1, ["Forest"])
    (mine,) = scenario.hand(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    with pytest.raises(EngineError, match="outside their turn"):
        LandPlayed(player=P1, card=theirs, rules=("305.1",)).apply(state)
    with pytest.raises(EngineError, match="isn't in player 0's hand"):
        LandPlayed(player=P0, card=theirs, rules=("305.1",)).apply(state)
    with pytest.raises(EngineError, match="without its outcome"):
        LandPlayed(player=P0, card=mine, played=ObjectId(1), rules=("305.1",)).apply(state)
    assert state.battlefield == []


def test_701_26_tapping_and_untapping() -> None:
    scenario = Scenario(2)
    first, second = scenario.battlefield(P0, ["Forest", "Forest"])
    (in_hand,) = scenario.hand(P0, ["Forest"])
    state = scenario.build()
    PermanentTapped(obj=first, rules=("701.26a",)).apply(state)
    assert state.objects[first].tapped
    with pytest.raises(EngineError, match="already tapped"):
        PermanentTapped(obj=first, rules=("701.26a",)).apply(state)
    with pytest.raises(EngineError, match="isn't a permanent"):
        PermanentTapped(obj=in_hand, rules=("701.26a",)).apply(state)
    with pytest.raises(EngineError, match="isn't tapped"):
        PermanentsUntapped(objs=(first, second), rules=("701.26b",)).apply(state)
    assert state.objects[first].tapped  # nothing changed: checked before untapping any
    PermanentsUntapped(objs=(first,), rules=("701.26b",)).apply(state)
    assert not state.objects[first].tapped


def test_106_4_mana_goes_into_the_pool_and_empties_all_at_once() -> None:
    state = Scenario(2).build()
    ManaAdded(player=P1, mana=(G, G), rules=("106.4",)).apply(state)
    ManaAdded(player=P1, mana=(Mana(ManaType.RED),), rules=("106.4",)).apply(state)
    assert state.player(P1).mana_pool == [G, G, Mana(ManaType.RED)]
    with pytest.raises(EngineError, match="pool isn't"):
        ManaPoolEmptied(player=P1, mana=(G,), rules=("500.5",)).apply(state)
    ManaPoolEmptied(player=P1, mana=(G, G, Mana(ManaType.RED)), rules=("500.5",)).apply(state)
    assert state.player(P1).mana_pool == []
    with pytest.raises(EngineError, match="needs some mana"):
        ManaAdded(player=P1, mana=(), rules=("106.4",)).apply(state)


def test_the_scenario_taps_permanents_and_fills_pools() -> None:
    scenario = Scenario(2)
    (forest,) = scenario.battlefield(P0, ["Forest"])
    (in_hand,) = scenario.hand(P0, ["Forest"])
    scenario.tap(forest).mana(P1, ManaType.GREEN, ManaType.BLUE)
    with pytest.raises(ScenarioError, match="isn't a permanent"):
        scenario.tap(in_hand)
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    assert state.objects[forest].tapped
    assert state.player(P1).mana_pool == [G, Mana(ManaType.BLUE)]


def test_invariants_catch_status_off_the_battlefield_and_unknown_mana_sources() -> None:
    scenario = Scenario(2)
    (in_hand,) = scenario.hand(P0, ["Forest"])
    state = scenario.build()
    state.objects[in_hand].tapped = True
    assert any("110.5d" in p for p in invariant_violations(state))
    state.objects[in_hand].tapped = False
    state.player(P1).mana_pool.append(Mana(ManaType.GREEN, ObjectId(500)))
    assert any("unknown source 500" in p for p in invariant_violations(state))


def test_701_8a_destroying_and_704_5f_putting_into_the_graveyard() -> None:
    scenario = Scenario(2)
    bears, giant = scenario.battlefield(P1, ["Grizzly Bears", "Hill Giant"], owner=P0)
    (in_hand,) = scenario.hand(P0, ["Forest"])
    state = scenario.build()
    destroyed = PermanentDestroyed(obj=bears, rules=("701.8a",)).apply(state)
    moved = PutIntoGraveyard(obj=giant, rules=("704.5f",)).apply(state)
    assert isinstance(destroyed, PermanentDestroyed) and isinstance(moved, PutIntoGraveyard)
    assert state.player(P0).graveyard == [destroyed.moved, moved.moved]  # the owner's
    assert state.battlefield == []
    with pytest.raises(EngineError, match="isn't a permanent"):
        PermanentDestroyed(obj=in_hand, rules=("701.8a",)).apply(state)


def test_514_2_damage_removed_clears_damage_and_refuses_non_permanents() -> None:
    scenario = Scenario(2)
    (bears,) = scenario.battlefield(P0, ["Grizzly Bears"])
    (in_hand,) = scenario.hand(P0, ["Forest"])
    scenario.damage(bears, 1)
    with pytest.raises(ScenarioError, match="isn't a permanent"):
        scenario.damage(in_hand, 1)
    with pytest.raises(ScenarioError, match="negative"):
        scenario.damage(bears, -1)
    state = scenario.build()
    with pytest.raises(EngineError, match="isn't a permanent"):
        DamageRemoved(objs=(bears, in_hand), rules=("514.2",)).apply(state)
    assert state.objects[bears].damage == 1
    DamageRemoved(objs=(bears,), rules=("514.2",)).apply(state)
    assert state.objects[bears].damage == 0


def test_invariants_catch_damage_off_the_battlefield_or_negative() -> None:
    scenario = Scenario(2)
    (in_hand,) = scenario.hand(P0, ["Forest"])
    (bears,) = scenario.battlefield(P0, ["Grizzly Bears"])
    state = scenario.build()
    state.objects[in_hand].damage = 1
    state.objects[bears].damage = -1
    problems = invariant_violations(state)
    assert any("120.6" in p for p in problems)
    assert any("negative damage" in p for p in problems)


def test_208_3_a_noncreature_permanent_has_no_power_or_toughness() -> None:
    """Even with numbers printed on it (a Vehicle); off the battlefield it has them."""
    scenario = Scenario(2)
    (on_field,) = scenario.battlefield(P0, ["Test Wagon"])
    (in_hand,) = scenario.hand(P0, ["Test Wagon"])
    state = scenario.build()
    assert (characteristics(state, on_field).power, characteristics(state, on_field).toughness) == (
        None,
        None,
    )
    assert (characteristics(state, in_hand).power, characteristics(state, in_hand).toughness) == (
        3,
        3,
    )


def test_208_3_power_and_toughness_of_noncreatures_are_none() -> None:
    scenario = Scenario(2)
    (forest,) = scenario.battlefield(P0, ["Forest"])
    (star,) = scenario.hand(P0, ["Test Star"])
    state = scenario.build()
    chars = characteristics(state, forest)
    assert (chars.power, chars.toughness) == (None, None)
    star_chars = characteristics(state, star)  # computing is fine; reading the star isn't
    with pytest.raises(NotImplementedRule):
        _ = star_chars.power
