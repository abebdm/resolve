"""Tests for tools/card_excerpt.py and the committed excerpt it wrote (the fuzz harness's decks)."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

import pytest

from resolve.cards.registry import default_registry
from resolve.data.cards import CardDataError, load_card_excerpt
from resolve.data.decklist import DeckEntry, Decklist
from resolve.engine.deck import build_deck
from tests import scryfall_fixtures as fx
from tools import card_excerpt as excerpt_tool
from tools import fuzz as fuzz_tool

# Fields of a full Scryfall card object that an excerpt drops: printing data that changes daily.
PRINTING_FIELDS = {"id": "print-1", "prices": {"usd": "0.10"}, "set": "tst", "image_uris": {}}


def snapshot_with_printing_fields(data_dir: Path) -> None:
    """A fixture snapshot whose cards (and the transform card's faces) carry printing fields."""
    cards: list[dict[str, Any]] = []
    for card in fx.default_cards():
        full: dict[str, Any] = {**card, **PRINTING_FIELDS}
        faces: list[dict[str, Any]] | None = full.get("card_faces")
        if faces is not None:
            full["card_faces"] = [{**face, "image_uris": {}} for face in faces]
        cards.append(full)
    fx.write_snapshot(data_dir, cards)


def run(*args: str) -> tuple[int, str]:
    output = io.StringIO()
    with redirect_stdout(output):
        status = excerpt_tool.main(list(args))
    return status, output.getvalue()


def test_an_excerpt_holds_the_named_cards_trimmed_with_their_rulings(tmp_path: Path) -> None:
    data = tmp_path / "data"
    snapshot_with_printing_fields(data)
    path = tmp_path / "excerpt.json"
    status, text = run(
        str(path), "Test Daybreaker // Test Nightfall", "Forest", "--data-dir", str(data)
    )
    assert status == 0, text
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["format"] == 1
    assert raw["taken_from"]["files"]["oracle_cards"]["updated_at"] == fx.ORACLE_UPDATED_AT
    # The cards in the order named, without the printing fields, on the card or on a face.
    assert raw["cards"] == [fx.TRANSFORM_CARD, fx.FOREST]
    # Only the named cards' rulings: the transform card has one, Forest none, the elves aren't in.
    assert [r["comment"] for r in raw["rulings"]] == ["Placeholder ruling C."]
    database = load_card_excerpt(path)
    assert len(database) == 2
    assert database.get("Forest").type_line == "Basic Land — Forest"
    assert [r.comment for r in database.rulings_for(database.get("Test Daybreaker"))] == [
        "Placeholder ruling C."
    ]
    assert database.snapshot is not None and database.snapshot.describe() == "Snapshot 2026-10-18"


def test_the_excerpt_is_written_with_unix_line_endings_in_utf8(tmp_path: Path) -> None:
    data = tmp_path / "data"
    fx.write_snapshot(data)
    path = tmp_path / "excerpt.json"
    assert run(str(path), "Forest", "--data-dir", str(data))[0] == 0
    raw = path.read_bytes()
    assert b"\r\n" not in raw and raw.endswith(b"}\n")
    assert "Basic Land — Forest".encode() in raw  # not escaped as —


def test_check_passes_for_a_matching_excerpt(tmp_path: Path) -> None:
    data = tmp_path / "data"
    snapshot_with_printing_fields(data)
    path = tmp_path / "excerpt.json"
    run(str(path), "Forest", "Llanowar Elves", "--data-dir", str(data))
    status, text = run(str(path), "--check", "--data-dir", str(data))
    assert status == 0
    assert "2 cards match Snapshot 2026-10-18" in text


def test_check_fails_when_a_card_or_its_rulings_differ(tmp_path: Path) -> None:
    data = tmp_path / "data"
    fx.write_snapshot(data)
    path = tmp_path / "excerpt.json"
    run(str(path), "Forest", "Llanowar Elves", "--data-dir", str(data))
    changed_elves = {**fx.LLANOWAR_ELVES, "oracle_text": "{T}: Add {G}{G}."}
    fx.write_snapshot(data, [fx.FOREST, changed_elves], rulings=[])
    status, text = run(str(path), "--check", "--data-dir", str(data))
    assert status == 1
    assert "'Llanowar Elves' differs from the snapshot" in text
    assert "'Forest'" not in text
    assert "the rulings differ from the snapshot" in text


@pytest.mark.parametrize(
    ("cards", "message"),
    [
        ([fx.FOREST], "no card named 'Llanowar Elves'"),
        ([fx.FOREST, fx.LLANOWAR_ELVES, {**fx.LLANOWAR_ELVES, "oracle_id": "oid-2"}], "2 cards"),
    ],
    ids=["missing", "ambiguous"],
)
def test_a_name_that_isnt_exactly_one_card_is_refused(
    tmp_path: Path, cards: list[dict[str, Any]], message: str
) -> None:
    data = tmp_path / "data"
    fx.write_snapshot(data, cards)
    path = tmp_path / "excerpt.json"
    status, text = run(str(path), "Llanowar Elves", "--data-dir", str(data))
    assert status == 1
    assert message in text
    assert not path.exists()


def test_a_token_with_the_name_isnt_a_match(tmp_path: Path) -> None:
    """Tokens can't be in a deck, so the loader doesn't index them; neither does the excerpt."""
    data = tmp_path / "data"
    fx.write_snapshot(data, [fx.FOREST, fx.token("oid-forest-token", "Forest")])
    path = tmp_path / "excerpt.json"
    assert run(str(path), "Forest", "--data-dir", str(data))[0] == 0
    assert [
        card["oracle_id"] for card in json.loads(path.read_text(encoding="utf-8"))["cards"]
    ] == ["oid-forest"]


def test_without_a_snapshot_the_tool_says_how_to_get_one(tmp_path: Path) -> None:
    status, text = run(str(tmp_path / "excerpt.json"), "Forest", "--data-dir", str(tmp_path))
    assert status == 1
    assert "tools/fetch_scryfall.py" in text


@pytest.mark.parametrize("args", [["excerpt.json"], ["excerpt.json", "Forest", "--check"]])
def test_names_or_check_but_not_both(args: list[str]) -> None:
    with pytest.raises(SystemExit) as exit_info, redirect_stdout(io.StringIO()):
        excerpt_tool.main(args)
    assert exit_info.value.code == 2


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("not json", "invalid JSON"),
        ('{"format": 2}', "unsupported excerpt format 2"),
        ('{"format": 1, "cards": [], "rulings": []}', "taken_from"),
    ],
)
def test_a_malformed_excerpt_is_refused(tmp_path: Path, text: str, message: str) -> None:
    path = tmp_path / "excerpt.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(CardDataError, match=message):
        load_card_excerpt(path)


