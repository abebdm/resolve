"""What the views show of permanents' abilities and of the payments under way (design.md §9).

Both are public (400.2): every player sees the permanents on the battlefield and their abilities,
and a spell being cast is on the stack (601.2a) with its cost announced as it is paid (601.2f-h);
a mana ability being activated is announced too (602.2a, 605.3a). An agent (the auto-payer,
``resolve.agents.autopay``) plans a payment from these alone (rule 4).

- ``ObjectView.abilities``: for each permanent, its abilities by index (what an
  ``ActivateAbilityOption`` names), text, the mana part of the activation cost (602.2b) and the
  mana a mana ability adds now (106.1a; 903.4 for "your commander's color identity", which
  adds nothing without a commander, 903.4f and 106.5), with its restriction (106.6). Objects
  elsewhere show none: a card in a hand may be hidden (402.3).
- ``PlayerView.payments``: the costs being paid, outermost first (a spell's cost, then the mana
  cost of a mana ability activated while paying it, 605.3a), each with its purpose and the
  restrictions that allow spending mana on it (106.6).
"""

from __future__ import annotations

from resolve.cards.primitives.restrictions import SpendOnlyOnSubtype
from resolve.cards.primitives.words import SubtypeWord
from resolve.data.mana_cost import parse_mana_cost
from resolve.data.types import Color
from resolve.decisions.kinds import DecisionKind
from resolve.engine.api import view_for
from resolve.engine.view import AbilityView, ManaOutput, PaymentView
from resolve.state.config import GameConfig
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import ForAbility, ForSpell, ManaType
from resolve.state.turn import Phase
from tests.casting_support import activate, activate_with_priority, cast, choose_color
from tests.game_fixtures import request_of
from tests.scenario import Scenario, run_script

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)
W, U, B, R, G, C = (
    ManaType.WHITE,
    ManaType.BLUE,
    ManaType.BLACK,
    ManaType.RED,
    ManaType.GREEN,
    ManaType.COLORLESS,
)
DINOSAUR = SpendOnlyOnSubtype(SubtypeWord("Dinosaur"))


def shown(state: GameState, viewer: PlayerId, obj: ObjectId) -> tuple[AbilityView, ...]:
    (seen,) = [o for o in view_for(state, viewer).battlefield if o.id == obj]
    return seen.abilities


