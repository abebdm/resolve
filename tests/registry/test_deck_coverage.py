"""Tests for deck coverage (resolve.cards.coverage)."""

from __future__ import annotations

from resolve.cards.coverage import CoverageStatus, deck_coverage
from resolve.cards.registry import CardDefinition, CardRegistry
from resolve.data.cards import CardDatabase, parse_oracle_cards, parse_rulings
from resolve.data.decklist import Section, parse_decklist
from tests import scryfall_fixtures as fx

DECK = """\
Commander
1 Test Daybreaker

Mainboard
1 Llanowar Elves
30 Forest
1 Test Spark // Test Frost
1 Not A Real Card

Sideboard
1 Llanowar Elves
1 Sideboard Only Card
"""


def database() -> CardDatabase:
    cards = [
        *fx.default_cards(),
        fx.simple_card("Test Twin", "a"),
        fx.simple_card("Test Twin", "b"),
    ]
    return CardDatabase(parse_oracle_cards(cards), parse_rulings(fx.default_rulings()))


def registry() -> CardRegistry:
    return CardRegistry(
        [CardDefinition("Forest"), CardDefinition("Llanowar Elves"), CardDefinition("Test Spark")]
    )


def test_each_distinct_card_is_classified_in_deck_order() -> None:
    coverage = deck_coverage(parse_decklist(DECK, name="deck"), database(), registry())
    assert coverage.deck_name == "deck"
    assert [(c.name, c.status) for c in coverage.cards] == [
        ("Test Daybreaker", CoverageStatus.MISSING),
        ("Llanowar Elves", CoverageStatus.IMPLEMENTED),
        ("Forest", CoverageStatus.IMPLEMENTED),
        ("Test Spark // Test Frost", CoverageStatus.MISSING),
        ("Not A Real Card", CoverageStatus.UNKNOWN),
    ]
    assert [c.name for c in coverage.implemented] == ["Llanowar Elves", "Forest"]
    assert [c.name for c in coverage.unknown] == ["Not A Real Card"]
    assert not coverage.is_fully_implemented


def test_sideboard_is_out_of_scope_by_default() -> None:
    coverage = deck_coverage(parse_decklist(DECK), database(), registry())
    assert "Sideboard Only Card" not in [c.name for c in coverage.cards]
    elves = next(c for c in coverage.cards if c.name == "Llanowar Elves")
    assert elves.count == 1
    assert elves.sections == (Section.MAINBOARD,)


def test_sideboard_included_when_asked() -> None:
    coverage = deck_coverage(parse_decklist(DECK), database(), registry(), include_sideboard=True)
    elves = next(c for c in coverage.cards if c.name == "Llanowar Elves")
    assert elves.count == 2
    assert elves.sections == (Section.MAINBOARD, Section.SIDEBOARD)
    assert coverage.cards[-1].name == "Sideboard Only Card"
    assert coverage.cards[-1].status is CoverageStatus.UNKNOWN


def test_counts_and_sections_are_reported() -> None:
    coverage = deck_coverage(parse_decklist(DECK), database(), registry())
    forest = next(c for c in coverage.cards if c.name == "Forest")
    assert forest.count == 30
    commander = coverage.cards[0]
    assert commander.sections == (Section.COMMANDER,)


def test_partially_implemented_multi_faced_card_lists_missing_faces() -> None:
    coverage = deck_coverage(parse_decklist(DECK), database(), registry())
    split = next(c for c in coverage.cards if c.name == "Test Spark // Test Frost")
    assert split.missing_faces == ("Test Frost",)
    assert split.card is not None and split.card.layout == "split"
    daybreaker = coverage.cards[0]
    assert daybreaker.missing_faces == ("Test Daybreaker", "Test Nightfall")


def test_unknown_and_ambiguous_names_carry_the_problem() -> None:
    deck = parse_decklist("Mainboard\n1 Test Twin\n1 forest\n")
    coverage = deck_coverage(deck, database(), registry())
    twin, forest = coverage.cards
    assert twin.status is CoverageStatus.UNKNOWN
    assert twin.problem is not None and "ambiguous" in twin.problem
    assert forest.status is CoverageStatus.UNKNOWN, "lookup is exact; 'forest' is not 'Forest'"
    assert forest.card is None


def test_fully_implemented_deck() -> None:
    deck = parse_decklist("Mainboard\n1 Llanowar Elves\n59 Forest\n")
    coverage = deck_coverage(deck, database(), registry())
    assert coverage.is_fully_implemented
    assert coverage.missing == () and coverage.unknown == ()


def test_empty_deck_has_no_cards() -> None:
    coverage = deck_coverage(parse_decklist(""), database(), registry())
    assert coverage.cards == ()
