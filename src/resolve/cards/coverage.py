"""Which cards of a decklist the engine implements (design.md §11, "Coverage").

This is what ``tools/coverage.py`` reports, and what ``new_game`` will use to refuse decks that
contain unimplemented cards.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from resolve.cards.registry import CardRegistry
from resolve.data.cards import CardData, CardDatabase, CardDataError
from resolve.data.decklist import Decklist, Section


class CoverageStatus(Enum):
    IMPLEMENTED = "implemented"
    MISSING = "missing"
    # The name doesn't identify exactly one card in the card data snapshot.
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CardCoverage:
    name: str
    count: int
    sections: tuple[Section, ...]
    status: CoverageStatus
    card: CardData | None = None
    missing_faces: tuple[str, ...] = ()
    problem: str | None = None


@dataclass(frozen=True)
class DeckCoverage:
    deck_name: str | None
    cards: tuple[CardCoverage, ...]

    def with_status(self, status: CoverageStatus) -> tuple[CardCoverage, ...]:
        return tuple(card for card in self.cards if card.status is status)

    @property
    def implemented(self) -> tuple[CardCoverage, ...]:
        return self.with_status(CoverageStatus.IMPLEMENTED)

    @property
    def missing(self) -> tuple[CardCoverage, ...]:
        return self.with_status(CoverageStatus.MISSING)

    @property
    def unknown(self) -> tuple[CardCoverage, ...]:
        return self.with_status(CoverageStatus.UNKNOWN)

    @property
    def is_fully_implemented(self) -> bool:
        return all(card.status is CoverageStatus.IMPLEMENTED for card in self.cards)


def deck_coverage(
    decklist: Decklist,
    database: CardDatabase,
    registry: CardRegistry,
    *,
    include_sideboard: bool = False,
) -> DeckCoverage:
    """Classify each distinct card name in the deck, in order of first appearance."""
    sections = [Section.COMMANDER, Section.MAINBOARD]
    if include_sideboard:
        sections.append(Section.SIDEBOARD)

    counts: dict[str, int] = {}
    sections_by_name: dict[str, list[Section]] = {}
    for section in sections:
        for entry in decklist.section(section):
            counts[entry.name] = counts.get(entry.name, 0) + entry.count
            sections_by_name.setdefault(entry.name, []).append(section)

    cards: list[CardCoverage] = []
    for name, count in counts.items():
        found_in = tuple(sections_by_name[name])
        try:
            card = database.get(name)
        except CardDataError as error:
            cards.append(
                CardCoverage(name, count, found_in, CoverageStatus.UNKNOWN, problem=str(error))
            )
            continue
        missing_faces = registry.missing_faces(card)
        status = CoverageStatus.MISSING if missing_faces else CoverageStatus.IMPLEMENTED
        cards.append(CardCoverage(name, count, found_in, status, card, missing_faces))
    return DeckCoverage(decklist.name, tuple(cards))
