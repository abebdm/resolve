"""Grizzly Bears, Savannah Lions and Hill Giant: creature cards with no rules text.

Oracle data (Scryfall): Grizzly Bears {1}{G}, Creature — Bear, 2/2; Savannah Lions {W},
Creature — Cat, 2/1; Hill Giant {3}{R}, Creature — Giant, 3/3; no Oracle text. Their rulings
don't change any of this. A creature spell may be cast only in its controller's main phase with
an empty stack (302.1); casting itself is a gap until M2 (601.2).
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from resolve.cards.definitions import vanilla_creatures
from resolve.cards.registry import default_registry
from resolve.data.cards import load_card_excerpt, parse_card
from resolve.data.mana_cost import parse_mana_cost
from resolve.data.types import CardType, Color
from resolve.decisions.spaces import CastSpellOption, ChooseOne, PassOption
from resolve.effects.characteristics import characteristics
from resolve.state.ids import PlayerId
from resolve.state.spell import FROM_HAND, NORMAL
from resolve.state.turn import Phase, Step
from tests import scryfall_fixtures as fx
from tests.game_fixtures import request_of
from tests.scenario import Scenario

P0, P1 = PlayerId(0), PlayerId(1)
CREATURES = [
    ("Grizzly Bears", ("Bear",), 2, 2),
    ("Savannah Lions", ("Cat",), 2, 1),
    ("Hill Giant", ("Giant",), 3, 3),
]


def test_they_are_registered_without_abilities() -> None:
    registry = default_registry()
    for name, *_ in CREATURES:
        assert registry.get(name).abilities == ()
    assert [d.name for d in vanilla_creatures.DEFINITIONS] == [name for name, *_ in CREATURES]


@pytest.mark.parametrize(("name", "subtypes", "power", "toughness"), CREATURES)
def test_printed_characteristics(
    name: str, subtypes: tuple[str, ...], power: int, toughness: int
) -> None:
    scenario = Scenario(2)
    (in_hand,) = scenario.hand(P0, [name])
    (on_field,) = scenario.battlefield(P0, [name])
    state = scenario.build()
    for obj in (in_hand, on_field):
        chars = characteristics(state, obj)
        assert chars.card_types == (CardType.CREATURE,)
        assert chars.subtypes == subtypes
        assert (chars.power, chars.toughness) == (power, toughness)
        assert chars.abilities == ()


@pytest.mark.parametrize(("name", "subtypes", "power", "toughness"), CREATURES)
def test_302_1_cast_only_in_the_main_phase(
    name: str, subtypes: tuple[str, ...], power: int, toughness: int
) -> None:
    for where, castable in ((Phase.PRECOMBAT_MAIN, True), (Step.UPKEEP, False)):
        scenario = Scenario(2)
        (card,) = scenario.hand(P0, [name])
        scenario.at(where)
        request = request_of(scenario.build())
        assert isinstance(request.space, ChooseOne)
        expected = (
            (PassOption(), CastSpellOption(card, NORMAL, FROM_HAND))
            if castable
            else (PassOption(),)
        )
        assert request.space.options == expected


# --- Mana cost, colors and mana value (202), against real Scryfall data -----------------------

EXCERPT = Path(__file__).resolve().parents[2] / "tools" / "excerpts" / "cards.json"
COSTS = [
    ("Grizzly Bears", "{1}{G}", (Color.GREEN,), 2, fx.GRIZZLY_BEARS),
    ("Savannah Lions", "{W}", (Color.WHITE,), 1, fx.SAVANNAH_LIONS),
    ("Hill Giant", "{3}{R}", (Color.RED,), 4, fx.HILL_GIANT),
]


def test_the_excerpt_holds_the_vanilla_creatures() -> None:
    """``tools/excerpts/cards.json`` is copied from the Scryfall snapshot, never hand-written
    (``tools/card_excerpt.py``, which also checks it against a local snapshot)."""
    database = load_card_excerpt(EXCERPT)
    assert {card.name for card in database.cards()} == {name for name, *_ in COSTS}


@pytest.mark.parametrize(("name", "text", "colors", "value", "record"), COSTS)
def test_202_the_real_cost_colors_and_mana_value(
    name: str, text: str, colors: tuple[Color, ...], value: int, record: dict[str, object]
) -> None:
    card = load_card_excerpt(EXCERPT).get(name)
    face = card.faces[0]
    assert face.cost == parse_mana_cost(text)
    assert face.cost is not None and face.cost.colors == colors  # 202.2
    assert face.cost.mana_value() == value == card.mana_value  # 202.3, as Scryfall reports it
    assert card.mana_cost_problems == ()
    # The fixture the engine tests use is the same card (its Oracle ID is invented).
    assert parse_card(record) == dataclasses.replace(card, oracle_id=parse_card(record).oracle_id)


@pytest.mark.parametrize(("name", "text", "colors", "value", "record"), COSTS)
def test_202_characteristics_have_the_cost_colors_and_mana_value(
    name: str, text: str, colors: tuple[Color, ...], value: int, record: dict[str, object]
) -> None:
    scenario = Scenario(2)
    (card,) = scenario.hand(P0, [name])
    chars = characteristics(scenario.build(), card)
    assert chars.mana_cost == parse_mana_cost(text)
    assert (chars.colors, chars.mana_value) == (colors, value)
