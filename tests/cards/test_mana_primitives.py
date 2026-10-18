"""The first primitives: ``TapSelfCost``, ``AddMana`` and ``ActivatedManaAbility``."""

from __future__ import annotations

import pytest

from resolve.cards.primitives.abilities import ActivatedManaAbility, intrinsic_mana_ability
from resolve.cards.primitives.costs import TapSelfCost
from resolve.cards.primitives.effects import AddMana
from resolve.events.mana import ManaAdded
from resolve.events.permanents import PermanentTapped
from resolve.state.ids import PlayerId
from resolve.state.mana import Mana, ManaType
from tests.scenario import Scenario

P0, P1 = PlayerId(0), PlayerId(1)
G, R = ManaType.GREEN, ManaType.RED


def test_107_5_118_3_tap_self_cost_needs_an_untapped_permanent() -> None:
    scenario = Scenario(2)
    untapped, tapped = scenario.battlefield(P0, ["Forest", "Forest"])
    (in_hand,) = scenario.hand(P0, ["Forest"])
    scenario.tap(tapped)
    state = scenario.build()
    cost = TapSelfCost()
    assert cost.can_pay(state, untapped, P0)
    assert not cost.can_pay(state, tapped, P0)
    assert not cost.can_pay(state, in_hand, P0)  # 110.5d: only permanents can be tapped
    assert cost.payment(state, untapped, P0) == (
        PermanentTapped(obj=untapped, rules=("107.5", "701.26a")),
    )
    assert cost.text == "{T}"


def test_106_3_add_mana_adds_mana_from_its_source() -> None:
    scenario = Scenario(2)
    (forest,) = scenario.battlefield(P1, ["Forest"])
    state = scenario.build()
    effect = AddMana((G, R))
    assert effect.events(state, forest, P1) == (
        ManaAdded(player=P1, mana=(Mana(G, forest), Mana(R, forest)), rules=("106.3", "106.4")),
    )
    assert effect.text == "Add {G}{R}."
    with pytest.raises(ValueError, match="at least one"):
        AddMana(())


def test_602_2_only_the_controller_can_activate() -> None:
    scenario = Scenario(2)
    (forest,) = scenario.battlefield(P1, ["Forest"])
    state = scenario.build()
    ability = ActivatedManaAbility((TapSelfCost(),), AddMana((G,)))
    assert ability.can_activate(state, forest, P1)
    assert not ability.can_activate(state, forest, P0)
    assert ability.text == "{T}: Add {G}."


@pytest.mark.parametrize(
    ("land_type", "mana"),
    [("Plains", "W"), ("Island", "U"), ("Swamp", "B"), ("Mountain", "R"), ("Forest", "G")],
)
def test_305_6_intrinsic_mana_abilities(land_type: str, mana: str) -> None:
    ability = intrinsic_mana_ability(land_type)
    assert ability == ActivatedManaAbility((TapSelfCost(),), AddMana((ManaType(mana),)))
    with pytest.raises(KeyError):
        intrinsic_mana_ability("Desert")  # not a basic land type
