"""Tests for tools/fetch_scryfall.py. No network: Scryfall is replaced by a fake opener."""

from __future__ import annotations

import io
import json
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, BinaryIO

import pytest

from resolve.data.cards import (
    ORACLE_CARDS_FILE,
    RULINGS_FILE,
    SNAPSHOT_FILE,
    load_card_database,
    load_snapshot_info,
)
from tests import scryfall_fixtures as fx
from tools import fetch_scryfall
from tools.fetch_scryfall import (
    BULK_DATA_URL,
    FetchError,
    fetch_snapshot,
    import_snapshot,
    select_bulk_entries,
    update_rules_readme,
    updated_at_from_file_name,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ORACLE_URI = "https://data.scryfall.io/oracle-cards/oracle-cards-20261018090211.json"
RULINGS_URI = "https://data.scryfall.io/rulings/rulings-20261018090034.json"


def bulk_index(**overrides: Any) -> dict[str, Any]:
    entries: list[dict[str, Any]] = [
        {
            "object": "bulk_data",
            "type": "oracle_cards",
            "updated_at": fx.ORACLE_UPDATED_AT,
            "download_uri": ORACLE_URI,
        },
        {
            "object": "bulk_data",
            "type": "unique_artwork",
            "updated_at": fx.ORACLE_UPDATED_AT,
            "download_uri": "https://data.scryfall.io/unique-artwork.json",
        },
        {
            "object": "bulk_data",
            "type": "rulings",
            "updated_at": fx.RULINGS_UPDATED_AT,
            "download_uri": RULINGS_URI,
        },
    ]
    return {"object": "list", "has_more": False, "data": entries, **overrides}


class FakeScryfall:
    """Serves URLs from a dict and records which were requested."""

    def __init__(self, responses: dict[str, bytes]) -> None:
        self.responses = responses
        self.requested: list[str] = []

    @contextmanager
    def __call__(self, url: str) -> Generator[BinaryIO]:
        self.requested.append(url)
        yield io.BytesIO(self.responses[url])


def fake_scryfall(
    oracle: bytes | None = None, rulings: bytes | None = None, index: object = None
) -> FakeScryfall:
    return FakeScryfall(
        {
            BULK_DATA_URL: json.dumps(bulk_index() if index is None else index).encode(),
            ORACLE_URI: fx.oracle_cards_bytes() if oracle is None else oracle,
            RULINGS_URI: fx.rulings_bytes() if rulings is None else rulings,
        }
    )


# --- The bulk-data index -------------------------------------------------------------------------


def test_selects_oracle_cards_and_rulings_entries() -> None:
    entries = select_bulk_entries(bulk_index())
    assert set(entries) == {"oracle_cards", "rulings"}
    assert entries["oracle_cards"].download_uri == ORACLE_URI
    assert entries["rulings"].updated_at == fx.RULINGS_UPDATED_AT


def test_index_without_rulings_is_refused() -> None:
    index = bulk_index()
    index["data"] = [e for e in index["data"] if e["type"] != "rulings"]
    with pytest.raises(FetchError, match="no entry for rulings"):
        select_bulk_entries(index)


@pytest.mark.parametrize("index", [[], {"data": "x"}, {"data": [1]}, {}])
def test_malformed_index_is_refused(index: object) -> None:
    with pytest.raises(FetchError, match="unexpected bulk-data index format"):
        select_bulk_entries(index)


def test_entry_without_download_uri_is_refused() -> None:
    index = bulk_index()
    del index["data"][0]["download_uri"]
    with pytest.raises(FetchError, match="lacks updated_at/download_uri"):
        select_bulk_entries(index)


# --- Downloading ---------------------------------------------------------------------------------


def test_fetch_downloads_validates_and_records_snapshot(tmp_path: Path) -> None:
    scryfall = fake_scryfall()
    snapshot = fetch_snapshot(tmp_path, scryfall)

    assert scryfall.requested == [BULK_DATA_URL, ORACLE_URI, RULINGS_URI]
    assert (tmp_path / ORACLE_CARDS_FILE).read_bytes() == fx.oracle_cards_bytes()
    assert (tmp_path / RULINGS_FILE).read_bytes() == fx.rulings_bytes()
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
        [ORACLE_CARDS_FILE, RULINGS_FILE, SNAPSHOT_FILE]
    ), "no partial files are left behind"

    assert snapshot == load_snapshot_info(tmp_path)
    assert snapshot.oracle_cards.source == ORACLE_URI
    assert snapshot.oracle_cards.size == len(fx.oracle_cards_bytes())
    assert snapshot.date == date(2026, 10, 18)
    assert "Llanowar Elves" in load_card_database(tmp_path)


