"""Mana costs and mana symbols (107.4, 202.1-202.3): parsing Scryfall's printed text.

Expected values are read off 107.4 (the symbols and what each represents), 202.2 (a cost's
colors) and 202.3 (its mana value: hybrid symbols count their largest half, 202.3f; Phyrexian
symbols count 1, 202.3g; {X} is 0 off the stack, 202.3e).

A mana cost that doesn't follow 107.4 (Un-set half-mana symbols) must not stop the card database
from loading; the card is refused only when it would be used (a deck, a game, the coverage
report), like an unreadable type line (docs/decisions.md).
"""

from __future__ import annotations

import copy
import pickle

import pytest

from resolve.cards.coverage import CoverageStatus, deck_coverage
from resolve.cards.registry import CardDefinition, CardRegistry
from resolve.data.cards import CardDatabase, parse_card, parse_oracle_cards
from resolve.data.decklist import parse_decklist
from resolve.data.mana_cost import (
    ManaCost,
    ManaCostError,
    ManaSymbol,
    SymbolKind,
    parse_mana_cost,
)
from resolve.data.types import Color
from resolve.engine.deck import DeckCard, DeckError
from tests import scryfall_fixtures as fx

W, U, B, R, G = Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN


def sym(kind: SymbolKind, colors: tuple[Color, ...] = (), number: int = 0) -> ManaSymbol:
    return ManaSymbol(kind, colors, number)


# --- 107.4: each kind of symbol parses --------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "symbols"),
    [
        ("{3}{R}", (sym(SymbolKind.GENERIC, (), 3), sym(SymbolKind.COLORED, (R,)))),
        ("{X}{G}", (sym(SymbolKind.VARIABLE), sym(SymbolKind.COLORED, (G,)))),
        ("{C}{C}", (sym(SymbolKind.COLORLESS), sym(SymbolKind.COLORLESS))),
        ("{0}", (sym(SymbolKind.GENERIC, (), 0),)),
        ("{W/U}", (sym(SymbolKind.HYBRID, (W, U)),)),
        ("{2/W}", (sym(SymbolKind.MONOCOLORED_HYBRID, (W,), 2),)),
        ("{C/G}", (sym(SymbolKind.COLORLESS_HYBRID, (G,), 1),)),
        ("{G/P}", (sym(SymbolKind.PHYREXIAN, (G,)),)),
        ("{G/U/P}", (sym(SymbolKind.HYBRID_PHYREXIAN, (G, U)),)),
        ("{S}", (sym(SymbolKind.SNOW),)),
        ("{10}", (sym(SymbolKind.GENERIC, (), 10),)),
        ("{1}{W}{U}{B}{R}{G}", (
            sym(SymbolKind.GENERIC, (), 1),
            sym(SymbolKind.COLORED, (W,)), sym(SymbolKind.COLORED, (U,)),
            sym(SymbolKind.COLORED, (B,)), sym(SymbolKind.COLORED, (R,)),
            sym(SymbolKind.COLORED, (G,)),
        )),
    ],
)  # fmt: skip
def test_107_4_each_mana_symbol_kind_parses(text: str, symbols: tuple[ManaSymbol, ...]) -> None:
    cost = parse_mana_cost(text)
    assert cost.symbols == symbols
    assert cost.text == text  # printed order is kept


@pytest.mark.parametrize(
    "text",
    [
        "{W/U}", "{W/B}", "{U/B}", "{U/R}", "{B/R}", "{B/G}", "{R/G}", "{R/W}", "{G/W}", "{G/U}",
        "{2/W}", "{2/U}", "{2/B}", "{2/R}", "{2/G}", "{C/W}", "{C/U}", "{C/B}", "{C/R}", "{C/G}",
        "{W/P}", "{U/P}", "{B/P}", "{R/P}", "{G/P}",
        "{W/U/P}", "{W/B/P}", "{U/B/P}", "{U/R/P}", "{B/R/P}",
        "{B/G/P}", "{R/G/P}", "{R/W/P}", "{G/W/P}", "{G/U/P}",
    ],
)  # fmt: skip
def test_107_4_every_listed_symbol_parses_and_prints_back(text: str) -> None:
    """The 35 hybrid, monocolored hybrid, Phyrexian and hybrid Phyrexian symbols 107.4 lists."""
    (symbol,) = parse_mana_cost(text).symbols
    assert symbol.text == text


@pytest.mark.parametrize(
    "text",
    [
        "",  # a cost has at least one symbol; "no mana cost" is the absence of a cost (202.3a)
        "{Q}", "{HW}", "{D}", "{}", "{ 1}", "{-1}", "{01}", "{1.5}",  # not 107.4 symbols
        "{U/W}", "{W/W}", "{2/2}", "{X/W}", "{P}", "{W/P/P}", "{W/U/B}",  # not listed in 107.4
        "{1", "1}", "1", "R", "{1}{R", "{1} {R}", "{1}garbage", "{1}{R} // {1}{U}",
        "{w}", "{x}", "{s}",  # symbols are upper case
    ],
)  # fmt: skip
def test_107_4_an_unknown_symbol_is_refused(text: str) -> None:
    with pytest.raises(ManaCostError):
        parse_mana_cost(text)


