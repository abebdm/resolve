"""Tests for the card data loader (resolve.data.cards)."""

from __future__ import annotations

import copy
import json
import pickle
from pathlib import Path
from typing import Any

import pytest

from resolve.data.cards import (
    NON_DECK_LAYOUTS,
    ORACLE_CARDS_FILE,
    SNAPSHOT_FILE,
    AmbiguousCardNameError,
    CardDatabase,
    CardDataError,
    UnknownCardError,
    load_card_database,
    load_snapshot_info,
    parse_card,
    parse_oracle_cards,
    parse_rulings,
)
from tests import scryfall_fixtures as fx


def make_database(
    cards: list[dict[str, Any]] | None = None, rulings: list[dict[str, Any]] | None = None
) -> CardDatabase:
    return CardDatabase(
        parse_oracle_cards(fx.default_cards() if cards is None else cards),
        parse_rulings(fx.default_rulings() if rulings is None else rulings),
    )


# --- Parsing ------------------------------------------------------------------------------------


def test_single_faced_card_has_one_face_with_its_characteristics() -> None:
    card = parse_card(fx.LLANOWAR_ELVES)
    assert card.name == "Llanowar Elves"
    assert card.oracle_id == "oid-llanowar-elves"
    assert card.layout == "normal"
    assert card.mana_value == 1.0
    assert card.color_identity == ("G",)
    assert not card.is_multi_faced
    assert card.face_names == ("Llanowar Elves",)
    (face,) = card.faces
    assert face.mana_cost == "{G}"
    assert face.type_line == "Creature — Elf Druid"
    assert face.oracle_text == "{T}: Add {G}."
    assert (face.power, face.toughness) == ("1", "1")
    assert face.loyalty is None and face.defense is None
    assert face.colors == ("G",)


def test_land_without_power_has_none_power_and_empty_cost() -> None:
    (face,) = parse_card(fx.FOREST).faces
    assert face.mana_cost == ""
    assert face.power is None and face.toughness is None
    assert face.colors == ()


def test_transforming_card_keeps_each_face() -> None:
    card = parse_card(fx.TRANSFORM_CARD)
    assert card.is_multi_faced
    assert card.face_names == ("Test Daybreaker", "Test Nightfall")
    assert card.faces[1].power == "4"
    assert card.keywords == ("Trample", "Transform")


def test_split_card_faces_inherit_card_colors() -> None:
    """Scryfall puts a split card's colors on the card, not on each face."""
    card = parse_card(fx.SPLIT_CARD)
    assert [face.colors for face in card.faces] == [("R", "U"), ("R", "U")]
    assert card.faces[1].oracle_text == "Tap target permanent.\nDraw a card."


def test_star_power_stays_a_string() -> None:
    card = parse_card(fx.simple_card("Test Star", "oid-star", power="*", toughness="1+*"))
    assert (card.faces[0].power, card.faces[0].toughness) == ("*", "1+*")


def test_reversible_card_takes_oracle_id_from_its_face() -> None:
    raw = {
        "object": "card",
        "name": "Test Reversible // Test Reversible",
        "layout": "reversible_card",
        "card_faces": [
            {"name": "Test Reversible", "oracle_id": "oid-face", "type_line": "Artifact"},
            {"name": "Test Reversible", "oracle_id": "oid-face", "type_line": "Artifact"},
        ],
    }
    assert parse_card(raw).oracle_id == "oid-face"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"name": None}, "name"),
        ({"oracle_id": None}, "oracle_id"),
        ({"cmc": "1"}, "cmc"),
        ({"cmc": True}, "cmc"),
        ({"colors": "G"}, "colors"),
        ({"keywords": [1]}, "keywords"),
        ({"oracle_text": 3}, "oracle_text"),
    ],
)
def test_malformed_card_is_refused(change: dict[str, Any], message: str) -> None:
    raw = {**fx.LLANOWAR_ELVES, **change}
    raw = {key: value for key, value in raw.items() if value is not None}
    with pytest.raises(CardDataError, match=message):
        parse_card(raw)


def test_card_with_empty_faces_is_refused() -> None:
    with pytest.raises(CardDataError, match="card_faces is empty"):
        parse_card({**fx.TRANSFORM_CARD, "card_faces": []})


