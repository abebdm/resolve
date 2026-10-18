"""Card data loaded from the pinned Scryfall bulk snapshot (design.md §2, §11).

The snapshot lives in ``data/`` (gitignored) and is written by ``tools/fetch_scryfall.py``:

- ``oracle-cards.jsonl.gz``: Scryfall's "Oracle Cards" bulk file, one card object per Oracle ID.
- ``rulings.jsonl.gz``: Scryfall's "Rulings" bulk file.

Both are kept exactly as Scryfall serves them: gzip-compressed JSON Lines (one JSON object per
line).
- ``snapshot.json``: a manifest recording when each file was published and its SHA-256, so a
  changed or partial file is detected instead of silently changing what tests mean.

This module only describes printed card data (name, cost, types, Oracle text, ...). How a card
behaves in a game is a card definition in ``resolve.cards``; this data is the input to writing it.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

ORACLE_CARDS_FILE = "oracle-cards.jsonl.gz"
RULINGS_FILE = "rulings.jsonl.gz"
SNAPSHOT_FILE = "snapshot.json"
SNAPSHOT_FORMAT = 1

# Scryfall bulk-data types, as named by https://api.scryfall.com/bulk-data.
ORACLE_CARDS_TYPE = "oracle_cards"
RULINGS_TYPE = "rulings"

# Layouts that are not cards a deck can contain. Tokens, emblems and the like share names with
# each other (there are many different "Soldier" tokens), so they are kept out of the name index.
# "reversible_card" objects are two-sided printings of cards that also exist with their normal
# layout, and "front_card" objects are Jumpstart theme-card fronts (memorabilia); both share names
# with real cards, so indexing them would make those names ambiguous.
NON_DECK_LAYOUTS = frozenset(
    {
        "art_series",
        "double_faced_token",
        "emblem",
        "front_card",
        "planar",
        "reversible_card",
        "scheme",
        "token",
        "vanguard",
    }
)


class CardDataError(Exception):
    """The card data is missing, malformed, or doesn't contain what was asked for."""


class UnknownCardError(CardDataError, KeyError):
    """No card with this exact name exists in the snapshot."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name

    def __str__(self) -> str:
        return f"no card named {self.name!r} in the card data snapshot"


class AmbiguousCardNameError(CardDataError, KeyError):
    """More than one card in the snapshot has this name."""

    def __init__(self, name: str, oracle_ids: tuple[str, ...]) -> None:
        super().__init__(name)
        self.name = name
        self.oracle_ids = oracle_ids

    def __str__(self) -> str:
        return f"card name {self.name!r} is ambiguous (Oracle IDs {', '.join(self.oracle_ids)})"


@dataclass(frozen=True)
class CardFace:
    """One face of a card. Single-faced cards have exactly one face, named like the card."""

    name: str
    mana_cost: str
    type_line: str
    oracle_text: str
    colors: tuple[str, ...]
    power: str | None = None
    toughness: str | None = None
    loyalty: str | None = None
    defense: str | None = None


@dataclass(frozen=True)
class CardData:
    """Oracle data for one card (one Scryfall Oracle object).

    ``faces`` always has at least one entry, so code can read ``faces[0].oracle_text`` without
    special-casing single-faced cards. Power, toughness and the like stay strings because Oracle
    values such as ``"*"`` and ``"1+*"`` are not numbers.
    """

    oracle_id: str
    name: str
    layout: str
    type_line: str
    mana_value: float
    color_identity: tuple[str, ...]
    keywords: tuple[str, ...]
    faces: tuple[CardFace, ...]

    @property
    def is_multi_faced(self) -> bool:
        return len(self.faces) > 1

    @property
    def face_names(self) -> tuple[str, ...]:
        return tuple(face.name for face in self.faces)


@dataclass(frozen=True)
class Ruling:
    """An official ruling or Scryfall note attached to an Oracle card."""

    oracle_id: str
    source: str
    published_at: str
    comment: str


@dataclass(frozen=True)
class BulkFileInfo:
    """Where one bulk file came from, as recorded in ``snapshot.json``."""

    type: str
    file: str
    updated_at: str
    size: int
    sha256: str
    source: str

    @property
    def updated(self) -> datetime:
        return datetime.fromisoformat(self.updated_at).astimezone(UTC)

    def to_json(self) -> dict[str, object]:
        return {
            "type": self.type,
            "file": self.file,
            "updated_at": self.updated_at,
            "size": self.size,
            "sha256": self.sha256,
            "source": self.source,
        }


@dataclass(frozen=True)
class SnapshotInfo:
    """The manifest of a local card data snapshot."""

    oracle_cards: BulkFileInfo
    rulings: BulkFileInfo

    @property
    def date(self) -> date:
        """The snapshot's date: the UTC publication date of the Oracle cards file."""
        return self.oracle_cards.updated.date()

    def describe(self) -> str:
        """A one-line description for reports and ``docs/rules/README.md``."""
        oracle_date = self.oracle_cards.updated.date().isoformat()
        rulings_date = self.rulings.updated.date().isoformat()
        if oracle_date == rulings_date:
            return f"Snapshot {oracle_date}"
        return f"Snapshot {oracle_date} (Oracle cards {oracle_date}, rulings {rulings_date})"

    def to_json(self) -> dict[str, object]:
        return {
            "format": SNAPSHOT_FORMAT,
            "files": {
                ORACLE_CARDS_TYPE: self.oracle_cards.to_json(),
                RULINGS_TYPE: self.rulings.to_json(),
            },
        }


