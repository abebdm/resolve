"""Download (or import) the Scryfall bulk data snapshot into ``data/`` and record its date.

Usage::

    uv run python tools/fetch_scryfall.py              # download the current snapshot
    uv run python tools/fetch_scryfall.py --update     # replace an existing snapshot
    uv run python tools/fetch_scryfall.py --import-files ORACLE.json RULINGS.json

``--import-files`` takes the "Oracle Cards" and "Rulings" files downloaded by hand from
https://scryfall.com/docs/api/bulk-data, for machines that can't reach Scryfall's API. Their
publication time is read from Scryfall's file names (``oracle-cards-YYYYMMDDHHMMSS.json``); for
renamed files, pass ``--updated-at`` with an ISO 8601 UTC time.

Either way the files are validated (they must parse as the right bulk type) before anything in
``data/`` is replaced, ``data/snapshot.json`` records their publication time and SHA-256, and the
snapshot date is written to ``docs/rules/README.md`` (design.md §2). The rules and card data are
updated together and deliberately, so an existing snapshot is only replaced with ``--update``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import urllib.request
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import BinaryIO

from resolve.data.cards import (
    ORACLE_CARDS_FILE,
    ORACLE_CARDS_TYPE,
    RULINGS_FILE,
    RULINGS_TYPE,
    SNAPSHOT_FILE,
    BulkFileInfo,
    CardDataError,
    SnapshotInfo,
    as_json_list,
    as_json_object,
    default_data_dir,
    parse_oracle_cards,
    parse_rulings,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
RULES_README = REPO_ROOT / "docs" / "rules" / "README.md"

BULK_DATA_URL = "https://api.scryfall.com/bulk-data"
# Scryfall asks API clients to send a descriptive User-Agent and an Accept header.
USER_AGENT = "resolve-rules-engine/0.0 (+https://github.com/abebdm/resolve)"
ACCEPT = "application/json;q=0.9,*/*;q=0.8"

FILE_NAMES = {ORACLE_CARDS_TYPE: ORACLE_CARDS_FILE, RULINGS_TYPE: RULINGS_FILE}
README_ROW_LABEL = "Scryfall Oracle cards + rulings"
SCRYFALL_FILE_NAME = re.compile(r"^(?P<kind>oracle-cards|rulings)-(?P<stamp>\d{14})\.json$")

Opener = Callable[[str], AbstractContextManager[BinaryIO]]


class FetchError(Exception):
    """The snapshot could not be fetched, imported or recorded."""


@dataclass(frozen=True)
class BulkEntry:
    """One entry of Scryfall's bulk-data index."""

    type: str
    updated_at: str
    download_uri: str


def open_url(url: str) -> AbstractContextManager[BinaryIO]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": ACCEPT})
    return urllib.request.urlopen(request, timeout=60)


def select_bulk_entries(index: object) -> dict[str, BulkEntry]:
    """Pick the Oracle-cards and rulings entries out of the bulk-data index JSON."""
    try:
        items = as_json_list(as_json_object(index, "bulk-data index").get("data"), "data")
        entries: dict[str, BulkEntry] = {}
        for item in items:
            raw = as_json_object(item, "bulk-data entry")
            bulk_type = raw.get("type")
            if not isinstance(bulk_type, str) or bulk_type not in FILE_NAMES:
                continue
            updated_at, uri = raw.get("updated_at"), raw.get("download_uri")
            if not isinstance(updated_at, str) or not isinstance(uri, str):
                raise FetchError(f"bulk-data entry {bulk_type!r} lacks updated_at/download_uri")
            entries[bulk_type] = BulkEntry(bulk_type, updated_at, uri)
    except CardDataError as error:
        raise FetchError(f"unexpected bulk-data index format: {error}") from error
    missing = [bulk_type for bulk_type in FILE_NAMES if bulk_type not in entries]
    if missing:
        raise FetchError(f"bulk-data index has no entry for {', '.join(missing)}")
    return entries


def download(opener: Opener, url: str, destination: Path) -> None:
    with opener(url) as response, destination.open("wb") as handle:
        shutil.copyfileobj(response, handle, length=1 << 20)


