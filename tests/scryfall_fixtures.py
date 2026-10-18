"""Small hand-written card data in Scryfall's bulk-data JSON format, for tests.

The real snapshot is large, gitignored and not available in CI, so loader and tool tests use these
records instead. They follow Scryfall's field names and structure; the cards whose names start
with "Test" are invented to exercise edge cases. Rulings here are placeholders, not real rulings.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

from resolve.data.cards import (
    ORACLE_CARDS_FILE,
    ORACLE_CARDS_TYPE,
    RULINGS_FILE,
    RULINGS_TYPE,
    SNAPSHOT_FILE,
    SNAPSHOT_FORMAT,
)

ORACLE_UPDATED_AT = "2026-10-18T09:02:11.4+00:00"
RULINGS_UPDATED_AT = "2026-10-18T09:00:34.1+00:00"

LLANOWAR_ELVES: dict[str, Any] = {
    "object": "card",
    "oracle_id": "oid-llanowar-elves",
    "name": "Llanowar Elves",
    "layout": "normal",
    "mana_cost": "{G}",
    "cmc": 1.0,
    "type_line": "Creature — Elf Druid",
    "oracle_text": "{T}: Add {G}.",
    "power": "1",
    "toughness": "1",
    "colors": ["G"],
    "color_identity": ["G"],
    "keywords": [],
}

FOREST: dict[str, Any] = {
    "object": "card",
    "oracle_id": "oid-forest",
    "name": "Forest",
    "layout": "normal",
    "mana_cost": "",
    "cmc": 0.0,
    "type_line": "Basic Land — Forest",
    "oracle_text": "({T}: Add {G}.)",
    "colors": [],
    "color_identity": ["G"],
    "keywords": [],
}


def basic_land(name: str, color: str) -> dict[str, Any]:
    """A basic land's record, like ``FOREST`` (Scryfall gives the reminder text as Oracle text)."""
    return {
        "object": "card",
        "oracle_id": f"oid-{name.lower()}",
        "name": name,
        "layout": "normal",
        "mana_cost": "",
        "cmc": 0.0,
        "type_line": f"Basic Land — {name}",
        "oracle_text": f"({{T}}: Add {{{color}}}.)",
        "colors": [],
        "color_identity": [color],
        "keywords": [],
    }


PLAINS = basic_land("Plains", "W")
ISLAND = basic_land("Island", "U")
SWAMP = basic_land("Swamp", "B")
MOUNTAIN = basic_land("Mountain", "R")

# An invented nonbasic land with a basic land type and no text (305.6, 305.8).
NONBASIC_FOREST: dict[str, Any] = {
    "object": "card",
    "oracle_id": "oid-test-nonbasic-forest",
    "name": "Test Nonbasic Forest",
    "layout": "normal",
    "mana_cost": "",
    "cmc": 0.0,
    "type_line": "Land — Forest",
    "oracle_text": "",
    "colors": [],
    "color_identity": ["G"],
    "keywords": [],
}

# An invented land that is also a creature (305.9) and a land with two basic land types (305.6).
LAND_CREATURE: dict[str, Any] = {
    **NONBASIC_FOREST,
    "oracle_id": "oid-test-land-creature",
    "name": "Test Land Creature",
    "type_line": "Land Creature — Forest Dryad",
    "power": "1",
    "toughness": "1",
}
DUAL_LAND: dict[str, Any] = {
    **NONBASIC_FOREST,
    "oracle_id": "oid-test-dual",
    "name": "Test Dual",
    "type_line": "Land — Forest Island",
    "color_identity": ["G", "U"],
}


def vanilla(
    name: str, cost: str, cmc: float, subtype: str, pt: tuple[str, str], color: str
) -> dict[str, Any]:
    """A creature with no rules text."""
    return {
        "object": "card",
        "oracle_id": "oid-" + name.lower().replace(" ", "-"),
        "name": name,
        "layout": "normal",
        "mana_cost": cost,
        "cmc": cmc,
        "type_line": f"Creature — {subtype}",
        "oracle_text": "",
        "power": pt[0],
        "toughness": pt[1],
        "colors": [color],
        "color_identity": [color],
        "keywords": [],
    }


