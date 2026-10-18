"""Building decks for new_game: unimplemented cards are refused, never approximated."""

from __future__ import annotations

import pytest

from resolve.cards.registry import CardDefinition, CardRegistry
from resolve.data.decklist import parse_decklist
from resolve.engine.deck import Deck, DeckCard, build_deck
from resolve.errors import DeckError
from tests.game_fixtures import DAYBREAKER, ELVES, FOREST, database, registry

DECK = """\
Commander
1 Test Daybreaker

Mainboard
3 Forest
1 Llanowar Elves

Sideboard
1 Not A Real Card
"""


def test_build_deck_expands_counts_and_separates_commanders() -> None:
    built = build_deck(parse_decklist(DECK, name="mine"), database(), registry())
    assert built == Deck((FOREST, FOREST, FOREST, ELVES), (DAYBREAKER,), "mine")


def test_build_deck_sets_the_sideboard_aside() -> None:
    """103.2a: sideboard cards are set aside before the game; an unknown one doesn't matter."""
    built = build_deck(parse_decklist(DECK), database(), registry())
    assert len(built.cards) + len(built.commanders) == 5


def test_build_deck_refuses_unknown_and_unimplemented_cards_and_lists_them_all() -> None:
    text = "Mainboard\n1 Forest\n1 Llanowar Elves\n1 Not A Real Card\n1 Test Daybreaker\n"
    partial = CardRegistry([CardDefinition("Forest"), CardDefinition("Test Daybreaker")])
    with pytest.raises(DeckError) as error:
        build_deck(parse_decklist(text, name="bad"), database(), partial)
    message = str(error.value)
    assert message.startswith("bad can't be played")
    assert "unknown card 'Not A Real Card'" in message
    assert "'Llanowar Elves' is not implemented" in message
    assert "missing: Test Nightfall" in message, "a multi-faced card needs every face"


def test_build_deck_of_an_empty_decklist_is_an_empty_deck() -> None:
    assert build_deck(parse_decklist(""), database(), registry()) == Deck(())


def test_deck_card_refuses_definitions_that_do_not_match_the_faces() -> None:
    with pytest.raises(DeckError, match="needs definitions"):
        DeckCard(FOREST.data, ())
    with pytest.raises(DeckError, match="needs definitions"):
        DeckCard(FOREST.data, (CardDefinition("Llanowar Elves"),))
    with pytest.raises(DeckError, match="needs definitions"):
        DeckCard(DAYBREAKER.data, (CardDefinition("Test Daybreaker"),))


def test_deck_card_from_registry() -> None:
    assert DeckCard.from_registry(DAYBREAKER.data, registry()) == DAYBREAKER
    with pytest.raises(DeckError, match="not implemented"):
        DeckCard.from_registry(FOREST.data, CardRegistry())
