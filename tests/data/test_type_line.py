"""Type lines (205): parsing Scryfall's printed text, and cards whose type lines can't be read.

Expected values are read off 205: supertypes come first (205.4a), then card types (205.2a), then
subtypes after the long dash (205.3b). Creature types may be two words ("Time Lord", 205.3m),
and a plane's subtype is the whole phrase after the dash (205.3b, 205.3n).

A type line that doesn't follow 205 (Un-set joke types) must not make the card database fail to
load; such a card is refused only when it would be used: in a deck, in a game, or as an
implemented card in the coverage report (docs/decisions.md).
"""

from __future__ import annotations

import copy
import pickle
from pathlib import Path

import pytest

from resolve.cards.coverage import CoverageStatus, deck_coverage
from resolve.cards.registry import CardDefinition, CardRegistry
from resolve.data.cards import CardDatabase, load_card_database, parse_card, parse_oracle_cards
from resolve.data.decklist import parse_decklist
from resolve.data.types import (
    CardType,
    Supertype,
    TypeLine,
    TypeLineError,
    parse_type_line,
    try_parse_type_line,
)
from resolve.engine.deck import DeckCard, build_deck
from resolve.errors import DeckError
from tests import scryfall_fixtures as fx
from tools import coverage as coverage_tool

JOKE = fx.simple_card("Test Joke", "oid-test-joke", type_line="Artifact Contraption Gizmo")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Basic Land — Forest",
            TypeLine((Supertype.BASIC,), (CardType.LAND,), ("Forest",)),
        ),
        (
            "Legendary Creature — Elf Druid",
            TypeLine((Supertype.LEGENDARY,), (CardType.CREATURE,), ("Elf", "Druid")),
        ),
        ("Land", TypeLine((), (CardType.LAND,), ())),
        (
            "Artifact Creature — Golem",
            TypeLine((), (CardType.ARTIFACT, CardType.CREATURE), ("Golem",)),
        ),
        (
            "Legendary Snow Enchantment Creature — God",
            TypeLine(
                (Supertype.LEGENDARY, Supertype.SNOW),
                (CardType.ENCHANTMENT, CardType.CREATURE),
                ("God",),
            ),
        ),
        ("Kindred Instant — Elf", TypeLine((), (CardType.KINDRED, CardType.INSTANT), ("Elf",))),
        ("Sorcery", TypeLine((), (CardType.SORCERY,), ())),
        # 205.3m: "Time Lord" is one creature type of two words.
        (
            "Legendary Creature — Time Lord Doctor",
            TypeLine((Supertype.LEGENDARY,), (CardType.CREATURE,), ("Time Lord", "Doctor")),
        ),
        # 205.3b: a plane's subtype is everything after the dash.
        (
            "Plane — Horsehead Nebula",
            TypeLine((), (CardType.PLANE,), ("Horsehead Nebula",)),
        ),
    ],
)
def test_205_parse_type_line(text: str, expected: TypeLine) -> None:
    assert parse_type_line(text) == expected
    assert try_parse_type_line(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Artifact Contraption Gizmo",  # 205.2a: not card types
        "",  # 205.1: a type line contains at least one card type
        "Legendary",  # a supertype with no card type
        "Creature —",  # 205.3b: a dash with nothing after it
        "— Elf",  # no card type before the dash
        "Summon Elf",  # an old printed type, not a 205.2a card type
    ],
)
def test_205_a_type_line_that_doesnt_follow_205_is_refused(text: str) -> None:
    with pytest.raises(TypeLineError):
        parse_type_line(text)
    assert try_parse_type_line(text) is None


def test_205_4a_a_supertype_after_a_card_type_is_refused() -> None:
    """205.4a: supertypes are printed directly before the card types."""
    with pytest.raises(TypeLineError, match="Legendary"):
        parse_type_line("Creature Legendary — Elf")


def test_card_faces_carry_their_parsed_type_line() -> None:
    forest = parse_card(fx.FOREST)
    assert forest.faces[0].types == TypeLine((Supertype.BASIC,), (CardType.LAND,), ("Forest",))
    assert forest.type_line_problems == ()
    daybreaker = parse_card(fx.TRANSFORM_CARD)
    assert [face.types for face in daybreaker.faces] == [
        TypeLine((), (CardType.CREATURE,), ("Human",)),
        TypeLine((), (CardType.CREATURE,), ("Werewolf",)),
    ]


def test_card_data_with_parsed_types_survives_copy_and_pickle() -> None:
    card = parse_card(fx.LLANOWAR_ELVES)
    assert pickle.loads(pickle.dumps(card)) == card
    assert copy.deepcopy(card) is card  # Immutable: copies are the value itself


def test_an_unreadable_type_line_is_recorded_not_raised() -> None:
    card = parse_card(JOKE)
    assert card.faces[0].types is None
    (problem,) = card.type_line_problems
    assert problem.startswith("Test Joke: ")
    assert "Contraption" in problem and "Gizmo" in problem


def test_the_database_loads_with_an_unreadable_card_present(tmp_path: Path) -> None:
    """Binding change 1: one unreadable card doesn't stop the database from loading."""
    fx.write_snapshot(tmp_path, cards=[*fx.default_cards(), JOKE])
    database = load_card_database(tmp_path)
    assert database.get("Test Joke").faces[0].types is None
    assert database.get("Forest").faces[0].types is not None


def test_a_deck_card_with_an_unreadable_type_line_is_refused() -> None:
    card = parse_card(JOKE)
    with pytest.raises(DeckError, match="type line"):
        DeckCard(card, (CardDefinition("Test Joke"),))


def test_build_deck_refuses_a_deck_with_an_unreadable_card() -> None:
    database = CardDatabase(parse_oracle_cards([*fx.default_cards(), JOKE]))
    registry = CardRegistry([CardDefinition("Forest"), CardDefinition("Test Joke")])
    decklist = parse_decklist("Mainboard\n10 Forest\n1 Test Joke\n")
    with pytest.raises(DeckError, match="'Test Joke' can't be played"):
        build_deck(decklist, database, registry)


def test_coverage_reports_an_unreadable_card_even_when_it_is_registered() -> None:
    database = CardDatabase(parse_oracle_cards([*fx.default_cards(), JOKE]))
    registry = CardRegistry([CardDefinition("Forest"), CardDefinition("Test Joke")])
    coverage = deck_coverage(
        parse_decklist("Mainboard\n10 Forest\n1 Test Joke\n"), database, registry
    )
    (unreadable,) = coverage.unreadable
    assert unreadable.name == "Test Joke"
    assert unreadable.status is CoverageStatus.UNREADABLE
    assert unreadable.problem is not None and "205" in unreadable.problem
    assert [card.name for card in coverage.implemented] == ["Forest"]
    assert not coverage.is_fully_implemented


def test_the_coverage_tool_lists_unreadable_cards_and_fails(tmp_path: Path) -> None:
    fx.write_snapshot(tmp_path, cards=[*fx.default_cards(), JOKE])
    deck = tmp_path / "deck.txt"
    deck.write_text("Mainboard\n10 Forest\n1 Test Joke\n", encoding="utf-8")
    report, status = coverage_tool.run(
        [deck], load_card_database(tmp_path), CardRegistry([CardDefinition("Forest")])
    )
    assert "2 distinct: 1 implemented, 0 missing, 0 unknown, 1 unreadable" in report
    assert "Unreadable (type line doesn't follow 205):\n  1 Test Joke  [Mainboard]" in report
    assert status == 1
