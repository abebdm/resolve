"""Llanowar Elves ("{T}: Add {G}.") and Avacyn's Pilgrim ("{T}: Add {W}."), 1/1 creatures for {G}.

Oracle text checked against the Scryfall snapshot of 2026-10-21 (``tools/excerpts/cards.json``),
which has no rulings for them. Their abilities are creatures' {T} abilities (302.6: see
``tests/rules/test_302_6_summoning_sickness.py``); a creature controlled since its controller's
turn began taps for mana with priority or while paying (605.3a).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from resolve.cards.definitions.mana_creatures import AVACYNS_PILGRIM, LLANOWAR_ELVES
from resolve.cards.registry import CardDefinition, default_registry
from resolve.data.cards import load_card_excerpt
from resolve.events.spells import SpellCast
from resolve.state.ids import PlayerId
from resolve.state.mana import Mana, ManaType
from resolve.state.turn import Phase
from tests.casting_support import activate, activate_with_priority, cast, records
from tests.game_fixtures import ELVES
from tests.scenario import Scenario, run_script

P0 = PlayerId(0)
EXCERPT = Path(__file__).resolve().parents[2] / "tools" / "excerpts" / "cards.json"
CASES = [
    (LLANOWAR_ELVES, "{T}: Add {G}.", ManaType.GREEN),
    (AVACYNS_PILGRIM, "{T}: Add {W}.", ManaType.WHITE),
]


@pytest.mark.parametrize(("definition", "text", "mana"), CASES)
def test_their_definitions_are_their_oracle_text(
    definition: CardDefinition, text: str, mana: ManaType
) -> None:
    assert default_registry().get(definition.name) is definition
    (ability,) = definition.abilities
    assert ability.text == text
    card = load_card_excerpt(EXCERPT).get(definition.name)
    assert card.faces[0].oracle_text == text
    assert card.faces[0].mana_cost == "{G}"


@pytest.mark.parametrize(("definition", "text", "mana"), CASES)
def test_605_3a_it_taps_for_its_mana_with_priority(
    definition: CardDefinition, text: str, mana: ManaType
) -> None:
    scenario = Scenario(2)
    (creature,) = scenario.battlefield(P0, [definition.name])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, activate_with_priority(creature))
    assert state.player(P0).mana_pool == [Mana(mana, creature)]
    assert state.objects[creature].tapped


def test_605_3a_avacyns_pilgrim_and_a_forest_pay_for_a_white_and_green_cost() -> None:
    """Savannah Lions ({W}) paid by the Pilgrim's {W}."""
    scenario = Scenario(2)
    (lions,) = scenario.hand(P0, ["Savannah Lions"])
    (pilgrim,) = scenario.battlefield(P0, ["Avacyn's Pilgrim"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(lions, P0), activate(pilgrim))
    (cast_event,) = records(state, SpellCast)
    assert cast_event.mana_spent == (Mana(ManaType.WHITE, pilgrim),)


def test_the_fixture_decks_use_the_real_llanowar_elves() -> None:
    assert ELVES.definitions == (LLANOWAR_ELVES,)
