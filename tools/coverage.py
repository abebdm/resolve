"""Report which cards of each decklist are implemented, and which are missing.

Usage::

    uv run python tools/coverage.py                     # every deck in decks/
    uv run python tools/coverage.py decks/byrke_counters.txt
    uv run python tools/coverage.py --oracle            # also print Oracle text of missing cards

Sideboards are out of scope for coverage (see docs/roadmap.md) and are only counted with
``--include-sideboard``. The exit status is 1 if a deck can't be parsed or names a card that isn't
in the card data snapshot; with ``--require-complete`` it is also 1 if any card is missing.
"""

from __future__ import annotations

import argparse
import io
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from resolve.cards.coverage import CardCoverage, DeckCoverage, deck_coverage
from resolve.cards.registry import CardRegistry, default_registry
from resolve.data.cards import CardData, CardDatabase, CardDataError, load_card_database
from resolve.data.decklist import DecklistError, load_decklist

REPO_ROOT = Path(__file__).resolve().parents[1]
DECKS_DIR = REPO_ROOT / "decks"


def describe_card(card: CardData) -> list[str]:
    """The card's printed characteristics, one line each, for reading Oracle text in reports."""
    lines: list[str] = []
    for face in card.faces:
        header = face.name
        if face.mana_cost:
            header += f" {face.mana_cost}"
        lines.append(header)
        lines.append(face.type_line)
        lines.extend(face.oracle_text.splitlines())
        if face.power is not None or face.toughness is not None:
            lines.append(f"{face.power}/{face.toughness}")
        if face.loyalty is not None:
            lines.append(f"Loyalty {face.loyalty}")
        if face.defense is not None:
            lines.append(f"Defense {face.defense}")
    return lines


def _entry_line(entry: CardCoverage) -> str:
    sections = ", ".join(section.value for section in entry.sections)
    line = f"  {entry.count} {entry.name}  [{sections}]"
    if entry.card is not None and entry.missing_faces and entry.card.is_multi_faced:
        line += f"  (faces missing: {', '.join(entry.missing_faces)})"
    if entry.problem is not None:
        line += f"  -- {entry.problem}"
    return line


def format_report(coverage: DeckCoverage, *, show_oracle: bool = False) -> str:
    """One deck's report: counts, then unknown, missing and implemented cards, then keywords.

    With ``show_oracle``, each missing card is followed by its printed characteristics, which is
    what the coverage audit reads. The keyword summary counts Scryfall's keyword list over
    distinct cards.
    """
    total = sum(entry.count for entry in coverage.cards)
    lines = [
        f"== {coverage.deck_name} ==",
        f"{total} cards, {len(coverage.cards)} distinct: "
        f"{len(coverage.implemented)} implemented, {len(coverage.missing)} missing, "
        f"{len(coverage.unknown)} unknown",
    ]
    for title, entries in (
        ("Unknown (not in the card data)", coverage.unknown),
        ("Missing", coverage.missing),
        ("Implemented", coverage.implemented),
    ):
        if not entries:
            continue
        lines.append("")
        lines.append(f"{title}:")
        for entry in entries:
            lines.append(_entry_line(entry))
            if show_oracle and entry.card is not None and title == "Missing":
                lines.extend(f"      {text}" for text in describe_card(entry.card))
                lines.append("")

    keywords = Counter(
        keyword for entry in coverage.cards if entry.card for keyword in entry.card.keywords
    )
    if keywords:
        lines.append("")
        lines.append("Keywords (from Scryfall, distinct cards):")
        ordered = sorted(keywords.items(), key=lambda item: (-item[1], item[0]))
        lines.extend(f"  {keyword}: {count}" for keyword, count in ordered)
    return "\n".join(lines)


def run(
    deck_paths: Sequence[Path],
    database: CardDatabase,
    registry: CardRegistry,
    *,
    include_sideboard: bool = False,
    show_oracle: bool = False,
    require_complete: bool = False,
) -> tuple[str, int]:
    """Build the report text for the given decks; returns (report, exit status)."""
    status = 0
    sections: list[str] = []
    if database.snapshot is not None:
        sections.append(f"Card data: {database.snapshot.describe()}")
    sections.append(f"Registered definitions: {len(registry)}")
    for path in deck_paths:
        try:
            decklist = load_decklist(path)
        except (DecklistError, OSError) as error:
            sections.append(f"== {path} ==\nerror: {error}")
            status = 1
            continue
        coverage = deck_coverage(decklist, database, registry, include_sideboard=include_sideboard)
        sections.append(format_report(coverage, show_oracle=show_oracle))
        if coverage.unknown or (require_complete and not coverage.is_fully_implemented):
            status = 1
    return "\n\n".join(sections) + "\n", status


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line; returns the exit status described in the module docstring."""
    parser = argparse.ArgumentParser(description="Report implemented and missing cards per deck.")
    parser.add_argument("decks", nargs="*", type=Path, help="decklists (default: decks/*.txt)")
    parser.add_argument("--data-dir", type=Path, default=None, help="card data snapshot directory")
    parser.add_argument("--include-sideboard", action="store_true")
    parser.add_argument(
        "--oracle", action="store_true", help="print the Oracle text of each missing card"
    )
    parser.add_argument(
        "--require-complete", action="store_true", help="exit with 1 if any card is missing"
    )
    args = parser.parse_args(argv)

    deck_paths: list[Path] = args.decks or sorted(DECKS_DIR.glob("*.txt"))
    try:
        database = load_card_database(args.data_dir)
    except CardDataError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    report, status = run(
        deck_paths,
        database,
        default_registry(),
        include_sideboard=args.include_sideboard,
        show_oracle=args.oracle,
        require_complete=args.require_complete,
    )
    sys.stdout.write(report)
    return status


if __name__ == "__main__":
    # Redirected output would use the locale's code page, cp1252 on Windows, which can't encode
    # every card or path name; write UTF-8 everywhere (CLAUDE.md, Platform).
    stdout = sys.stdout
    if isinstance(stdout, io.TextIOWrapper):
        stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
