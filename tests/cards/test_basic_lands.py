"""Plains, Island, Swamp, Mountain and Forest.

Oracle text (Scryfall): only reminder text, "({T}: Add {W}.)" and so on, which isn't rules
text. Their mana ability is intrinsic to the basic land type (305.6); they are basic (305.8),
and are played, never cast (305.1, 305.9). The card data has no rulings for them that change
any of this.
"""

from __future__ import annotations

import pytest

from resolve.agents.scripted import choose
from resolve.cards.definitions import basic_lands
from resolve.cards.registry import default_registry
from resolve.data.cards import CardDatabase, parse_oracle_cards
from resolve.data.decklist import parse_decklist
from resolve.data.types import CardType, Supertype
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import ActivateAbilityOption, ChooseOne, PassOption, PlayLandOption
from resolve.effects.characteristics import characteristics
from resolve.engine.deck import build_deck
from resolve.state.ids import PlayerId
from resolve.state.mana import Mana, ManaType
from resolve.state.turn import Phase
from tests import scryfall_fixtures as fx
from tests.game_fixtures import request_of
from tests.scenario import Scenario, run_script

P0 = PlayerId(0)
LANDS = [
    ("Plains", ManaType.WHITE, fx.PLAINS),
    ("Island", ManaType.BLUE, fx.ISLAND),
    ("Swamp", ManaType.BLACK, fx.SWAMP),
    ("Mountain", ManaType.RED, fx.MOUNTAIN),
    ("Forest", ManaType.GREEN, fx.FOREST),
]


def test_all_five_are_registered_without_printed_abilities() -> None:
    registry = default_registry()
    for name, _, _ in LANDS:
        definition = registry.get(name)
        assert definition.abilities == ()
    assert [d.name for d in basic_lands.DEFINITIONS] == [name for name, _, _ in LANDS]


@pytest.mark.parametrize(("name", "mana", "record"), LANDS)
def test_characteristics_and_mana(name: str, mana: ManaType, record: dict[str, object]) -> None:
    scenario = Scenario(2)
    (land,) = scenario.battlefield(P0, [name])
    (in_hand,) = scenario.hand(P0, [name])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    chars = characteristics(state, land)
    assert chars.name == name
    assert chars.supertypes == (Supertype.BASIC,)
    assert chars.card_types == (CardType.LAND,)
    assert chars.subtypes == (name,)
    (ability,) = chars.abilities
    assert ability.text == "{T}: Add {" + mana.value + "}."
    request = request_of(state)
    assert request.kind is DecisionKind.PRIORITY_ACTION
    assert isinstance(request.space, ChooseOne)
    # Played (305.1), never cast (305.9); the one on the battlefield taps for mana (305.6).
    assert request.space.options == (
        PassOption(),
        PlayLandOption(in_hand),
        ActivateAbilityOption(land, 0),
    )
    run_script(state, choose(ActivateAbilityOption(land, 0)))
    assert state.player(P0).mana_pool == [Mana(mana, land)]


def test_a_basic_land_decklist_builds_with_the_default_registry() -> None:
    database = CardDatabase(parse_oracle_cards([record for _, _, record in LANDS]))
    decklist = parse_decklist("Mainboard\n" + "".join(f"2 {n}\n" for n, _, _ in LANDS))
    deck = build_deck(decklist, database, default_registry())
    assert len(deck.cards) == 10
    assert deck.cards[0].definitions == (basic_lands.PLAINS,)
