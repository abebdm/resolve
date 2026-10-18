"""Small hand-written card data in Scryfall's bulk-data JSON format, for tests.

The real snapshot is large, gitignored and not available in CI, so loader and tool tests use these
records instead. They follow Scryfall's field names and structure; the cards whose names start
with "Test" are invented to exercise edge cases. Rulings here are placeholders, not real rulings.
"""

from __future__ import annotations

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


def token(oracle_id: str, name: str = "Soldier") -> dict[str, Any]:
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
    return {
        "object": "ruling",
        "oracle_id": oracle_id,
        "source": "wotc",
        "published_at": published_at,
        "comment": comment,
    }


def default_cards() -> list[dict[str, Any]]:
    return [LLANOWAR_ELVES, FOREST, TRANSFORM_CARD, SPLIT_CARD, token("oid-soldier-1")]


def default_rulings() -> list[dict[str, Any]]:
    return [
        ruling("oid-llanowar-elves", "2020-06-01", "Placeholder ruling B."),
        ruling("oid-llanowar-elves", "2019-01-01", "Placeholder ruling A."),
        ruling("oid-test-transform", "2021-09-24", "Placeholder ruling C."),
    ]


def oracle_cards_bytes(cards: list[dict[str, Any]] | None = None) -> bytes:
    return json.dumps(default_cards() if cards is None else cards).encode()


def rulings_bytes(rulings: list[dict[str, Any]] | None = None) -> bytes:
    return json.dumps(default_rulings() if rulings is None else rulings).encode()


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
