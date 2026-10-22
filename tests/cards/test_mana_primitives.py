"""Mana primitives: ``TapSelfCost``, ``ManaPaymentCost``, ``AddMana``, ``AddManaOfAnyColor``,
``SpendOnlyOnSubtype``, ``ControlsAtLeast`` and ``ActivatedManaAbility``."""

from __future__ import annotations

import pytest

from resolve.cards.primitives.abilities import ActivatedManaAbility, intrinsic_mana_ability
from resolve.cards.primitives.conditions import ControlsAtLeast
from resolve.cards.primitives.costs import ManaPaymentCost, TapSelfCost
from resolve.cards.primitives.effects import AddMana, AddManaOfAnyColor
from resolve.cards.primitives.restrictions import SpendOnlyOnSubtype
from resolve.cards.primitives.words import SubtypeWord
from resolve.data.mana_cost import parse_mana_cost
from resolve.data.types import CardType, Color
from resolve.errors import EngineError
from resolve.events.mana import ManaAdded
from resolve.events.permanents import PermanentTapped
from resolve.state.config import GameConfig
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


def test_602_2b_a_mana_payment_cost_is_paid_while_activating_not_up_front() -> None:
    """Whether a mana cost can be paid is known only once the player has paid it (601.2g-h,
    605.3a), so ``can_pay`` doesn't refuse it even with no mana at all; it has no payment events
    of its own (``PayCosts`` pays it)."""
    scenario = Scenario(2)
    (signet,) = scenario.battlefield(P0, ["Selesnya Signet"])
    state = scenario.build()
    cost = ManaPaymentCost(parse_mana_cost("{1}"))
    assert cost.text == "{1}"
    assert cost.can_pay(state, signet, P0)
    with pytest.raises(EngineError):
        cost.payment(state, signet, P0)


def test_602_2b_an_activation_cost_has_at_most_one_mana_cost() -> None:
    one = ManaPaymentCost(parse_mana_cost("{1}"))
    with pytest.raises(ValueError, match=r"602\.2b"):
        ActivatedManaAbility((one, one, TapSelfCost()), AddMana((G,)))
    ability = ActivatedManaAbility((one, TapSelfCost()), AddMana((G, ManaType.WHITE)))
    assert ability.mana_cost == one
    assert ability.text == "{1}, {T}: Add {G}{W}."
    assert ActivatedManaAbility((TapSelfCost(),), AddMana((G,))).mana_cost is None


def test_106_1a_add_mana_of_any_color_offers_all_five_colors_and_adds_the_chosen_one() -> None:
    scenario = Scenario(2)
    (source,) = scenario.battlefield(P1, ["Ixalli's Lorekeeper"])
    state = scenario.build()
    effect = AddManaOfAnyColor()
    assert effect.text == "Add one mana of any color."
    assert effect.colors(state, source, P1) == tuple(Color)
    assert effect.events(state, source, P1, Color.BLUE) == (
        ManaAdded(
            player=P1, mana=(Mana(ManaType.BLUE, source),), rules=("106.1a", "106.3", "106.4")
        ),
    )
    assert effect.events(state, source, P1, None) == ()  # 106.5


def test_903_4_commander_identity_mana_reads_the_controllers_commanders() -> None:
    """Two players: P0's commander is green and white, P1 has none (903.4f: no color to choose)."""
    scenario = Scenario(2, config=GameConfig.commander_game())
    scenario.commander(P0, "Avacyn's Pilgrim")
    (tower,) = scenario.battlefield(P0, ["Command Tower"])
    (theirs,) = scenario.battlefield(P1, ["Command Tower"])
    state = scenario.build()
    effect = AddManaOfAnyColor(commander_identity=True)
    assert effect.text == "Add one mana of any color in your commander's color identity."
    assert effect.colors(state, tower, P0) == (Color.WHITE, Color.GREEN)
    assert effect.colors(state, theirs, P1) == ()


def test_106_6_restricted_mana_carries_its_restriction() -> None:
    scenario = Scenario(2)
    (source,) = scenario.battlefield(P0, ["Ixalli's Lorekeeper"])
    state = scenario.build()
    restriction = SpendOnlyOnSubtype(SubtypeWord("Dinosaur"))
    effect = AddManaOfAnyColor(restriction=restriction)
    assert effect.text == (
        "Add one mana of any color. Spend this mana only to cast a Dinosaur spell or activate an "
        "ability of a Dinosaur source."
    )
    (added,) = effect.events(state, source, P0, Color.RED)
    assert isinstance(added, ManaAdded)
    assert added.mana == (Mana(R, source, restriction),)
    # 106.6: the restriction doesn't change the mana's type.
    assert added.mana[0].type is R
    assert SpendOnlyOnSubtype(SubtypeWord("Elf")).text.startswith(
        "Spend this mana only to cast an Elf spell or activate an ability of an Elf source"
    )


def test_602_5_controls_at_least_counts_the_players_permanents_of_the_type() -> None:
    scenario = Scenario(2)
    temple, *_ = scenario.battlefield(P0, ["Temple of the False God", "Forest", "Sol Ring"])
    scenario.battlefield(P1, ["Forest", "Forest"])
    state = scenario.build()
    assert ControlsAtLeast(2, CardType.LAND).met(state, temple, P0)
    assert not ControlsAtLeast(3, CardType.LAND).met(state, temple, P0)
    assert ControlsAtLeast(1, CardType.ARTIFACT).met(state, temple, P0)
    assert ControlsAtLeast(2, CardType.LAND).met(state, temple, P1)
    assert (
        ControlsAtLeast(5, CardType.LAND).text == "Activate only if you control five or more lands."
    )
    with pytest.raises(ValueError):
        ControlsAtLeast(0, CardType.LAND)


def test_602_5_an_unmet_condition_forbids_activation() -> None:
    scenario = Scenario(2)
    (temple,) = scenario.battlefield(P0, ["Temple of the False God"])
    state = scenario.build()
    ability = ActivatedManaAbility(
        (TapSelfCost(),), AddMana((ManaType.COLORLESS,)), ControlsAtLeast(1, CardType.LAND)
    )
    assert ability.can_activate(state, temple, P0)
    stricter = ActivatedManaAbility(
        (TapSelfCost(),), AddMana((ManaType.COLORLESS,)), ControlsAtLeast(2, CardType.LAND)
    )
    assert not stricter.can_activate(state, temple, P0)
    assert stricter.text == "{T}: Add {C}. Activate only if you control two or more lands."
