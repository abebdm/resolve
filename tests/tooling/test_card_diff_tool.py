"""Tests for tools/card_diff.py, on small hand-made snapshots."""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

from resolve.data.cards import CardDatabase
from tests import scryfall_fixtures as fx
from tools import card_diff as tool


def run(*args: str) -> tuple[int, str]:
    output = io.StringIO()
    with redirect_stdout(output):
        status = tool.main(list(args))
    return status, output.getvalue()


def deck(tmp_path: Path, *names: str) -> str:
    path = tmp_path / "deck.txt"
    path.write_text(
        "Mainboard\n" + "\n".join(f"1 {name}" for name in names) + "\n", encoding="utf-8"
    )
    return str(path)


def snapshots(
    tmp_path: Path, new_cards: list[dict[str, object]], new_rulings: list[dict[str, object]]
) -> tuple[str, str]:
    fx.write_snapshot(tmp_path / "old", fx.default_cards(), fx.default_rulings())
    fx.write_snapshot(tmp_path / "new", new_cards, new_rulings)  # type: ignore[arg-type]
    return str(tmp_path / "old"), str(tmp_path / "new")


def test_identical_snapshots_have_no_differences(tmp_path: Path) -> None:
    old, new = snapshots(tmp_path, fx.default_cards(), fx.default_rulings())  # type: ignore[arg-type]
    status, text = run(old, new, deck(tmp_path, "Llanowar Elves", "Forest"))
    assert status == 0
    # Implemented cards the tiny fixture snapshots lack are listed; nothing else is.
    assert "Llanowar Elves:" not in text and "Forest:" not in text
    assert "MISSING" not in text and "oracle text" not in text


def test_changed_text_type_line_cost_and_rulings_are_reported(tmp_path: Path) -> None:
    elves = {
        **fx.LLANOWAR_ELVES,
        "oracle_text": "{T}: Add {R}.",
        "type_line": "Creature — Elf",
        "mana_cost": "{2}{G}",
    }
    rulings = [r for r in fx.default_rulings() if r["comment"] != "Placeholder ruling B."]
    rulings.append(fx.ruling("oid-llanowar-elves", "2026-01-01", "A new ruling."))
    cards = [elves if c["name"] == "Llanowar Elves" else c for c in fx.default_cards()]
    old, new = snapshots(tmp_path, cards, rulings)  # type: ignore[arg-type]
    status, text = run(old, new, deck(tmp_path, "Llanowar Elves", "Forest"))
    assert status == 0
    assert "Llanowar Elves:" in text
    assert "mana_cost:" in text and "type_line:" in text
    assert "oracle text: {T}: Add [-{G}.-] {+{R}.+}" in text
    assert "ruling removed (2020-06-01): Placeholder ruling B." in text
    assert "ruling added (2026-01-01): A new ruling." in text
    assert "Forest:" not in text


def test_a_card_missing_from_the_new_snapshot_is_reported(tmp_path: Path) -> None:
    cards = [c for c in fx.default_cards() if c["name"] != "Llanowar Elves"]
    old, new = snapshots(tmp_path, cards, [])  # type: ignore[arg-type]
    _, text = run(old, new, deck(tmp_path, "Llanowar Elves"))
    assert "Llanowar Elves: MISSING from the new snapshot" in text


def test_every_implemented_card_is_compared_even_if_no_deck_names_it(tmp_path: Path) -> None:
    forest = {**fx.FOREST, "oracle_text": "({T}: Add {G}. Changed.)"}
    cards = [forest if c["name"] == "Forest" else c for c in fx.default_cards()]
    old, new = snapshots(tmp_path, cards, fx.default_rulings())  # type: ignore[arg-type]
    _, text = run(old, new, deck(tmp_path, "Llanowar Elves"))  # Forest is a basic land definition
    assert "Forest:" in text


def test_an_unreadable_snapshot_is_an_error(tmp_path: Path) -> None:
    status, _ = run(str(tmp_path / "missing1"), str(tmp_path / "missing2"), deck(tmp_path, "X"))
    assert status == 1


def databases(tmp_path: Path, new_cards: list[dict[str, Any]]) -> tuple[CardDatabase, CardDatabase]:
    old, new = snapshots(tmp_path, new_cards, fx.default_rulings())  # type: ignore[arg-type]
    return tool.load_database(Path(old)), tool.load_database(Path(new))


def test_card_level_fields_and_color_indicators_are_compared(tmp_path: Path) -> None:
    elves = {**fx.LLANOWAR_ELVES, "color_identity": ["G", "U"], "layout": "saga", "cmc": 3.0}
    forest = {**fx.FOREST, "colors": ["G"]}
    cards = [elves if c["name"] == "Llanowar Elves" else c for c in fx.default_cards()]
    cards = [forest if c["name"] == "Forest" else c for c in cards]
    old_db, new_db = databases(tmp_path, cards)
    lines, checked = tool.compare(["Llanowar Elves", "Forest"], old_db, new_db)
    text = "\n".join(lines)
    assert checked == 2
    assert "color_identity: ('G',) -> ('G', 'U')" in text
    assert "layout: 'normal' -> 'saga'" in text
    assert "mana_value: 1.0 -> 3.0" in text
    assert "colors: () -> ('G',)" in text, "a color indicator on a face"


def test_a_card_renamed_by_errata_is_matched_by_oracle_id(tmp_path: Path) -> None:
    renamed = {**fx.LLANOWAR_ELVES, "name": "Llanowar Elf"}
    cards = [renamed if c["name"] == "Llanowar Elves" else c for c in fx.default_cards()]
    old_db, new_db = databases(tmp_path, cards)
    lines, checked = tool.compare(["Llanowar Elves"], old_db, new_db)
    assert checked == 1
    assert lines[0] == "Llanowar Elves: RENAMED to Llanowar Elf (rename its definition and tests)"
    assert "MISSING" not in "\n".join(lines)


def test_a_back_face_name_finds_its_card_and_each_card_is_reported_once(tmp_path: Path) -> None:
    changed = {
        **fx.TRANSFORM_CARD,
        "card_faces": [
            {**fx.TRANSFORM_CARD["card_faces"][0], "oracle_text": "Changed."},
            fx.TRANSFORM_CARD["card_faces"][1],
        ],
    }
    cards = [changed if c["name"] == changed["name"] else c for c in fx.default_cards()]
    old_db, new_db = databases(tmp_path, cards)
    names = ["Test Nightfall", "Test Daybreaker"]  # the back face first, then the front
    lines, checked = tool.compare(names, old_db, new_db)
    assert checked == 1
    assert "not in the old snapshot" not in "\n".join(lines)
    assert [line for line in lines if not line.startswith("  ")] == [
        "Test Daybreaker // Test Nightfall:"
    ]
    assert any("[Test Daybreaker] oracle text:" in line for line in lines)