def test_a_missing_excerpt_is_refused(tmp_path: Path) -> None:
    with pytest.raises(CardDataError, match="can't read the card data excerpt"):
        load_card_excerpt(tmp_path / "missing.json")


# --- The committed excerpt ----------------------------------------------------------------------


def test_the_basic_lands_excerpt_holds_the_five_basic_lands() -> None:
    """The fuzz harness's decks. The expected values are the basic lands' printed
    characteristics: no mana cost (202.1a, so mana value 0, 202.3), the supertype basic and the
    land type of the same name (205.4a, 305.6), reminder text only, colorless (105.2c, lands have
    no color indicator) and the color identity of their mana symbol (903.4)."""
    database = load_card_excerpt(fuzz_tool.BASIC_LANDS_EXCERPT)
    symbols = {"Plains": "W", "Island": "U", "Swamp": "B", "Mountain": "R", "Forest": "G"}
    assert len(database) == 5
    for name, symbol in symbols.items():
        card = database.get(name)
        assert card.layout == "normal"
        assert card.type_line == f"Basic Land — {name}"
        assert card.mana_value == 0.0
        assert card.color_identity == (symbol,)
        assert card.keywords == ()
        (face,) = card.faces
        assert face.mana_cost == ""
        assert face.oracle_text == f"({{T}}: Add {{{symbol}}}.)"
        assert face.colors == ()
        assert database.rulings_for(card) == ()
    snapshot = database.snapshot
    assert snapshot is not None
    assert snapshot.oracle_cards.source.startswith("https://data.scryfall.io/oracle-cards/")


def test_the_excerpt_lists_the_basic_lands_in_the_harness_order() -> None:
    raw = json.loads(fuzz_tool.BASIC_LANDS_EXCERPT.read_text(encoding="utf-8"))
    assert [card["name"] for card in raw["cards"]] == list(fuzz_tool.BASIC_LAND_NAMES)
    assert excerpt_tool.excerpt_names(fuzz_tool.BASIC_LANDS_EXCERPT) == list(
        fuzz_tool.BASIC_LAND_NAMES
    )


def test_the_basic_lands_excerpt_builds_decks_with_the_real_definitions() -> None:
    decklist = Decklist(mainboard=(DeckEntry(2, "Island"), DeckEntry(1, "Forest")))
    deck = build_deck(
        decklist, load_card_excerpt(fuzz_tool.BASIC_LANDS_EXCERPT), default_registry()
    )
    assert [card.data.name for card in deck.cards] == ["Island", "Island", "Forest"]
    assert [card.definitions for card in deck.cards][2] == (default_registry().get("Forest"),)
