"""Decks as ``new_game`` takes them: cards resolved to their data and definitions (design.md §11).

``build_deck`` turns a parsed decklist into a ``Deck`` using the card data and the registry. It
refuses decks with any unknown or unimplemented card, listing all of them; nothing is
approximated. The sideboard is set aside (103.2a).

Deck legality (deck size, singleton, color identity: 100.2a, 903.5) isn't checked yet; it arrives
with deck validation in M7 (docs/decisions.md 2026-10-18).
"""

from __future__ import annotations

from dataclasses import dataclass

from resolve.cards.coverage import deck_coverage
from resolve.cards.registry import CardDefinition, CardRegistry
from resolve.data.cards import CardData, CardDatabase
from resolve.data.decklist import DeckEntry, Decklist
from resolve.errors import DeckError
from resolve.values import Immutable


@dataclass(frozen=True)
class DeckCard(Immutable):
    """One physical card for a deck: its Oracle data and one definition per face, in face order.

    Building one with definitions that don't match the faces raises ``DeckError``, so a deck can't
    contain an unimplemented card even when it is built by hand. Nor can it contain a card whose
    type line or mana cost the engine can't read (205, 107.4; Un-set jokes).
    """

    data: CardData
    definitions: tuple[CardDefinition, ...]

    def __post_init__(self) -> None:
        names = tuple(definition.name for definition in self.definitions)
        if names != self.data.face_names:
            raise DeckError(
                f"{self.data.name!r} needs definitions for {list(self.data.face_names)}, "
                f"got {list(names)}"
            )
        problems = self.data.type_line_problems
        if problems:
            raise DeckError(
                f"{self.data.name!r} can't be played: its type line doesn't follow 205 "
                f"({'; '.join(problems)})"
            )
        problems = self.data.mana_cost_problems
        if problems:
            raise DeckError(
                f"{self.data.name!r} can't be played: its mana cost doesn't follow 107.4 "
                f"({'; '.join(problems)})"
            )

    @classmethod
    def from_registry(cls, data: CardData, registry: CardRegistry) -> DeckCard:
        """The card with its definitions from ``registry``; ``DeckError`` if any face is missing."""
        missing = registry.missing_faces(data)
        if missing:
            raise DeckError(f"{data.name!r} is not implemented (missing: {', '.join(missing)})")
        return cls(data, tuple(registry.get(name) for name in data.face_names))


@dataclass(frozen=True)
class Deck(Immutable):
    """A player's deck: the cards that start in the library and, for Commander, the commanders."""

    cards: tuple[DeckCard, ...]
    commanders: tuple[DeckCard, ...] = ()
    name: str | None = None


def build_deck(decklist: Decklist, database: CardDatabase, registry: CardRegistry) -> Deck:
    """Resolve every card of ``decklist``; ``DeckError`` lists all unknown and missing cards."""
    coverage = deck_coverage(decklist, database, registry)
    problems = [f"unknown card {card.name!r}: {card.problem}" for card in coverage.unknown]
    problems += [
        f"{card.name!r} is not implemented (missing: {', '.join(card.missing_faces)})"
        for card in coverage.missing
    ]
    problems += [f"{card.name!r} can't be played: {card.problem}" for card in coverage.unreadable]
    if problems:
        deck = decklist.name or "deck"
        raise DeckError(f"{deck} can't be played:\n" + "\n".join(f"- {p}" for p in problems))

    def expand(entries: tuple[DeckEntry, ...]) -> tuple[DeckCard, ...]:
        cards: list[DeckCard] = []
        for entry in entries:
            card = DeckCard.from_registry(database.get(entry.name), registry)
            cards.extend([card] * entry.count)
        return tuple(cards)

    return Deck(expand(decklist.mainboard), expand(decklist.commander), decklist.name)