# Real vanilla creatures (Oracle text empty), and invented ones for 704.5f and 208.2.
GRIZZLY_BEARS = vanilla("Grizzly Bears", "{1}{G}", 2.0, "Bear", ("2", "2"), "G")
SAVANNAH_LIONS = vanilla("Savannah Lions", "{W}", 1.0, "Cat", ("2", "1"), "W")
HILL_GIANT = vanilla("Hill Giant", "{3}{R}", 4.0, "Giant", ("3", "3"), "R")
ZERO_TOUGHNESS = vanilla("Test Wisp", "{G}", 1.0, "Spirit", ("1", "0"), "G")
STAR_CREATURE = vanilla("Test Star", "{1}{G}", 2.0, "Elemental", ("*", "*"), "G")

# A transforming double-faced card: colors live on the faces, not on the card.
TRANSFORM_CARD: dict[str, Any] = {
    "object": "card",
    "oracle_id": "oid-test-transform",
    "name": "Test Daybreaker // Test Nightfall",
    "layout": "transform",
    "cmc": 2.0,
    "type_line": "Creature — Human // Creature — Werewolf",
    "color_identity": ["G"],
    "keywords": ["Trample", "Transform"],
    "card_faces": [
        {
            "object": "card_face",
            "name": "Test Daybreaker",
            "mana_cost": "{1}{G}",
            "type_line": "Creature — Human",
            "oracle_text": "At the beginning of each upkeep, transform this creature.",
            "colors": ["G"],
            "power": "2",
            "toughness": "2",
        },
        {
            "object": "card_face",
            "name": "Test Nightfall",
            "mana_cost": "",
            "type_line": "Creature — Werewolf",
            "oracle_text": "Trample",
            "colors": ["G"],
            "power": "4",
            "toughness": "4",
        },
    ],
}

# A split card: the faces have no "colors"; the card's colors apply.
SPLIT_CARD: dict[str, Any] = {
    "object": "card",
    "oracle_id": "oid-test-split",
    "name": "Test Spark // Test Frost",
    "layout": "split",
    "mana_cost": "{1}{R} // {1}{U}",
    "cmc": 4.0,
    "type_line": "Instant // Instant",
    "colors": ["R", "U"],
    "color_identity": ["R", "U"],
    "keywords": [],
    "card_faces": [
        {
            "object": "card_face",
            "name": "Test Spark",
            "mana_cost": "{1}{R}",
            "type_line": "Instant",
            "oracle_text": "Test Spark deals 2 damage divided as you choose among one or two "
            "targets.",
        },
        {
            "object": "card_face",
            "name": "Test Frost",
            "mana_cost": "{1}{U}",
            "type_line": "Instant",
            "oracle_text": "Tap target permanent.\nDraw a card.",
        },
    ],
}


# Invented one-mana spells, for the timing rules of instants and sorceries (117.1a).
INSTANT_CARD: dict[str, Any] = {
    "object": "card",
    "oracle_id": "oid-test-shock",
    "name": "Test Shock",
    "layout": "normal",
    "mana_cost": "{R}",
    "cmc": 1.0,
    "type_line": "Instant",
    "oracle_text": "Test Shock deals 2 damage to any target.",
    "colors": ["R"],
    "color_identity": ["R"],
    "keywords": [],
}

SORCERY_CARD: dict[str, Any] = {
    "object": "card",
    "oracle_id": "oid-test-ponder",
    "name": "Test Ponder",
    "layout": "normal",
    "mana_cost": "{U}",
    "cmc": 1.0,
    "type_line": "Sorcery",
    "oracle_text": "Draw a card.",
    "colors": ["U"],
    "color_identity": ["U"],
    "keywords": [],
}


