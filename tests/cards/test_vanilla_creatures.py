"""Grizzly Bears, Savannah Lions and Hill Giant: creature cards with no rules text.

Oracle data (Scryfall): Grizzly Bears {1}{G}, Creature — Bear, 2/2; Savannah Lions {W},
Creature — Cat, 2/1; Hill Giant {3}{R}, Creature — Giant, 3/3; no Oracle text. Their rulings
don't change any of this. A creature spell may be cast only in its controller's main phase with
an empty stack (302.1); casting itself is a gap until M2 (601.2).
"""

from __future__ import annotations

import pytest

from resolve.cards.definitions import vanilla_creatures
from resolve.cards.registry import default_registry
from resolve.data.types import CardType
from resolve.decisions.spaces import CastSpellOption, ChooseOne, PassOption
from resolve.effects.characteristics import characteristics
from resolve.state.ids import PlayerId
from resolve.state.turn import Phase, Step
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
        expected = (PassOption(), CastSpellOption(card)) if castable else (PassOption(),)
        assert request.space.options == expected