class CardDatabase:
    """All cards in a snapshot, looked up by exact name.

    Lookups are exact and case-sensitive: a decklist that misspells a card is refused rather than
    matched to something close. A multi-faced card can also be found by the name of its front face
    (for example a transforming card by its front face's name), because that is how decklists
    usually name them; the full Scryfall name (``"Front // Back"``) always works too.
    """

    def __init__(
        self,
        cards: Iterable[CardData],
        rulings: Iterable[Ruling] = (),
        snapshot: SnapshotInfo | None = None,
    ) -> None:
        self.snapshot = snapshot
        self._by_name: dict[str, CardData] = {}
        self._ambiguous: dict[str, list[str]] = {}
        self._by_oracle_id: dict[str, CardData] = {}

        deck_cards = [card for card in cards if card.layout not in NON_DECK_LAYOUTS]
        for card in deck_cards:
            self._by_oracle_id[card.oracle_id] = card
            self._add_name(card.name, card)
        # Front-face aliases come second, so a full card name always wins over an alias.
        for card in deck_cards:
            front = card.faces[0].name
            if card.is_multi_faced and front not in self._by_name and front not in self._ambiguous:
                self._by_name[front] = card

        rulings_by_id: dict[str, list[Ruling]] = {}
        for ruling in rulings:
            rulings_by_id.setdefault(ruling.oracle_id, []).append(ruling)
        # Stable sort: rulings published the same day keep Scryfall's order.
        self._rulings = {
            oracle_id: tuple(sorted(items, key=lambda r: r.published_at))
            for oracle_id, items in rulings_by_id.items()
        }

    def _add_name(self, name: str, card: CardData) -> None:
        if name in self._ambiguous:
            self._ambiguous[name].append(card.oracle_id)
        elif name in self._by_name:
            existing = self._by_name.pop(name)
            self._ambiguous[name] = [existing.oracle_id, card.oracle_id]
        else:
            self._by_name[name] = card

    def __len__(self) -> int:
        return len(self._by_oracle_id)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._by_name

    def get(self, name: str) -> CardData:
        """Return the card with exactly this name (or front-face name)."""
        if name in self._ambiguous:
            raise AmbiguousCardNameError(name, tuple(sorted(self._ambiguous[name])))
        try:
            return self._by_name[name]
        except KeyError:
            raise UnknownCardError(name) from None

    def rulings_for(self, card: CardData) -> tuple[Ruling, ...]:
        return self._rulings.get(card.oracle_id, ())


# --- Loading -----------------------------------------------------------------------------------