@pytest.mark.parametrize(
    ("oracle", "rulings", "message"),
    [
        (b"not json", None, "not a valid oracle_cards bulk file"),
        (b"[]", None, "contains no cards"),
        (fx.oracle_cards_bytes([fx.FOREST, fx.FOREST]), None, "more than once"),
        (fx.rulings_bytes(), None, "not a valid oracle_cards bulk file"),
        (None, b"[]", "contains no rulings"),
        (None, fx.oracle_cards_bytes(), "not a valid rulings bulk file"),
    ],
)
def test_invalid_download_leaves_existing_snapshot_untouched(
    tmp_path: Path, oracle: bytes | None, rulings: bytes | None, message: str
) -> None:
    fx.write_snapshot(tmp_path, cards=[fx.FOREST])
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    with pytest.raises(FetchError, match=message):
        fetch_snapshot(tmp_path, fake_scryfall(oracle, rulings))
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


# --- Importing hand-downloaded files --------------------------------------------------------------


def write_downloads(directory: Path) -> tuple[Path, Path]:
    directory.mkdir()
    oracle = directory / "oracle-cards-20261018090211.json"
    rulings = directory / "rulings-20261018090034.json"
    oracle.write_bytes(fx.oracle_cards_bytes())
    rulings.write_bytes(fx.rulings_bytes())
    return oracle, rulings


def test_import_reads_publication_time_from_scryfall_file_names(tmp_path: Path) -> None:
    oracle, rulings = write_downloads(tmp_path / "downloads")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    snapshot = import_snapshot(data_dir, oracle, rulings)

    assert snapshot.oracle_cards.updated_at == "2026-10-18T09:02:11+00:00"
    assert snapshot.rulings.updated_at == "2026-10-18T09:00:34+00:00"
    assert snapshot.oracle_cards.source == f"manual import of {oracle.name}"
    assert oracle.exists() and rulings.exists(), "the downloaded files are copied, not moved"
    assert len(load_card_database(data_dir)) == 4


def test_import_with_explicit_publication_time(tmp_path: Path) -> None:
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    (downloads / "cards.json").write_bytes(fx.oracle_cards_bytes())
    (downloads / "rules.json").write_bytes(fx.rulings_bytes())
    snapshot = import_snapshot(
        tmp_path, downloads / "cards.json", downloads / "rules.json", "2026-10-17T08:00:00Z"
    )
    assert snapshot.date == date(2026, 10, 17)


def test_import_of_renamed_files_needs_publication_time(tmp_path: Path) -> None:
    (tmp_path / "cards.json").write_bytes(fx.oracle_cards_bytes())
    (tmp_path / "rules.json").write_bytes(fx.rulings_bytes())
    with pytest.raises(FetchError, match="pass --updated-at"):
        import_snapshot(tmp_path, tmp_path / "cards.json", tmp_path / "rules.json")


def test_import_with_files_swapped_is_refused(tmp_path: Path) -> None:
    oracle, rulings = write_downloads(tmp_path / "downloads")
    with pytest.raises(FetchError, match="looks like a rulings file"):
        import_snapshot(tmp_path, rulings, oracle)


def test_import_of_missing_file_is_refused(tmp_path: Path) -> None:
    oracle, _ = write_downloads(tmp_path / "downloads")
    with pytest.raises(FetchError, match="does not exist"):
        import_snapshot(tmp_path, oracle, tmp_path / "rulings-20261018090034.json")
    assert not (tmp_path / SNAPSHOT_FILE).exists()
    assert not list(tmp_path.glob("*.part"))


@pytest.mark.parametrize(
    ("updated_at", "message"),
    [("2026-10-18T09:00:00", "needs a time zone"), ("yesterday", "--updated-at")],
)
def test_import_rejects_bad_publication_time(tmp_path: Path, updated_at: str, message: str) -> None:
    oracle, rulings = write_downloads(tmp_path / "downloads")
    with pytest.raises(FetchError, match=message):
        import_snapshot(tmp_path, oracle, rulings, updated_at)


@pytest.mark.parametrize(
    ("name", "kind", "expected"),
    [
        ("oracle-cards-20261018090211.json", "oracle-cards", "2026-10-18T09:02:11+00:00"),
        ("rulings-20260101000000.json", "rulings", "2026-01-01T00:00:00+00:00"),
    ],
)
def test_publication_time_from_file_name(name: str, kind: str, expected: str) -> None:
    assert updated_at_from_file_name(Path(name), kind) == expected


def test_default_cards_file_name_is_not_accepted_as_oracle_cards() -> None:
    with pytest.raises(FetchError, match="pass --updated-at"):
        updated_at_from_file_name(Path("default-cards-20261018090211.json"), "oracle-cards")


# --- Recording the snapshot in docs/rules/README.md -----------------------------------------------


def snapshot_for_readme(tmp_path: Path) -> Any:
    fx.write_snapshot(tmp_path)
    return load_snapshot_info(tmp_path)