def test_a_basic_lands_intrinsic_ability_is_shown_to_every_player() -> None:
    """305.6: a Forest has "{T}: Add {G}."; the battlefield is public (400.2)."""
    scenario = Scenario(3)
    (forest,) = scenario.battlefield(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    expected = (AbilityView(0, "{T}: Add {G}.", None, ManaOutput(fixed=(G,))),)
    for viewer in (P0, P1, P2):
        assert shown(state, viewer, forest) == expected


def test_602_2b_a_mana_cost_in_the_activation_cost_is_shown() -> None:
    scenario = Scenario(2)
    signet, ring = scenario.battlefield(P0, ["Selesnya Signet", "Sol Ring"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    assert shown(state, P1, signet) == (
        AbilityView(0, "{1}, {T}: Add {G}{W}.", parse_mana_cost("{1}"), ManaOutput(fixed=(G, W))),
    )
    assert shown(state, P1, ring) == (
        AbilityView(0, "{T}: Add {C}{C}.", None, ManaOutput(fixed=(C, C))),
    )


def test_903_4_command_towers_choice_is_its_controllers_commanders_identity() -> None:
    """Avacyn's Pilgrim is green and white (903.4): W or G, in WUBRG order. The opponent's
    commander doesn't count (903.3: "your commander")."""
    scenario = Scenario(2, config=GameConfig.commander_game())
    scenario.commander(P0, "Avacyn's Pilgrim")
    scenario.commander(P1, "Hill Giant")
    (tower,) = scenario.battlefield(P0, ["Command Tower"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    (ability,) = shown(state, P1, tower)
    assert ability.mana == ManaOutput(one_of=(W, G))


def test_903_4f_without_a_commander_command_tower_shows_that_it_adds_nothing() -> None:
    """106.5: mana of an undefined type isn't added, so there is no color to choose."""
    scenario = Scenario(2)
    (tower,) = scenario.battlefield(P0, ["Command Tower"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    (ability,) = shown(state, P0, tower)
    assert ability.mana == ManaOutput()


def test_106_6_a_restriction_on_the_mana_is_shown() -> None:
    scenario = Scenario(2)
    (lorekeeper,) = scenario.battlefield(P0, ["Ixalli's Lorekeeper"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    (ability,) = shown(state, P1, lorekeeper)
    assert ability.mana == ManaOutput(one_of=(W, U, B, R, G), restriction=DINOSAUR)


def test_objects_off_the_battlefield_show_no_abilities() -> None:
    """A card in a hand may be hidden (402.3); only permanents show their abilities. Even its
    owner sees none for it: the view shows abilities of permanents only."""
    scenario = Scenario(2)
    (ring,) = scenario.hand(P0, ["Sol Ring"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    (seen,) = view_for(state, P0).players[0].hand
    assert seen.id == ring and seen.abilities == ()


def test_no_payment_is_under_way_at_priority() -> None:
    scenario = Scenario(2)
    scenario.battlefield(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    assert view_for(state, P0).payments == ()


def test_601_2g_a_spells_cost_is_shown_to_every_player_while_it_is_paid() -> None:
    """Grizzly Bears ({1}{G}) on the stack (601.2a): its total cost (601.2f) is being paid.
    Once cast (601.2i), no payment is under way."""
    scenario = Scenario(3)
    forest, other = scenario.battlefield(P0, ["Forest", "Forest"])
    (bears,) = scenario.hand(P0, ["Grizzly Bears"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(bears, P0))
    spell = state.stack[-1]
    expected = (PaymentView(P0, parse_mana_cost("{1}{G}"), ForSpell(spell)),)
    for viewer in (P0, P1, P2):
        assert view_for(state, viewer).payments == expected
    run_script(state, activate(forest), activate(other))
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION
    assert view_for(state, P1).payments == ()


def test_605_3a_a_mana_abilitys_cost_paid_while_paying_a_spell_comes_after_the_spells() -> None:
    """Casting Grizzly Bears, P0 activates Selesnya Signet: its {1} is paid inside the spell's
    payment (605.3a), so the view lists the spell's cost, then the Signet's."""
    scenario = Scenario(2)
    signet, _ = scenario.battlefield(P0, ["Selesnya Signet", "Forest"])
    (bears,) = scenario.hand(P0, ["Grizzly Bears"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(bears, P0), activate(signet))
    spell = state.stack[-1]
    assert request_of(state).source == signet
    assert view_for(state, P1).payments == (
        PaymentView(P0, parse_mana_cost("{1}{G}"), ForSpell(spell)),
        PaymentView(P0, parse_mana_cost("{1}"), ForAbility(signet, 0)),
    )


def test_605_3a_a_mana_abilitys_cost_paid_with_priority_is_shown() -> None:
    scenario = Scenario(2)
    signet, _ = scenario.battlefield(P0, ["Selesnya Signet", "Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, activate_with_priority(signet))
    assert view_for(state, P0).payments == (
        PaymentView(P0, parse_mana_cost("{1}"), ForAbility(signet, 0)),
    )


def test_106_1a_a_color_chosen_while_paying_belongs_to_the_spells_payment() -> None:
    """Command Tower activated while paying for Grizzly Bears: as its color is chosen (605.3b),
    the payment under way is the spell's (Command Tower's ability has no mana cost)."""
    scenario = Scenario(2, config=GameConfig.commander_game())
    scenario.commander(P0, "Avacyn's Pilgrim")
    tower, _ = scenario.battlefield(P0, ["Command Tower", "Forest"])
    (bears,) = scenario.hand(P0, ["Grizzly Bears"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(bears, P0), activate(tower))
    assert request_of(state).kind is DecisionKind.CHOOSE_COLOR
    spell = state.stack[-1]
    assert view_for(state, P0).payments == (
        PaymentView(P0, parse_mana_cost("{1}{G}"), ForSpell(spell)),
    )
    run_script(state, choose_color(Color.GREEN))


def test_106_6_spendable_lists_the_restrictions_that_allow_spending_on_the_payment() -> None:
    """Ixalli's Lorekeeper's mana may be spent on a Dinosaur spell (Test Raptor) but not on
    Grizzly Bears; the engine says which (``spendable``), from the abilities on the battlefield
    and the mana in the pool alike."""
    for name, spendable in (("Test Raptor", (DINOSAUR,)), ("Grizzly Bears", ())):
        scenario = Scenario(2)
        scenario.battlefield(P0, ["Ixalli's Lorekeeper", "Forest", "Forest"])
        (card,) = scenario.hand(P0, [name])
        scenario.at(Phase.PRECOMBAT_MAIN)
        state = scenario.build()
        run_script(state, cast(card, P0))
        (payment,) = view_for(state, P1).payments
        assert payment.spendable == spendable, name

    # Restricted mana already in the pool counts too, with no source left on the battlefield.
    scenario = Scenario(2)
    (raptor,) = scenario.hand(P0, ["Test Raptor"])
    scenario.battlefield(P0, ["Forest"])
    scenario.mana(P0, G, restriction=DINOSAUR)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(raptor, P0))
    (payment,) = view_for(state, P0).payments
    assert payment.spendable == (DINOSAUR,)