def test_bulk_files_must_be_lists() -> None:
    with pytest.raises(CardDataError, match="expected a JSON list"):
        parse_oracle_cards({"data": []})
    with pytest.raises(CardDataError, match="expected a JSON list"):
        parse_rulings("nope")


def test_card_data_survives_deepcopy_and_pickle() -> None:
    """Card data may be referenced from game state, which must deepcopy and pickle."""
    card = parse_card(fx.TRANSFORM_CARD)
    assert copy.deepcopy(card) == card
    assert pickle.loads(pickle.dumps(card)) == card


# --- Lookup -------------------------------------------------------------------------------------


def test_lookup_by_exact_name() -> None:
    database = make_database()
    assert database.get("Llanowar Elves").oracle_id == "oid-llanowar-elves"
    assert "Llanowar Elves" in database


@pytest.mark.parametrize("name", ["llanowar elves", "Llanowar Elves ", "Llanowar Elf", ""])
def test_lookup_is_exact_and_never_approximate(name: str) -> None:
    database = make_database()
    assert name not in database
    with pytest.raises(UnknownCardError) as caught:
        database.get(name)
    assert caught.value.name == name
    assert repr(name) in str(caught.value)


def test_unknown_card_error_is_a_key_error() -> None:
    with pytest.raises(KeyError):
        make_database().get("No Such Card")


def test_multi_faced_card_found_by_full_name_and_front_face_but_not_back_face() -> None:
    database = make_database()
    card = database.get("Test Daybreaker // Test Nightfall")
    assert database.get("Test Daybreaker") is card
    assert database.get("Test Spark") is database.get("Test Spark // Test Frost")
    with pytest.raises(UnknownCardError):
        database.get("Test Nightfall")


def test_full_card_name_wins_over_front_face_alias() -> None:
    """A card actually named like another card's front face is never shadowed by the alias."""
    real = fx.simple_card("Test Daybreaker", "oid-real-daybreaker")
    database = make_database([fx.TRANSFORM_CARD, real])
    assert database.get("Test Daybreaker").oracle_id == "oid-real-daybreaker"


@pytest.mark.parametrize("layout", sorted(NON_DECK_LAYOUTS))
def test_non_deck_layouts_are_not_indexed(layout: str) -> None:
    other = {**fx.token("oid-x", name="Test Object"), "layout": layout}
    database = make_database([fx.LLANOWAR_ELVES, other])
    assert "Test Object" not in database
    assert len(database) == 1


def test_tokens_sharing_a_name_do_not_make_it_ambiguous() -> None:
    database = make_database([fx.token("oid-1"), fx.token("oid-2"), fx.LLANOWAR_ELVES])
    assert "Soldier" not in database
    assert database.get("Llanowar Elves").name == "Llanowar Elves"


def test_duplicate_card_names_are_ambiguous() -> None:
    cards = [
        fx.simple_card("Test Twin", "oid-b"),
        fx.simple_card("Test Twin", "oid-a"),
        fx.simple_card("Test Twin", "oid-c"),
    ]
    database = make_database(cards)
    assert "Test Twin" not in database
    with pytest.raises(AmbiguousCardNameError) as caught:
        database.get("Test Twin")
    assert caught.value.oracle_ids == ("oid-a", "oid-b", "oid-c")


def test_ambiguous_front_face_alias_is_not_created() -> None:
    """An alias that would collide with an ambiguous full name stays ambiguous."""
    cards = [
        fx.simple_card("Test Daybreaker", "oid-a"),
        fx.simple_card("Test Daybreaker", "oid-b"),
        fx.TRANSFORM_CARD,
    ]
    with pytest.raises(AmbiguousCardNameError):
        make_database(cards).get("Test Daybreaker")


def test_empty_database() -> None:
    database = make_database([], [])
    assert len(database) == 0
    assert "Forest" not in database


# --- Rulings ------------------------------------------------------------------------------------


def test_rulings_sorted_by_publication_date() -> None:
    database = make_database()
    rulings = database.rulings_for(database.get("Llanowar Elves"))
    assert [r.comment for r in rulings] == ["Placeholder ruling A.", "Placeholder ruling B."]
    assert rulings[0].source == "wotc"