def test_rules_readme_records_snapshot_and_changelog_entry(tmp_path: Path) -> None:
    text = (REPO_ROOT / "docs" / "rules" / "README.md").read_text(encoding="utf-8")
    updated = update_rules_readme(text, snapshot_for_readme(tmp_path), date(2026, 10, 18))

    row = next(line for line in updated.splitlines() if line.startswith("| Scryfall"))
    assert row.split("|")[2].strip() == "Snapshot 2026-10-18"
    assert (
        row.split("|")[3]
        == text.splitlines()[
            next(i for i, line in enumerate(text.splitlines()) if line.startswith("| Scryfall"))
        ].split("|")[3]
    ), "the location column is unchanged"

    changelog = updated.split("## Changelog", 1)[1].strip().splitlines()
    assert changelog[-1] == (
        "| 2026-10-18 | Pinned the Scryfall Oracle cards and rulings bulk data: "
        "Snapshot 2026-10-18. |"
    )
    assert len(changelog) == len(text.split("## Changelog", 1)[1].strip().splitlines()) + 1


def test_changelog_entry_goes_after_the_last_row_even_with_text_below(tmp_path: Path) -> None:
    text = (
        "| Scryfall Oracle cards + rulings | x | `data/` |\n\n## Changelog\n\n"
        "| Date | Change |\n|---|---|\n| 2026-10-17 | First. |\n\nTrailing paragraph.\n"
    )
    lines = update_rules_readme(text, snapshot_for_readme(tmp_path), date(2026, 10, 19)).split("\n")
    entry = lines.index("| 2026-10-17 | First. |") + 1
    assert lines[entry].startswith("| 2026-10-19 | Pinned")
    assert lines[entry + 2] == "Trailing paragraph."


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("## Changelog\n| a | b |\n", "one 'Scryfall Oracle cards \\+ rulings' row"),
        ("| Scryfall Oracle cards + rulings | x |\n", "unexpected format"),
        ("| Scryfall Oracle cards + rulings | x | y |\n", "no '## Changelog' section"),
        ("| Scryfall Oracle cards + rulings | x | y |\n## Changelog\n\nnone\n", "no changelog"),
    ],
)
def test_unexpected_rules_readme_is_refused(tmp_path: Path, text: str, message: str) -> None:
    with pytest.raises(FetchError, match=message):
        update_rules_readme(text, snapshot_for_readme(tmp_path), date(2026, 10, 18))


# --- The command line -----------------------------------------------------------------------------


def readme_copy(tmp_path: Path) -> Path:
    readme = tmp_path / "README.md"
    readme.write_text((REPO_ROOT / "docs" / "rules" / "README.md").read_text(encoding="utf-8"))
    return readme


def test_cli_import_installs_and_records(tmp_path: Path) -> None:
    oracle, rulings = write_downloads(tmp_path / "downloads")
    readme = readme_copy(tmp_path)
    data_dir = tmp_path / "data"
    args = ["--data-dir", str(data_dir), "--rules-readme", str(readme)]
    assert fetch_scryfall.main([*args, "--import-files", str(oracle), str(rulings)]) == 0
    assert (data_dir / SNAPSHOT_FILE).exists()
    assert "Snapshot 2026-10-18" in readme.read_text()


def test_cli_refuses_to_replace_a_pinned_snapshot_without_update(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    oracle, rulings = write_downloads(tmp_path / "downloads")
    data_dir = tmp_path / "data"
    fx.write_snapshot(data_dir, cards=[fx.FOREST])
    readme = readme_copy(tmp_path)
    before = (data_dir / SNAPSHOT_FILE).read_text()
    args = ["--data-dir", str(data_dir), "--rules-readme", str(readme)]

    assert fetch_scryfall.main([*args, "--import-files", str(oracle), str(rulings)]) == 1
    assert "--update" in capsys.readouterr().err
    assert (data_dir / SNAPSHOT_FILE).read_text() == before

    assert (
        fetch_scryfall.main([*args, "--update", "--import-files", str(oracle), str(rulings)]) == 0
    )
    assert (data_dir / SNAPSHOT_FILE).read_text() != before


def test_cli_reports_errors_without_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    readme = readme_copy(tmp_path)
    args = ["--data-dir", str(tmp_path / "data"), "--rules-readme", str(readme)]
    missing = str(tmp_path / "nope.json")
    assert fetch_scryfall.main([*args, "--import-files", missing, missing]) == 1
    assert capsys.readouterr().err.startswith("error: ")


def test_cli_updated_at_requires_import_files(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as caught:
        fetch_scryfall.main(["--data-dir", str(tmp_path), "--updated-at", "2026-10-18T00:00Z"])
    assert caught.value.code == 2
