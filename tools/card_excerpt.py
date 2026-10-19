"""Write a card data excerpt from the local snapshot, or check one against it.

Usage::

    uv run python tools/card_excerpt.py EXCERPT NAME [NAME ...]   # write EXCERPT with these cards
    uv run python tools/card_excerpt.py EXCERPT --check            # compare EXCERPT with data/

The fuzz harness's basic lands are ``tools/excerpts/basic_lands.json`` (Plains, Island, Swamp,
Mountain and Forest, in that order).

An excerpt is a few cards' records copied from the Scryfall snapshot in ``data/`` and committed,
so a tool can use those cards on a machine without the snapshot (CI, a fresh checkout). The
records are copied, never written by hand: each card object is trimmed to the fields the loader
reads (``EXCERPT_CARD_FIELDS``, on the card and on each face), with the cards' rulings, and the
excerpt records the manifest of the snapshot it was taken from. ``load_card_excerpt`` reads it.

With names, the excerpt is (re)written with those cards, in that order. With ``--check``, the
cards and rulings already in the excerpt are compared with the snapshot's; the snapshot they
came from may be older, so ``taken_from`` isn't compared.

Exit status: 0 written, or the excerpt matches; 1 a card is missing or ambiguous, the excerpt
differs from the snapshot, or the card data can't be read; 2 bad arguments.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from resolve.data.cards import (
    EXCERPT_CARD_FIELDS,
    EXCERPT_FORMAT,
    NON_DECK_LAYOUTS,
    CardDataError,
    SnapshotInfo,
    as_json_list,
    as_json_object,
    default_data_dir,
    load_card_excerpt,
    load_snapshot_info,
    read_jsonl_gz,
    sha256_of,
)


def trim_card(card: Mapping[str, object]) -> dict[str, object]:
    """A Scryfall card object with only ``EXCERPT_CARD_FIELDS``, on the card and on each face."""
    trimmed: dict[str, object] = {}
    for field in EXCERPT_CARD_FIELDS:
        if field not in card:
            continue
        value = card[field]
        if field == "card_faces":
            faces = as_json_list(value, f"card_faces of {card.get('name')!r}")
            value = [trim_card(as_json_object(face, "card face")) for face in faces]
        trimmed[field] = value
    return trimmed


def read_snapshot(data_dir: Path) -> tuple[SnapshotInfo, list[dict[str, object]], list[object]]:
    """The snapshot's manifest, card objects and ruling objects, checked against the manifest."""
    snapshot = load_snapshot_info(data_dir)
    payloads: list[list[object]] = []
    for info in (snapshot.oracle_cards, snapshot.rulings):
        path = data_dir / info.file
        if not path.exists() or sha256_of(path) != info.sha256:
            raise CardDataError(f"{path} is missing or doesn't match its SHA-256 in the manifest")
        payloads.append(read_jsonl_gz(path))
    cards = [as_json_object(card, "card") for card in payloads[0]]
    return snapshot, cards, payloads[1]


def excerpt_of(
    names: Sequence[str],
    snapshot: SnapshotInfo,
    cards: Sequence[Mapping[str, object]],
    rulings: Sequence[object],
) -> dict[str, object]:
    """The excerpt holding the cards named ``names`` (in that order) and their rulings.

    Each name must belong to exactly one card a deck can contain (``NON_DECK_LAYOUTS`` are
    skipped, as the loader does); otherwise ``CardDataError``.
    """
    chosen: list[dict[str, object]] = []
    for name in names:
        found = [
            card
            for card in cards
            if card.get("name") == name and card.get("layout") not in NON_DECK_LAYOUTS
        ]
        if len(found) != 1:
            what = "no card" if not found else f"{len(found)} cards"
            raise CardDataError(f"{what} named {name!r} in the snapshot")
        chosen.append(trim_card(found[0]))
    oracle_ids = {card.get("oracle_id") for card in chosen}
    kept = [
        ruling
        for ruling in rulings
        if as_json_object(ruling, "ruling").get("oracle_id") in oracle_ids
    ]
    return {
        "format": EXCERPT_FORMAT,
        "taken_from": snapshot.to_json(),
        "cards": chosen,
        "rulings": kept,
    }


def write_excerpt(path: Path, excerpt: Mapping[str, object]) -> None:
    """Write ``excerpt`` as UTF-8 JSON with ``\\n`` line endings: the same bytes everywhere."""
    text = json.dumps(excerpt, ensure_ascii=False, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def excerpt_differences(path: Path, current: Mapping[str, object]) -> list[str]:
    """How the excerpt at ``path`` differs from ``current`` (the same cards, from the snapshot).

    Compares the cards and the rulings, not ``taken_from``.
    """
    load_card_excerpt(path)  # refuses a malformed excerpt
    stored = as_json_object(json.loads(path.read_text(encoding="utf-8")), str(path))
    problems: list[str] = []
    stored_cards = as_json_list(stored.get("cards"), "cards")
    current_cards = as_json_list(current.get("cards"), "cards")
    for old, new in zip(stored_cards, current_cards, strict=True):
        if old != new:
            name = as_json_object(old, "card").get("name")
            problems.append(f"{name!r} differs from the snapshot")
    if stored.get("rulings") != current.get("rulings"):
        problems.append("the rulings differ from the snapshot")
    return problems


def excerpt_names(path: Path) -> list[str]:
    """The names of the cards in the excerpt at ``path``, in order."""
    load_card_excerpt(path)  # refuses a malformed excerpt
    stored = as_json_object(json.loads(path.read_text(encoding="utf-8")), str(path))
    cards = as_json_list(stored.get("cards"), "cards")
    return [str(as_json_object(card, "card").get("name")) for card in cards]


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line; returns the exit status described in the module docstring."""
    parser = argparse.ArgumentParser(
        description="Write a card data excerpt from the snapshot, or check one against it."
    )
    parser.add_argument("excerpt", type=Path, help="the excerpt file")
    parser.add_argument("names", nargs="*", help="exact card names to write, in order")
    parser.add_argument("--check", action="store_true", help="compare the excerpt with data/")
    parser.add_argument("--data-dir", type=Path, default=None, help="card data snapshot directory")
    args = parser.parse_args(argv)
    if args.check == bool(args.names):
        parser.error("give card names to write an excerpt, or --check to check one")
    data_dir: Path = default_data_dir() if args.data_dir is None else args.data_dir
    path: Path = args.excerpt
    try:
        names: list[str] = excerpt_names(path) if args.check else args.names
        snapshot, cards, rulings = read_snapshot(data_dir)
        excerpt = excerpt_of(names, snapshot, cards, rulings)
        if args.check:
            problems = excerpt_differences(path, excerpt)
            if problems:
                print(f"{path} doesn't match {snapshot.describe()}:")
                print("\n".join(f"- {problem}" for problem in problems))
                return 1
            print(f"{path}: {len(names)} cards match {snapshot.describe()}.")
            return 0
        write_excerpt(path, excerpt)
    except (CardDataError, OSError, ValueError) as error:
        print(f"error: {error}")
        return 1
    print(f"Wrote {len(names)} cards from {snapshot.describe()} to {path}.")
    return 0


if __name__ == "__main__":
    # Redirected output would use the locale's code page, cp1252 on Windows, which can't encode
    # every card or path name; write UTF-8 everywhere (CLAUDE.md, Platform).
    stdout = sys.stdout
    if isinstance(stdout, io.TextIOWrapper):
        stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