def test_rulings_on_the_same_date_keep_scryfall_order() -> None:
    rulings = [
        fx.ruling("oid-forest", "2020-01-01", "first"),
        fx.ruling("oid-forest", "2020-01-01", "second"),
    ]
    database = make_database(rulings=rulings)
    comments = [r.comment for r in database.rulings_for(database.get("Forest"))]
    assert comments == ["first", "second"]


def test_card_without_rulings_has_none() -> None:
    database = make_database()
    assert database.rulings_for(database.get("Forest")) == ()


# --- Loading a snapshot from disk ---------------------------------------------------------------


def test_load_card_database_from_snapshot(tmp_path: Path) -> None:
    fx.write_snapshot(tmp_path)
    database = load_card_database(tmp_path)
    assert len(database) == 4  # the token is not indexed
    assert database.get("Forest").layout == "normal"
    assert database.snapshot is not None
    assert database.snapshot.date.isoformat() == "2026-10-18"
    assert len(database.rulings_for(database.get("Llanowar Elves"))) == 2


def test_missing_snapshot_explains_how_to_fetch(tmp_path: Path) -> None:
    with pytest.raises(CardDataError, match="fetch_scryfall"):
        load_card_database(tmp_path)


def test_modified_file_is_refused(tmp_path: Path) -> None:
    fx.write_snapshot(tmp_path)
    path = tmp_path / ORACLE_CARDS_FILE
    path.write_bytes(path.read_bytes().replace(b"Llanowar", b"Llanowor"))
    with pytest.raises(CardDataError, match="SHA-256"):
        load_card_database(tmp_path)


def test_verification_can_be_skipped(tmp_path: Path) -> None:
    fx.write_snapshot(tmp_path)
    path = tmp_path / ORACLE_CARDS_FILE
    path.write_bytes(path.read_bytes().replace(b"Llanowar", b"Llanowor"))
    assert "Llanowor Elves" in load_card_database(tmp_path, verify=False)


def test_file_listed_in_manifest_but_missing_is_refused(tmp_path: Path) -> None:
    fx.write_snapshot(tmp_path)
    (tmp_path / ORACLE_CARDS_FILE).unlink()
    with pytest.raises(CardDataError, match="missing"):
        load_card_database(tmp_path)


def test_unsupported_manifest_format_is_refused(tmp_path: Path) -> None:
    fx.write_snapshot(tmp_path)
    manifest = json.loads((tmp_path / SNAPSHOT_FILE).read_text())
    manifest["format"] = 99
    (tmp_path / SNAPSHOT_FILE).write_text(json.dumps(manifest))
    with pytest.raises(CardDataError, match="unsupported snapshot format"):
        load_snapshot_info(tmp_path)


def test_manifest_with_bad_size_is_refused(tmp_path: Path) -> None:
    fx.write_snapshot(tmp_path)
    manifest = json.loads((tmp_path / SNAPSHOT_FILE).read_text())
    manifest["files"]["rulings"]["size"] = "12"
    (tmp_path / SNAPSHOT_FILE).write_text(json.dumps(manifest))
    with pytest.raises(CardDataError, match="size"):
        load_snapshot_info(tmp_path)


def test_snapshot_date_is_utc(tmp_path: Path) -> None:
    """A file published late on the 18th in UTC-5 belongs to the 19th in UTC."""
    fx.write_snapshot(tmp_path)
    manifest = json.loads((tmp_path / SNAPSHOT_FILE).read_text())
    manifest["files"]["oracle_cards"]["updated_at"] = "2026-10-18T22:30:00-05:00"
    (tmp_path / SNAPSHOT_FILE).write_text(json.dumps(manifest))
    snapshot = load_snapshot_info(tmp_path)
    assert snapshot.date.isoformat() == "2026-10-19"
    assert snapshot.describe() == (
        "Snapshot 2026-10-19 (Oracle cards 2026-10-19, rulings 2026-10-18)"
    )


def test_snapshot_description_with_matching_dates(tmp_path: Path) -> None:
    fx.write_snapshot(tmp_path)
    assert load_snapshot_info(tmp_path).describe() == "Snapshot 2026-10-18"


def test_snapshot_info_round_trips_through_json(tmp_path: Path) -> None:
    fx.write_snapshot(tmp_path)
    snapshot = load_snapshot_info(tmp_path)
    (tmp_path / SNAPSHOT_FILE).write_text(json.dumps(snapshot.to_json()))
    assert load_snapshot_info(tmp_path) == snapshot
