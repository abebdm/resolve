"""202, 105.2, 204: an object's mana cost, colors and mana value in its characteristics.

From the pinned CR:

- 202.1, 202.3a: a card's mana cost is the symbols printed in its top right; a land (or any card
  without one) has no mana cost, and its mana value is 0, which is not the same as a cost of {0}.
- 202.2, 105.2: an object is the color or colors of the mana symbols in its mana cost (hybrid
  and Phyrexian symbols are all of their colors, 202.2d); colorless mana symbols and generic
  mana add no color. 204.2: a color indicator adds colors; the card data's colors include it.
- 202.3, 202.3e-g: mana value is the total amount of mana in the cost; {X} is 0 off the stack,
  hybrid symbols count their largest half, Phyrexian symbols 1.
- 109.3: characteristics include mana cost and color; the omen and preparation layouts have two
  parts, each with its own characteristics, which the engine doesn't compute yet.
"""

from __future__ import annotations

from typing import Any

import pytest

from resolve.cards.registry import CardDefinition, CardRegistry
from resolve.data.cards import CardDatabase, parse_oracle_cards
from resolve.data.mana_cost import parse_mana_cost
from resolve.data.types import Color
from resolve.effects.characteristics import Characteristics, characteristics
from resolve.errors import NotImplementedRule
from resolve.state.ids import PlayerId
from tests import scryfall_fixtures as fx
from tests.scenario import Scenario

P0 = PlayerId(0)
W, U, B, R, G = Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN

CARDS = [
    fx.FOREST,
    fx.GRIZZLY_BEARS,
    fx.HILL_GIANT,
    fx.LLANOWAR_ELVES,
    fx.SOL_RING,
    fx.SELESNYA_SIGNET,
    fx.FIERY_CONFLUENCE,
    fx.RISHKARS_EXPERTISE,
    fx.TEST_MOX,
    fx.TEST_GOLD,
    fx.TEST_GROWTH,
    fx.TEST_HYBRID,
    fx.TEST_TWO_TONE,
    fx.TEST_PHYREXIAN,
    fx.TEST_SNOW,
]


def chars_of(*records: dict[str, Any]) -> list[Characteristics]:
    """The characteristics of each card, in hand, with the definitions the tests need."""
    names = [name for record in records for name in _face_names(record)]
    scenario = Scenario(
        2,
        database=CardDatabase(parse_oracle_cards([*CARDS, *records])),
        registry=CardRegistry([CardDefinition(name) for name in {*names, "Forest"}]),
    )
    objects = scenario.hand(P0, [record["name"] for record in records])
    state = scenario.build()
    return [characteristics(state, obj) for obj in objects]


def _face_names(record: dict[str, Any]) -> list[str]:
    faces: list[dict[str, Any]] = record.get("card_faces", [record])
    return [face["name"] for face in faces]


def one(record: dict[str, Any]) -> Characteristics:
    (chars,) = chars_of(record)
    return chars


# --- 202.1, 202.3a: the cost ------------------------------------------------------------------


def test_202_1_the_mana_cost_is_in_the_characteristics() -> None:
    assert one(fx.HILL_GIANT).mana_cost == parse_mana_cost("{3}{R}")
    assert one(fx.TEST_HYBRID).mana_cost == parse_mana_cost("{2/W}{2/W}")


def test_202_1_a_land_has_no_mana_cost_unlike_a_zero_cost() -> None:
    """202.3a: a land has no mana cost and mana value 0; {0} is a cost, with mana value 0 too."""
    forest, mox = chars_of(fx.FOREST, fx.TEST_MOX)
    assert forest.mana_cost is None and forest.mana_value == 0
    assert mox.mana_cost is not None and mox.mana_value == 0
    assert forest.mana_cost != mox.mana_cost


# --- 202.3: mana value ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("record", "value"),
    [
        (fx.HILL_GIANT, 4),
        (fx.FIERY_CONFLUENCE, 4),
        (fx.LLANOWAR_ELVES, 1),
        (fx.RISHKARS_EXPERTISE, 6),
        (fx.TEST_GROWTH, 1),  # 202.3e: {X}{G} with X as 0 off the stack
        (fx.TEST_HYBRID, 4),  # 202.3f: {2/W}{2/W}
        (fx.TEST_TWO_TONE, 3),  # 202.3f: {1}{W/U}{W/U}
        (fx.TEST_PHYREXIAN, 3),  # 202.3g: {1}{W/P}{W/P}
        (fx.TEST_SNOW, 2),
        (fx.FOREST, 0),
    ],
)
def test_202_3_mana_value(record: dict[str, Any], value: int) -> None:
    assert one(record).mana_value == value


# --- 105.2, 202.2: colors ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("record", "colors"),
    [
        (fx.GRIZZLY_BEARS, (G,)),
        (fx.SOL_RING, ()),  # 202.2b: no colored symbol in {1}
        (fx.SELESNYA_SIGNET, ()),  # 202.2b: its {G}{W} is in its ability, not its cost
        (fx.TEST_GOLD, (W, B)),  # 202.2c
        (fx.TEST_TWO_TONE, (W, U)),  # 202.2d
        (fx.TEST_PHYREXIAN, (W,)),  # 107.4f
        (fx.FOREST, ()),  # 105.2c: a land isn't green, whatever it taps for
    ],
)
def test_105_2_colors_come_from_the_card(record: dict[str, Any], colors: tuple[Color, ...]) -> None:
    assert one(record).colors == colors


def test_204_2_a_color_indicator_gives_the_colors_the_card_data_lists() -> None:
    """204.2: an object with a color indicator is each color it denotes. Scryfall's colors
    include indicators, so a face with no cost and colors [U] (a back face) is blue."""
    indicated = fx.spell("Test Indicated", "", 0.0, "Creature — Spirit", ["U"])
    (chars,) = chars_of(indicated)
    assert chars.mana_cost is None and chars.colors == (U,) and chars.mana_value == 0


def test_105_2_colors_are_listed_in_the_order_white_blue_black_red_green() -> None:
    data_order = fx.spell("Test Reversed", "{G}{W}", 2.0, "Sorcery", ["G", "W"])
    assert one(data_order).colors == (W, G)


# --- 109.3: the omen and preparation layouts --------------------------------------------------


def _two_part(layout: str, faces: int) -> dict[str, Any]:
    """A card of ``layout`` whose data has one face (trimmed) or two."""
    front = fx.spell(f"Test Front {layout}", "{1}{G}", 2.0, "Creature — Elf", ["G"])
    front["power"], front["toughness"] = "2", "2"
    front["layout"] = layout
    if faces == 1:
        return front
    back = fx.spell(f"Test Back {layout}", "{G}", 1.0, "Sorcery", ["G"])
    return {
        **front,
        "name": f"{front['name']} // {back['name']}",
        "card_faces": [{**front, "object": "card_face"}, {**back, "object": "card_face"}],
    }


@pytest.mark.parametrize("layout", ["prepare", "omen"])
@pytest.mark.parametrize("faces", [1, 2])
def test_109_3_omen_and_preparation_layouts_are_a_gap(layout: str, faces: int) -> None:
    """720 (omen) and 722 (preparation) cards have two parts with their own characteristics.
    Their data may arrive as one face (a trimmed excerpt) or two; neither is read as a plain
    single-faced card."""
    record = _two_part(layout, faces)
    with pytest.raises(NotImplementedRule) as gap:
        chars_of(record)
    assert gap.value.rule == "109.3"