def token(oracle_id: str, name: str = "Soldier") -> dict[str, Any]:
    """A token object (layout ``token``), which the name index must ignore."""
    return {
        "object": "card",
        "oracle_id": oracle_id,
        "name": name,
        "layout": "token",
        "cmc": 0.0,
        "type_line": "Token Creature — Soldier",
        "oracle_text": "",
        "power": "1",
        "toughness": "1",
        "colors": ["W"],
        "color_identity": ["W"],
        "keywords": [],
    }


def simple_card(name: str, oracle_id: str, **overrides: Any) -> dict[str, Any]:
    """A plain single-faced artifact; ``overrides`` replace or add Scryfall fields."""
    card: dict[str, Any] = {
        "object": "card",
        "oracle_id": oracle_id,
        "name": name,
        "layout": "normal",
        "mana_cost": "{1}",
        "cmc": 1.0,
        "type_line": "Artifact",
        "oracle_text": "",
        "colors": [],
        "color_identity": [],
        "keywords": [],
    }
    card.update(overrides)
    return card


def ruling(oracle_id: str, published_at: str, comment: str) -> dict[str, Any]:
    """A ruling object from Wizards (source ``wotc``)."""
    return {
        "object": "ruling",
        "oracle_id": oracle_id,
        "source": "wotc",
        "published_at": published_at,
        "comment": comment,
    }


def default_cards() -> list[dict[str, Any]]:
    """The standard fixture cards: four deck cards (normal, land, transform, split) and a token."""
    return [LLANOWAR_ELVES, FOREST, TRANSFORM_CARD, SPLIT_CARD, token("oid-soldier-1")]


def default_rulings() -> list[dict[str, Any]]:
    """Placeholder rulings: two for Llanowar Elves (out of date order) and one for the DFC."""
    return [
        ruling("oid-llanowar-elves", "2020-06-01", "Placeholder ruling B."),
        ruling("oid-llanowar-elves", "2019-01-01", "Placeholder ruling A."),
        ruling("oid-test-transform", "2021-09-24", "Placeholder ruling C."),
    ]


def jsonl_gz(items: list[dict[str, Any]]) -> bytes:
    """Items in Scryfall's bulk format: gzip-compressed JSON Lines (mtime 0, so reproducible)."""
    text = "".join(json.dumps(item) + "\n" for item in items)
    return gzip.compress(text.encode(), mtime=0)


def oracle_cards_bytes(cards: list[dict[str, Any]] | None = None) -> bytes:
    """An Oracle-cards bulk file's bytes (default: ``default_cards()``)."""
    return jsonl_gz(default_cards() if cards is None else cards)


def rulings_bytes(rulings: list[dict[str, Any]] | None = None) -> bytes:
    """A rulings bulk file's bytes (default: ``default_rulings()``)."""
    return jsonl_gz(default_rulings() if rulings is None else rulings)


def write_snapshot(
    data_dir: Path,
    cards: list[dict[str, Any]] | None = None,
    rulings: list[dict[str, Any]] | None = None,
) -> None:
    """Write a complete snapshot (both bulk files and a matching manifest) to ``data_dir``."""
    data_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, object] = {}
    for bulk_type, file_name, payload, updated_at in (
        (ORACLE_CARDS_TYPE, ORACLE_CARDS_FILE, oracle_cards_bytes(cards), ORACLE_UPDATED_AT),
        (RULINGS_TYPE, RULINGS_FILE, rulings_bytes(rulings), RULINGS_UPDATED_AT),
    ):
        (data_dir / file_name).write_bytes(payload)
        files[bulk_type] = {
            "type": bulk_type,
            "file": file_name,
            "updated_at": updated_at,
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "source": f"https://data.scryfall.io/{file_name}",
        }
    manifest = {"format": SNAPSHOT_FORMAT, "files": files}
    (data_dir / SNAPSHOT_FILE).write_text(json.dumps(manifest), encoding="utf-8")