def validate_bulk_file(bulk_type: str, path: Path) -> None:
    """Refuse a file that isn't the bulk type it claims to be.

    Catches truncated downloads and mixed-up files: Scryfall's other card bulk files ("Default
    Cards" and so on) parse as cards too, but list each Oracle card many times.
    """
    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        if bulk_type == ORACLE_CARDS_TYPE:
            cards = parse_oracle_cards(payload)
            if not cards:
                raise FetchError(f"{path}: contains no cards")
            oracle_ids = [card.oracle_id for card in cards]
            if len(set(oracle_ids)) != len(oracle_ids):
                raise FetchError(
                    f"{path}: lists some Oracle IDs more than once, so it is not the "
                    "'Oracle Cards' bulk file"
                )
        else:
            if not parse_rulings(payload):
                raise FetchError(f"{path}: contains no rulings")
    except (CardDataError, ValueError) as error:
        raise FetchError(f"{path} is not a valid {bulk_type} bulk file: {error}") from error


def sha256_and_size(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def install_snapshot(data_dir: Path, staged: dict[str, tuple[Path, str, str]]) -> SnapshotInfo:
    """Validate staged files, move them into ``data_dir`` and write the manifest.

    ``staged`` maps bulk type to (staged path, updated_at, source). Nothing in ``data_dir`` is
    replaced unless every file validates; the manifest is written last.
    """
    infos: dict[str, BulkFileInfo] = {}
    for bulk_type, (path, updated_at, source) in staged.items():
        validate_bulk_file(bulk_type, path)
        sha256, size = sha256_and_size(path)
        infos[bulk_type] = BulkFileInfo(
            type=bulk_type,
            file=FILE_NAMES[bulk_type],
            updated_at=updated_at,
            size=size,
            sha256=sha256,
            source=source,
        )
    snapshot = SnapshotInfo(oracle_cards=infos[ORACLE_CARDS_TYPE], rulings=infos[RULINGS_TYPE])
    for bulk_type, (path, _, _) in staged.items():
        os.replace(path, data_dir / FILE_NAMES[bulk_type])
    manifest = json.dumps(snapshot.to_json(), indent=2) + "\n"
    (data_dir / SNAPSHOT_FILE).write_text(manifest, encoding="utf-8")
    return snapshot


def fetch_snapshot(data_dir: Path, opener: Opener = open_url) -> SnapshotInfo:
    """Download the current Oracle-cards and rulings files from Scryfall into ``data_dir``."""
    with opener(BULK_DATA_URL) as response:
        entries = select_bulk_entries(json.load(response))
    staged: dict[str, tuple[Path, str, str]] = {}
    try:
        for bulk_type, entry in entries.items():
            part = data_dir / f"{FILE_NAMES[bulk_type]}.part"
            staged[bulk_type] = (part, entry.updated_at, entry.download_uri)
            print(f"Downloading {entry.download_uri} ...", file=sys.stderr)
            download(opener, entry.download_uri, part)
        return install_snapshot(data_dir, staged)
    finally:
        for part, _, _ in staged.values():
            part.unlink(missing_ok=True)


def updated_at_from_file_name(path: Path, expected_kind: str) -> str:
    """Read the publication time from a Scryfall bulk file name, as an ISO 8601 UTC time."""
    match = SCRYFALL_FILE_NAME.match(path.name)
    if match is None:
        raise FetchError(
            f"can't read a publication time from {path.name!r} (expected "
            f"'{expected_kind}-YYYYMMDDHHMMSS.json'); pass --updated-at"
        )
    if match["kind"] != expected_kind:
        raise FetchError(f"{path.name!r} looks like a {match['kind']} file, not {expected_kind}")
    stamp = datetime.strptime(match["stamp"], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    return stamp.isoformat()


def import_snapshot(
    data_dir: Path,
    oracle_cards: Path,
    rulings: Path,
    updated_at: str | None = None,
) -> SnapshotInfo:
    """Install bulk files that were downloaded by hand."""
    if updated_at is not None:
        try:
            parsed = datetime.fromisoformat(updated_at)
        except ValueError as error:
            raise FetchError(f"--updated-at: {error}") from error
        if parsed.tzinfo is None:
            raise FetchError("--updated-at needs a time zone, for example 2026-10-18T09:00:00Z")
    sources = {
        ORACLE_CARDS_TYPE: (oracle_cards, "oracle-cards"),
        RULINGS_TYPE: (rulings, "rulings"),
    }
    staged: dict[str, tuple[Path, str, str]] = {}
    try:
        for bulk_type, (source, kind) in sources.items():
            if not source.is_file():
                raise FetchError(f"{source} does not exist")
            stamp = updated_at or updated_at_from_file_name(source, kind)
            part = data_dir / f"{FILE_NAMES[bulk_type]}.part"
            staged[bulk_type] = (part, stamp, f"manual import of {source.name}")
            shutil.copyfile(source, part)
        return install_snapshot(data_dir, staged)
    finally:
        for part, _, _ in staged.values():
            part.unlink(missing_ok=True)


def update_rules_readme(text: str, snapshot: SnapshotInfo, today: date) -> str:
    """Record the snapshot in ``docs/rules/README.md``: the version table and the changelog."""
    lines = text.splitlines()
    row_prefix = f"| {README_ROW_LABEL} |"
    rows = [i for i, line in enumerate(lines) if line.startswith(row_prefix)]
    if len(rows) != 1:
        raise FetchError(f"expected one '{README_ROW_LABEL}' row in the rules README")
    cells = lines[rows[0]].split("|")
    # cells: ['', ' label ', ' version ', ' location ', '']
    if len(cells) != 5:
        raise FetchError(f"unexpected format of the '{README_ROW_LABEL}' row")
    cells[2] = f" {snapshot.describe()} "
    lines[rows[0]] = "|".join(cells)

    try:
        changelog = lines.index("## Changelog")
    except ValueError:
        raise FetchError("no '## Changelog' section in the rules README") from None
    last_row = changelog
    for i in range(changelog + 1, len(lines)):
        if lines[i].startswith("|"):
            last_row = i
        elif last_row != changelog and lines[i].strip():
            break
    if last_row == changelog:
        raise FetchError("no changelog table in the rules README")
    entry = (
        f"| {today.isoformat()} | Pinned the Scryfall Oracle cards and rulings bulk data: "
        f"{snapshot.describe()}. |"
    )
    lines.insert(last_row + 1, entry)
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--data-dir", type=Path, default=default_data_dir())
    parser.add_argument("--rules-readme", type=Path, default=RULES_README)
    parser.add_argument(
        "--update", action="store_true", help="replace an existing snapshot in the data directory"
    )
    parser.add_argument(
        "--import-files",
        nargs=2,
        type=Path,
        metavar=("ORACLE_CARDS", "RULINGS"),
        help="install bulk files downloaded by hand instead of downloading them",
    )
    parser.add_argument(
        "--updated-at", help="publication time of imported files (ISO 8601, with time zone)"
    )
    args = parser.parse_args(argv)
    data_dir: Path = args.data_dir

    if args.updated_at is not None and args.import_files is None:
        parser.error("--updated-at only applies with --import-files")
    if (data_dir / SNAPSHOT_FILE).exists() and not args.update:
        print(
            f"{data_dir / SNAPSHOT_FILE} already exists. The card data is pinned; pass --update "
            "to replace it deliberately.",
            file=sys.stderr,
        )
        return 1

    data_dir.mkdir(parents=True, exist_ok=True)
    try:
        if args.import_files is not None:
            oracle_cards, rulings = args.import_files
            snapshot = import_snapshot(data_dir, oracle_cards, rulings, args.updated_at)
        else:
            snapshot = fetch_snapshot(data_dir)
        readme: Path = args.rules_readme
        readme.write_text(
            update_rules_readme(readme.read_text(encoding="utf-8"), snapshot, date.today()),
            encoding="utf-8",
        )
    except (FetchError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"Installed {snapshot.describe()} in {data_dir}; recorded it in {readme}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