def default_data_dir() -> Path:
    """``data/`` at the root of the source checkout."""
    # src/resolve/data/cards.py -> parents[3] is the repository root.
    return Path(__file__).resolve().parents[3] / "data"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def load_snapshot_info(data_dir: Path) -> SnapshotInfo:
    path = data_dir / SNAPSHOT_FILE
    if not path.exists():
        raise CardDataError(
            f"no card data snapshot in {data_dir} ({SNAPSHOT_FILE} is missing); "
            "run `uv run python tools/fetch_scryfall.py` first"
        )
    raw = as_json_object(json.loads(path.read_text(encoding="utf-8")), SNAPSHOT_FILE)
    if raw.get("format") != SNAPSHOT_FORMAT:
        raise CardDataError(f"{path}: unsupported snapshot format {raw.get('format')!r}")
    files = as_json_object(raw.get("files"), f"{SNAPSHOT_FILE} files")
    return SnapshotInfo(
        oracle_cards=_parse_bulk_file_info(files, ORACLE_CARDS_TYPE),
        rulings=_parse_bulk_file_info(files, RULINGS_TYPE),
    )


def load_card_database(data_dir: Path | None = None, *, verify: bool = True) -> CardDatabase:
    """Load the snapshot in ``data_dir`` (default: the checkout's ``data/``).

    With ``verify`` (the default) each file's SHA-256 is checked against the manifest, so a file
    that was edited, truncated or swapped is refused.
    """
    data_dir = default_data_dir() if data_dir is None else data_dir
    snapshot = load_snapshot_info(data_dir)
    payloads: dict[str, object] = {}
    for info in (snapshot.oracle_cards, snapshot.rulings):
        path = data_dir / info.file
        if not path.exists():
            raise CardDataError(f"{path} is listed in {SNAPSHOT_FILE} but missing")
        if verify and sha256_of(path) != info.sha256:
            raise CardDataError(
                f"{path} does not match the SHA-256 recorded in {SNAPSHOT_FILE}; "
                "re-fetch the snapshot with tools/fetch_scryfall.py"
            )
        payloads[info.type] = read_jsonl_gz(path)
    return CardDatabase(
        cards=parse_oracle_cards(payloads[ORACLE_CARDS_TYPE]),
        rulings=parse_rulings(payloads[RULINGS_TYPE]),
        snapshot=snapshot,
    )


# --- Parsing Scryfall JSON ---------------------------------------------------------------------


def read_jsonl_gz(path: Path) -> list[object]:
    """Read a gzip-compressed JSON Lines file (Scryfall's bulk format) into a list of values."""
    items: list[object] = []
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    items.append(json.loads(line))
                except ValueError as error:
                    raise CardDataError(f"{path}:{number}: invalid JSON: {error}") from error
    except (OSError, EOFError) as error:
        # gzip.BadGzipFile is an OSError; a truncated file raises EOFError.
        raise CardDataError(f"{path}: not a readable gzip file: {error}") from error
    return items


def parse_oracle_cards(payload: object) -> list[CardData]:
    """Parse Scryfall's "Oracle Cards" bulk data (a list of card objects)."""
    return [parse_card(item) for item in as_json_list(payload, ORACLE_CARDS_FILE)]


def parse_rulings(payload: object) -> list[Ruling]:
    """Parse Scryfall's "Rulings" bulk data (a list of ruling objects)."""
    rulings: list[Ruling] = []
    for item in as_json_list(payload, RULINGS_FILE):
        raw = as_json_object(item, "ruling")
        rulings.append(
            Ruling(
                oracle_id=_str(raw, "oracle_id"),
                source=_str(raw, "source"),
                published_at=_str(raw, "published_at"),
                comment=_str(raw, "comment"),
            )
        )
    return rulings


