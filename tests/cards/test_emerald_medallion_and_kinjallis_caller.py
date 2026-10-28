"""Emerald Medallion ({2}, Artifact: "Green spells you cast cost {1} less to cast.") and
Kinjalli's Caller ({W}, Creature — Human Cleric 0/3: "Dinosaur spells you cast cost {1} less to
cast.").

Oracle text and rulings checked against the Scryfall snapshot of 2026-10-26
(``tools/excerpts/cards.json``). The rulings, and the tests for each:

Emerald Medallion (2023-07-28):

1. Additional costs and increases (Thalia, Guardian of Thraben) are applied before reductions.
   (tests/rules/test_601_2f_cost_modifiers.py, ``test_601_2f_modifiers_apply_in_the_rules_order``,
   with Test Thorn as the increase.)
2. With {X} in the mana cost, X is chosen before the total cost is calculated.
   (``test_601_2f_x_is_chosen_before_the_reduction``.)
3. It changes neither the mana cost nor the mana value, only the total cost.
   (``test_202_3_mana_value_isnt_changed``.)
4. It reduces only the generic mana component, never the colored mana.
   (``test_118_7a_it_cant_reduce_colored_mana``.)
5. The reduction can apply to alternative costs such as flashback costs: no M2 card has an
   alternative cost with mana in it (601.2f's base is "the mana cost or alternative cost"; the
   first is flashback, M4), so this ruling is tested with that card.

Kinjalli's Caller:

1. (2017-09-29) Start with the mana cost or alternative cost, add increases, then apply
   reductions; the mana value is unchanged.
   (``test_kinjallis_caller_applies_after_an_increase_and_keeps_the_mana_value``.)
2. (2018-01-19) A "[subtype] spell" is only a spell with that subtype.
   (``test_kinjallis_caller_only_dinosaur_spells``.)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from resolve.cards.definitions.cost_reducers import EMERALD_MEDALLION, KINJALLIS_CALLER
from resolve.cards.registry import CardDefinition, default_registry
from resolve.data.cards import load_card_excerpt
from resolve.data.mana_cost import ManaCost, parse_mana_cost
from resolve.data.types import CardType, Color
from resolve.effects.characteristics import characteristics
from resolve.engine.api import view_for
from resolve.events.spells import SpellCast
from resolve.state.ids import PlayerId
from resolve.state.mana import ManaType
from resolve.state.turn import Phase
from tests.casting_support import cast, records
from tests.scenario import Scenario, run_script

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)
G = ManaType.GREEN
EXCERPT = Path(__file__).resolve().parents[2] / "tools" / "excerpts" / "cards.json"


def cost(text: str) -> ManaCost:
    return parse_mana_cost(text)


@pytest.mark.parametrize(
    ("definition", "text"),
    [
        (EMERALD_MEDALLION, "Green spells you cast cost {1} less to cast."),
        (KINJALLIS_CALLER, "Dinosaur spells you cast cost {1} less to cast."),
    ],
)
def test_their_definitions_are_their_oracle_text(definition: CardDefinition, text: str) -> None:
    assert default_registry().get(definition.name) is definition
    (ability,) = definition.abilities
    assert ability.text == text
    card = load_card_excerpt(EXCERPT).get(definition.name)
    assert card.faces[0].oracle_text == text


def test_their_characteristics_come_from_the_card_data() -> None:
    scenario = Scenario(2)
    medallion, caller = scenario.battlefield(P0, ["Emerald Medallion", "Kinjalli's Caller"])
    state = scenario.build()
    chars = characteristics(state, medallion)
    assert (chars.mana_cost, chars.colors, chars.card_types) == (
        cost("{2}"),
        (),
        (CardType.ARTIFACT,),
    )
    chars = characteristics(state, caller)
    assert (chars.mana_cost, chars.colors) == (cost("{W}"), (Color.WHITE,))
    assert chars.subtypes == ("Human", "Cleric")
    assert (chars.power, chars.toughness) == (0, 3)


def test_emerald_medallion_doesnt_reduce_a_colorless_spell() -> None:
    """Sol Ring ({1}) is colorless, not green (105.2): it still costs {1}."""
    scenario = Scenario(2)
    (ring,) = scenario.hand(P0, ["Sol Ring"])
    scenario.battlefield(P0, ["Emerald Medallion", "Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(ring, P0))
    (payment,) = view_for(state, P0).payments
    assert payment.cost == cost("{1}")


def test_kinjallis_caller_only_dinosaur_spells() -> None:
    """With Kinjalli's Caller, Test Raptor ({1}{G}, a Dinosaur) costs {G}; Grizzly Bears
    ({1}{G}, a Bear) still costs {1}{G} (205.3: a "Dinosaur spell" has that subtype). P1's
    Caller doesn't reduce P0's Raptor ("you cast")."""
    scenario = Scenario(2)
    raptor, bears = scenario.hand(P0, ["Test Raptor", "Grizzly Bears"])
    scenario.battlefield(P0, ["Kinjalli's Caller"])
    scenario.mana(P0, G)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(raptor, P0))
    (cast_event,) = records(state, SpellCast)
    assert cast_event.total_cost == cost("{G}")

    scenario = Scenario(2)
    (bears,) = scenario.hand(P0, ["Grizzly Bears"])
    scenario.battlefield(P0, ["Kinjalli's Caller", "Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(bears, P0))
    (payment,) = view_for(state, P0).payments
    assert payment.cost == cost("{1}{G}")

    scenario = Scenario(3)
    (raptor,) = scenario.hand(P0, ["Test Raptor"])
    scenario.battlefield(P0, ["Forest"])
    scenario.battlefield(P1, ["Kinjalli's Caller"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(raptor, P0))
    (payment,) = view_for(state, P0).payments
    assert payment.cost == cost("{1}{G}")


def test_kinjallis_caller_applies_after_an_increase_and_keeps_the_mana_value() -> None:
    """Test Raptor ({1}{G}) with Test Thorn (+{1}) and Kinjalli's Caller (-{1}): {2}{G}, then
    {1}{G} (601.2f). The Raptor's mana value stays 2 (202.3). With Test Thorn alone it costs
    {2}{G}."""
    scenario = Scenario(2)
    (raptor,) = scenario.hand(P0, ["Test Raptor"])
    scenario.battlefield(P0, ["Test Thorn", "Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(raptor, P0))
    (payment,) = view_for(state, P0).payments
    assert payment.cost == cost("{2}{G}")

    scenario = Scenario(2)
    (raptor,) = scenario.hand(P0, ["Test Raptor"])
    scenario.battlefield(P0, ["Kinjalli's Caller", "Test Thorn"])
    scenario.mana(P0, G, G)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(raptor, P0))
    (cast_event,) = records(state, SpellCast)
    assert cast_event.total_cost == cost("{1}{G}")
    assert characteristics(state, cast_event.spell).mana_value == 2