# --- 202.3: mana value ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "x", "value"),
    [
        ("{3}{R}", 0, 4),  # Hill Giant
        ("{2}{R}{R}", 0, 4),  # Fiery Confluence
        ("{G}", 0, 1),  # Llanowar Elves
        ("{4}{G}{G}", 0, 6),  # Rishkar's Expertise
        ("{0}", 0, 0),
        ("{X}{G}", 0, 1),  # 202.3e: X is 0 off the stack
        ("{X}{G}", 3, 4),  # 202.3e: X is the chosen number on the stack
        ("{X}{X}{G}", 2, 5),
        ("{1}{W/U}{W/U}", 0, 3),  # 202.3f
        ("{2/B}{2/B}{2/B}", 0, 6),  # 202.3f: the largest component of each hybrid symbol
        ("{2/W}", 0, 2),
        ("{C/W}", 0, 1),  # the colorless half is one mana
        ("{G/P}", 0, 1),  # 202.3g
        ("{1}{W/P}{W/P}", 0, 3),  # 202.3g
        ("{G/U/P}", 0, 1),
        ("{S}{S}", 0, 2),
        ("{1000000}", 0, 1000000),
    ],
)
def test_202_3_mana_value(text: str, x: int, value: int) -> None:
    assert parse_mana_cost(text).mana_value(x) == value


def test_202_3e_x_defaults_to_zero() -> None:
    assert parse_mana_cost("{X}{G}").mana_value() == 1


# --- 202.2: colors ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "colors"),
    [
        ("{2}{W}", (W,)),  # 202.2 example
        ("{2}", ()),  # 202.2 example
        ("{2}{W}{B}", (W, B)),  # 202.2c
        ("{B}{W}", (W, B)),  # always listed in WUBRG order
        ("{C}{C}", ()),  # colorless mana isn't a color
        ("{X}", ()),
        ("{W/U}", (W, U)),  # 202.2d, 107.4e: a hybrid symbol is all of its colors
        ("{2/B}", (B,)),
        ("{C/G}", (G,)),  # 107.4e: colored even though one half is colorless
        ("{R/P}", (R,)),  # 107.4f
        ("{G/U/P}", (U, G)),  # 107.4f: hybrid Phyrexian is both colors
        ("{S}", ()),  # 107.4h: snow is neither a color nor a type of mana
        ("{1}{R}{R}{G}", (R, G)),  # no repeats
    ],
)
def test_202_2_a_costs_colors_are_those_of_its_symbols(
    text: str, colors: tuple[Color, ...]
) -> None:
    assert parse_mana_cost(text).colors == colors


# --- Card faces carry their parsed cost -------------------------------------------------------


def test_202_1_card_faces_carry_their_parsed_cost() -> None:
    elves = parse_card(fx.LLANOWAR_ELVES)
    assert elves.faces[0].cost == parse_mana_cost("{G}")
    assert elves.mana_cost_problems == ()
    daybreaker = parse_card(fx.TRANSFORM_CARD)
    assert daybreaker.faces[0].cost == parse_mana_cost("{1}{G}")
    assert daybreaker.faces[1].cost is None  # 202.3a: the back face has no mana cost
    split = parse_card(fx.SPLIT_CARD)
    assert [face.cost for face in split.faces] == [
        parse_mana_cost("{1}{R}"),
        parse_mana_cost("{1}{U}"),
    ]


def test_202_3a_no_mana_cost_is_not_a_cost_of_zero() -> None:
    """A land has no mana cost (``None``); a ``{0}`` card has one. Both have mana value 0."""
    forest = parse_card(fx.FOREST).faces[0]
    mox = parse_card(fx.TEST_MOX).faces[0]
    assert forest.cost is None
    assert mox.cost == ManaCost((sym(SymbolKind.GENERIC, (), 0),))
    assert mox.cost is not None and mox.cost.mana_value() == 0


def test_a_card_with_a_cost_survives_copy_and_pickle() -> None:
    card = parse_card(fx.TEST_TWO_TONE)
    assert pickle.loads(pickle.dumps(card)) == card
    assert copy.deepcopy(card) is card  # Immutable: copies are the value itself


# --- A cost that doesn't follow 107.4 ---------------------------------------------------------


def test_an_unreadable_mana_cost_is_recorded_not_raised() -> None:
    card = parse_card(fx.TEST_HALF)
    assert card.faces[0].cost is None
    (problem,) = card.mana_cost_problems
    assert problem.startswith("Test Half: ") and "HW" in problem
    assert card.type_line_problems == ()


def test_a_deck_card_with_an_unreadable_mana_cost_is_refused() -> None:
    card = parse_card(fx.TEST_HALF)
    with pytest.raises(DeckError, match="mana cost"):
        DeckCard(card, (CardDefinition("Test Half"),))


def test_coverage_reports_an_unreadable_mana_cost_even_when_registered() -> None:
    database = CardDatabase(parse_oracle_cards([*fx.default_cards(), fx.TEST_HALF]))
    registry = CardRegistry([CardDefinition("Forest"), CardDefinition("Test Half")])
    coverage = deck_coverage(
        parse_decklist("Mainboard\n10 Forest\n1 Test Half\n"), database, registry
    )
    (unreadable,) = coverage.unreadable
    assert unreadable.name == "Test Half"
    assert unreadable.status is CoverageStatus.UNREADABLE
    assert unreadable.problem is not None and "107.4" in unreadable.problem
    assert [card.name for card in coverage.implemented] == ["Forest"]
