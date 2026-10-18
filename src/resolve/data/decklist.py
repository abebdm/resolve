"""Parser for the decklist format used in ``decks/``.

The format::

    # Comments start with '#' at the beginning of a line.
    Commander
    1 Gishath, Sun's Avatar

    Mainboard
    1 Akroma's Will
    8 Forest

    Sideboard
    1 Bronzebeak Foragers

- Blank lines and comment lines are ignored.
- A line that is exactly a section name (case-insensitive) starts that section. Each section may
  appear at most once, and every card line must come after a section header.
- A card line is ``<count> <exact card name>``, where count is a positive integer.
- A card listed twice in one section has its counts added together.

Parsing only reads the file. Whether the names exist is checked against the card data
(``resolve.data.cards``), and deck legality (size, singleton, color identity) belongs to deck
validation, not to this parser.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class Section(Enum):
    """A decklist section. The value is the header as written in ``decks/`` files.

    The commander is the card designated in 903.3; the sideboard is the optional card pool of
    100.4, which is out of scope for card coverage.
    """

    COMMANDER = "Commander"
    MAINBOARD = "Mainboard"
    SIDEBOARD = "Sideboard"


_SECTIONS_BY_HEADER = {section.value.casefold(): section for section in Section}
_CARD_LINE = re.compile(r"^(?P<count>\d+)\s+(?P<name>\S.*)$")


class DecklistError(ValueError):
    """The decklist text is malformed."""

    def __init__(self, message: str, *, line: int | None = None, source: str | None = None) -> None:
        location = ""
        if source is not None and line is not None:
            location = f"{source}:{line}: "
        elif line is not None:
            location = f"line {line}: "
        super().__init__(f"{location}{message}")
        self.line = line
        self.source = source


@dataclass(frozen=True)
class DeckEntry:
    """One card line: how many copies, and the exact card name as written."""

    count: int
    name: str


@dataclass(frozen=True)
class Decklist:
    """A parsed decklist. Entries keep the order of their first appearance in the file."""

    commander: tuple[DeckEntry, ...] = ()
    mainboard: tuple[DeckEntry, ...] = ()
    sideboard: tuple[DeckEntry, ...] = ()
    name: str | None = None

    def section(self, section: Section) -> tuple[DeckEntry, ...]:
        """The entries of one section."""
        match section:
            case Section.COMMANDER:
                return self.commander
            case Section.MAINBOARD:
                return self.mainboard
            case Section.SIDEBOARD:
                return self.sideboard

    def entries(self, *, include_sideboard: bool = False) -> tuple[DeckEntry, ...]:
        """Commander entries, then mainboard entries (then sideboard entries, if asked)."""
        entries = self.commander + self.mainboard
        return entries + self.sideboard if include_sideboard else entries

    def unique_names(self, *, include_sideboard: bool = False) -> tuple[str, ...]:
        """Each card name once, in order of first appearance."""
        names = (entry.name for entry in self.entries(include_sideboard=include_sideboard))
        return tuple(dict.fromkeys(names))

    def card_count(self, *, include_sideboard: bool = False) -> int:
        """Total copies in the commander and mainboard sections (and sideboard, if asked).

        For a Commander deck this is the deck size of 903.5a, which must be 100; the parser
        reports it but doesn't enforce it.
        """
        return sum(entry.count for entry in self.entries(include_sideboard=include_sideboard))


def parse_decklist(text: str, *, name: str | None = None) -> Decklist:
    """Parse decklist text. ``name`` labels the deck and appears in error messages."""
    sections: dict[Section, dict[str, int]] = {}
    current: dict[str, int] | None = None

    for number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        section = _SECTIONS_BY_HEADER.get(line.casefold())
        if section is not None:
            if section in sections:
                raise DecklistError(
                    f"section {section.value!r} appears more than once", line=number, source=name
                )
            current = sections[section] = {}
            continue

        match = _CARD_LINE.match(line)
        if match is None:
            raise DecklistError(
                f"expected '<count> <card name>' or a section header, got {line!r}",
                line=number,
                source=name,
            )
        if current is None:
            raise DecklistError(
                "card line before any section header (Commander, Mainboard or Sideboard)",
                line=number,
                source=name,
            )
        count = int(match["count"])
        if count < 1:
            raise DecklistError(f"count must be at least 1, got {count}", line=number, source=name)
        card_name = match["name"].strip()
        current[card_name] = current.get(card_name, 0) + count

    def entries(section: Section) -> tuple[DeckEntry, ...]:
        counts = sections.get(section, {})
        return tuple(DeckEntry(count, card) for card, count in counts.items())

    return Decklist(
        commander=entries(Section.COMMANDER),
        mainboard=entries(Section.MAINBOARD),
        sideboard=entries(Section.SIDEBOARD),
        name=name,
    )


def load_decklist(path: Path) -> Decklist:
    """Read and parse a decklist file; the deck is named after the file's stem."""
    return parse_decklist(path.read_text(encoding="utf-8"), name=path.stem)