def parse_card(item: object) -> CardData:
    raw = as_json_object(item, "card")
    name = _str(raw, "name")
    raw_faces = raw.get("card_faces")
    card_colors = _str_tuple(raw, "colors")
    if raw_faces is None:
        faces = (_parse_face(raw, card_colors),)
    else:
        faces = tuple(
            _parse_face(as_json_object(face, f"face of {name}"), card_colors)
            for face in as_json_list(raw_faces, f"card_faces of {name}")
        )
        if not faces:
            raise CardDataError(f"{name}: card_faces is empty")
    # Reversible cards carry their Oracle ID on each face instead of on the card.
    oracle_id = raw.get("oracle_id")
    if not isinstance(oracle_id, str) and raw_faces is not None:
        oracle_id = as_json_object(as_json_list(raw_faces, "card_faces")[0], "face").get(
            "oracle_id"
        )
    if not isinstance(oracle_id, str):
        raise CardDataError(f"{name}: missing oracle_id")
    mana_value = raw.get("cmc", 0)
    if not isinstance(mana_value, int | float) or isinstance(mana_value, bool):
        raise CardDataError(f"{name}: cmc is not a number")
    return CardData(
        oracle_id=oracle_id,
        name=name,
        layout=_str(raw, "layout"),
        type_line=_str(raw, "type_line", default=" // ".join(face.type_line for face in faces)),
        mana_value=float(mana_value),
        color_identity=_str_tuple(raw, "color_identity"),
        keywords=_str_tuple(raw, "keywords"),
        faces=faces,
    )


def _parse_face(raw: Mapping[str, object], card_colors: tuple[str, ...]) -> CardFace:
    # Faces of split and adventure cards have no "colors"; the card-level colors apply.
    colors = _str_tuple(raw, "colors") if "colors" in raw else card_colors
    return CardFace(
        name=_str(raw, "name"),
        mana_cost=_str(raw, "mana_cost", default=""),
        type_line=_str(raw, "type_line", default=""),
        oracle_text=_str(raw, "oracle_text", default=""),
        colors=colors,
        power=_opt_str(raw, "power"),
        toughness=_opt_str(raw, "toughness"),
        loyalty=_opt_str(raw, "loyalty"),
        defense=_opt_str(raw, "defense"),
    )


def _parse_bulk_file_info(files: Mapping[str, object], bulk_type: str) -> BulkFileInfo:
    raw = as_json_object(files.get(bulk_type), f"{SNAPSHOT_FILE} entry {bulk_type!r}")
    size = raw.get("size")
    if not isinstance(size, int) or isinstance(size, bool):
        raise CardDataError(f"{SNAPSHOT_FILE} entry {bulk_type!r}: size is not an integer")
    return BulkFileInfo(
        type=bulk_type,
        file=_str(raw, "file"),
        updated_at=_str(raw, "updated_at"),
        size=size,
        sha256=_str(raw, "sha256"),
        source=_str(raw, "source"),
    )


_MISSING = object()


def as_json_object(value: object, what: str) -> dict[str, object]:
    """``value`` as a JSON object (from ``json.load``), or a CardDataError naming ``what``."""
    if not isinstance(value, dict):
        raise CardDataError(f"{what}: expected a JSON object")
    return {str(key): item for key, item in cast(dict[object, object], value).items()}


def as_json_list(value: object, what: str) -> list[object]:
    """``value`` as a JSON list (from ``json.load``), or a CardDataError naming ``what``."""
    if not isinstance(value, list):
        raise CardDataError(f"{what}: expected a JSON list")
    return list(cast(list[object], value))


def _str(raw: Mapping[str, object], key: str, default: object = _MISSING) -> str:
    value = raw.get(key, default)
    if value is _MISSING:
        raise CardDataError(f"missing field {key!r} in {raw.get('name', 'object')!r}")
    if not isinstance(value, str):
        raise CardDataError(f"field {key!r} of {raw.get('name', 'object')!r} is not a string")
    return value


def _opt_str(raw: Mapping[str, object], key: str) -> str | None:
    return None if raw.get(key) is None else _str(raw, key)


def _str_tuple(raw: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = raw.get(key, [])
    items = as_json_list(value, f"field {key!r} of {raw.get('name', 'object')!r}")
    if not all(isinstance(item, str) for item in items):
        raise CardDataError(f"field {key!r} of {raw.get('name', 'object')!r} has non-strings")
    return tuple(str(item) for item in items)
