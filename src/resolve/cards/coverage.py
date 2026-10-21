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
    """Whether the engine can play a deck card."""

    IMPLEMENTED = "implemented"
    MISSING = "missing"
    # The name doesn't identify exactly one card in the card data snapshot (a typo, a card newer
    # than the snapshot, or an ambiguous name).
    UNKNOWN = "unknown"
    # The card's type line or mana cost doesn't follow 205 or 107.4 (an Un-set joke), so it can't
    # be played.
    UNREADABLE = "unreadable"


@dataclass(frozen=True)
class CardCoverage:
    """The coverage of one distinct card name in a deck.

    ``count`` adds up the copies across the sections that were checked, and ``sections`` lists
    them. ``card`` is the matched card data (``None`` when the name is unknown), ``missing_faces``
    names the faces that still need a definition, and ``problem`` explains an unknown name or an
    unreadable type line.
    """

    name: str
    count: int
    sections: tuple[Section, ...]
    status: CoverageStatus
    card: CardData | None = None
    missing_faces: tuple[str, ...] = ()
    problem: str | None = None


@dataclass(frozen=True)
class DeckCoverage:
    """The coverage of every distinct card in a deck, in order of first appearance."""

    deck_name: str | None
    cards: tuple[CardCoverage, ...]

    def with_status(self, status: CoverageStatus) -> tuple[CardCoverage, ...]:
        """The cards with this status, in deck order."""
        return tuple(card for card in self.cards if card.status is status)

    @property
    def implemented(self) -> tuple[CardCoverage, ...]:
        """Cards whose every face has a definition."""
        return self.with_status(CoverageStatus.IMPLEMENTED)

    @property
    def missing(self) -> tuple[CardCoverage, ...]:
        """Cards found in the card data but missing a definition for at least one face."""
        return self.with_status(CoverageStatus.MISSING)

    @property
    def unknown(self) -> tuple[CardCoverage, ...]:
        """Names that don't identify exactly one card in the card data."""
        return self.with_status(CoverageStatus.UNKNOWN)

    @property
    def unreadable(self) -> tuple[CardCoverage, ...]:
        """Cards whose type line or mana cost the engine can't read (205, 107.4), so they can't be
        played."""
        return self.with_status(CoverageStatus.UNREADABLE)

    @property
    def is_fully_implemented(self) -> bool:
        """Whether every card is implemented, so the deck could be played (an empty deck is)."""
        return all(card.status is CoverageStatus.IMPLEMENTED for card in self.cards)


def deck_coverage(
    decklist: Decklist,
    database: CardDatabase,
    registry: CardRegistry,
    *,
    include_sideboard: bool = False,
) -> DeckCoverage:
    """Classify each distinct card name in the deck, in order of first appearance.

    The commander and mainboard are checked; the sideboard (100.4) only with
    ``include_sideboard``. A name in several sections is reported once, with its counts added.
    """
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
        if card.type_line_problems:
            problems = "; ".join(card.type_line_problems)
            status, reason = (
                CoverageStatus.UNREADABLE,
                f"its type line doesn't follow 205 ({problems})",
            )
        elif card.mana_cost_problems:
            problems = "; ".join(card.mana_cost_problems)
            status, reason = (
                CoverageStatus.UNREADABLE,
                f"its mana cost doesn't follow 107.4 ({problems})",
            )
        elif missing_faces:
            status, reason = CoverageStatus.MISSING, None
        else:
            status, reason = CoverageStatus.IMPLEMENTED, None
        cards.append(CardCoverage(name, count, found_in, status, card, missing_faces, reason))
    return DeckCoverage(decklist.name, tuple(cards))
