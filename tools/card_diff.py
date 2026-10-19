"""Compare two card data snapshots for the cards that matter: implemented cards and deck cards.

Usage::

    uv run python tools/card_diff.py OLD NEW
    uv run python tools/card_diff.py OLD NEW decks/byrke_counters.txt   # only these decks

``OLD`` and ``NEW`` are snapshot folders (as in ``data/``) or card data excerpts (``.json``).
The cards compared are every card with a definition (``resolve.cards.definitions``) plus every
card in the decklists (default: ``decks/*.txt``; sideboards included). For each card the report
lists a card missing from either snapshot (renamed or removed), and changes to each face's name,
mana cost, type line, Oracle text (word diff: ``[-old-]`` ``{+new+}``), power, toughness, loyalty
and defense, and to the rulings (added or removed, matched by text). The exit status is 0
whatever the differences are, and 1 if a snapshot or decklist can't be read.
"""

from __future__ import annotations

import argparse
import io
import sys
from collections.abc import Sequence
from pathlib import Path

from resolve.cards.registry import default_registry
from resolve.data.cards import (
    CardData,
    CardDatabase,
    CardDataError,
    load_card_database,
    load_card_excerpt,
)
from resolve.data.decklist import DecklistError, load_decklist
from resolve.data.rules_text import word_diff

REPO_ROOT = Path(__file__).resolve().parents[1]
DECKS_DIR = REPO_ROOT / "decks"
_CARD_FIELDS = ("name", "layout", "mana_value", "color_identity")
_FACE_FIELDS = (
    "name",
    "mana_cost",
    "type_line",
    "colors",
    "power",
    "toughness",
    "loyalty",
    "defense",
)


def load_database(path: Path) -> CardDatabase:
    """Load a snapshot folder or a ``.json`` excerpt."""
    if path.is_file():
        return load_card_excerpt(path)
    return load_card_database(path, verify=False)


def card_changes(
    old: CardData, new: CardData, old_db: CardDatabase, new_db: CardDatabase
) -> list[str]:
    """Describe how one card differs between the snapshots; empty if it doesn't."""
    changes: list[str] = []
    for field in _CARD_FIELDS:
        a, b = getattr(old, field), getattr(new, field)
        if a != b:
            changes.append(f"{field}: {a!r} -> {b!r}")
    if len(old.faces) != len(new.faces):
        changes.append(f"faces: {len(old.faces)} -> {len(new.faces)}")
    for before, after in zip(old.faces, new.faces, strict=False):
        label = f"[{before.name}] " if len(old.faces) > 1 else ""
        for field in _FACE_FIELDS:
            a, b = getattr(before, field), getattr(after, field)
            if a != b:
                changes.append(f"{label}{field}: {a!r} -> {b!r}")
        if before.oracle_text.split() != after.oracle_text.split():
            changes.append(
                f"{label}oracle text: {word_diff(before.oracle_text, after.oracle_text)}"
            )
    old_rulings = {r.comment: r for r in old_db.rulings_for(old)}
    new_rulings = {r.comment: r for r in new_db.rulings_for(new)}
    changes += [
        f"ruling removed ({r.published_at}): {r.comment}"
        for c, r in old_rulings.items()
        if c not in new_rulings
    ]
    changes += [
        f"ruling added ({r.published_at}): {r.comment}"
        for c, r in new_rulings.items()
        if c not in old_rulings
    ]
    return changes


def find_card(name: str, database: CardDatabase) -> CardData | None:
    """The card with this name, or one of whose faces has it (a back face), or ``None``."""
    if name in database:
        return database.get(name)
    for card in database.cards():
        if name in card.face_names:
            return card
    return None


def compare(
    names: Sequence[str], old_db: CardDatabase, new_db: CardDatabase
) -> tuple[list[str], int]:
    """Report lines for the cards with these names, and how many were found in both snapshots.

    A name is looked up as a card name or a face name; a card named by several names (its faces)
    is reported once. A card absent from the new snapshot under its old name is looked up by
    Oracle ID, and reported as renamed if it is there (definitions are registered by name).
    """
    lines: list[str] = []
    checked = 0
    seen: set[str] = set()
    for name in names:
        old = find_card(name, old_db)
        if old is None:
            lines.append(f"{name}: not in the old snapshot")
            continue
        if old.oracle_id in seen:
            continue
        seen.add(old.oracle_id)
        new = find_card(old.name, new_db) or new_db.by_oracle_id(old.oracle_id)
        if new is None:
            lines.append(f"{old.name}: MISSING from the new snapshot (removed)")
            continue
        checked += 1
        changes = card_changes(old, new, old_db, new_db)
        renamed = new.name != old.name
        if renamed:
            lines.append(f"{old.name}: RENAMED to {new.name} (rename its definition and tests)")
        elif changes:
            lines.append(f"{old.name}:")
        lines += [f"  {change}" for change in changes]
    return lines, checked


def main(argv: Sequence[str] | None = None) -> int:
    """Print the report; the exit status is 1 if a snapshot or decklist can't be read."""
    parser = argparse.ArgumentParser(description="Compare two card data snapshots.")
    parser.add_argument("old", type=Path, help="the pinned snapshot folder or excerpt")
    parser.add_argument("new", type=Path, help="the new snapshot folder or excerpt")
    parser.add_argument("decks", nargs="*", type=Path, help="decklists (default: decks/*.txt)")
    args = parser.parse_args(argv)
    deck_paths: list[Path] = args.decks or sorted(DECKS_DIR.glob("*.txt"))
    try:
        old_db, new_db = load_database(args.old), load_database(args.new)
        deck_names = [
            name
            for path in deck_paths
            for name in load_decklist(path).unique_names(include_sideboard=True)
        ]
    except (CardDataError, DecklistError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    names = sorted(dict.fromkeys([*default_registry().names(), *deck_names]))
    lines, checked = compare(names, old_db, new_db)
    print(f"cards compared: {checked} of {len(names)} (implemented cards and deck cards)")
    print("\n".join(lines) if lines else "no differences")
    return 0


if __name__ == "__main__":
    # Redirected output would use the locale's code page, cp1252 on Windows, which can't encode
    # every card name or Oracle character; write UTF-8 everywhere (CLAUDE.md, Platform).
    stdout = sys.stdout
    if isinstance(stdout, io.TextIOWrapper):
        stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
