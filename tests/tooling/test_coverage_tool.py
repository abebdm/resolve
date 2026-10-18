"""Tests for tools/coverage.py."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from resolve.cards.coverage import deck_coverage
from resolve.cards.registry import CardDefinition, CardRegistry
from resolve.data.cards import CardDatabase, load_card_database, parse_card, parse_oracle_cards
from resolve.data.decklist import parse_decklist
from tests import scryfall_fixtures as fx
from tools import coverage as coverage_tool
from tools.coverage import describe_card, format_report, run

REPO_ROOT = Path(__file__).resolve().parents[2]

DECK = """\
Commander
1 Test Daybreaker

Mainboard
1 Llanowar Elves
30 Forest
1 Not A Real Card

Sideboard
1 Test Spark // Test Frost
"""


def database() -> CardDatabase:
    return CardDatabase(parse_oracle_cards(fx.default_cards()))


def registry() -> CardRegistry:
    return CardRegistry([CardDefinition("Forest")])


def write_deck(tmp_path: Path, text: str = DECK, name: str = "deck.txt") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_describe_card_shows_every_face() -> None:
    lines = describe_card(parse_card(fx.TRANSFORM_CARD))
    assert lines == [
        "Test Daybreaker {1}{G}",
        "Creature — Human",
        "At the beginning of each upkeep, transform this creature.",
        "2/2",
        "Test Nightfall",
        "Creature — Werewolf",
        "Trample",
        "4/4",
    ]


def test_describe_card_without_power() -> None:
    assert describe_card(parse_card(fx.FOREST)) == [
        "Forest",
        "Basic Land — Forest",
        "({T}: Add {G}.)",
    ]


def test_report_lists_cards_by_status_with_counts() -> None:
    coverage = deck_coverage(parse_decklist(DECK, name="deck"), database(), registry())
    report = format_report(coverage)
    assert report.splitlines()[:2] == [
        "== deck ==",
        "33 cards, 4 distinct: 1 implemented, 2 missing, 1 unknown, 0 unreadable",
    ]
    assert "Unknown (not in the card data):\n  1 Not A Real Card  [Mainboard]  -- no card" in report
    assert "Missing:\n  1 Test Daybreaker  [Commander]  (faces missing: " in report
    assert "Implemented:\n  30 Forest  [Mainboard]" in report
    assert "Test Spark" not in report, "the sideboard is out of scope"
    assert "{T}: Add {G}." not in report


def test_report_with_oracle_text_shows_missing_cards_only() -> None:
    coverage = deck_coverage(parse_decklist(DECK), database(), registry())
    report = format_report(coverage, show_oracle=True)
    assert "      {T}: Add {G}." in report  # Llanowar Elves is missing
    assert "      ({T}: Add {G}.)" not in report  # Forest is implemented


def test_report_counts_scryfall_keywords() -> None:
    coverage = deck_coverage(parse_decklist(DECK), database(), registry())
    report = format_report(coverage)
    assert report.endswith(
        "Keywords (from Scryfall, distinct cards):\n  Trample: 1\n  Transform: 1"
    )


def test_run_fails_on_unknown_cards(tmp_path: Path) -> None:
    report, status = run([write_deck(tmp_path)], database(), registry())
    assert status == 1
    assert "Registered definitions: 1" in report


def test_run_passes_when_all_names_are_known(tmp_path: Path) -> None:
    deck = write_deck(tmp_path, "Mainboard\n1 Llanowar Elves\n59 Forest\n")
    assert run([deck], database(), registry())[1] == 0
    assert run([deck], database(), registry(), require_complete=True)[1] == 1
    complete = CardRegistry([CardDefinition("Forest"), CardDefinition("Llanowar Elves")])
    assert run([deck], database(), complete, require_complete=True)[1] == 0


def test_run_reports_unparseable_and_missing_decks(tmp_path: Path) -> None:
    bad = write_deck(tmp_path, "1 Forest\n", name="bad.txt")
    good = write_deck(tmp_path, "Mainboard\n1 Forest\n", name="good.txt")
    report, status = run([bad, tmp_path / "absent.txt", good], database(), registry())
    assert status == 1
    assert "error: bad:1: card line before any section header" in report
    assert "absent.txt" in report
    assert "== good ==" in report


def test_main_reads_the_snapshot(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data_dir = tmp_path / "data"
    fx.write_snapshot(data_dir)
    deck = write_deck(tmp_path, "Mainboard\n1 Llanowar Elves\n")
    assert coverage_tool.main([str(deck), "--data-dir", str(data_dir)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("Card data: Snapshot 2026-10-18\n")
    assert "1 cards, 1 distinct: 0 implemented, 1 missing, 0 unknown" in out


def test_main_without_snapshot_fails_clearly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert coverage_tool.main(["--data-dir", str(tmp_path)]) == 1
    assert "fetch_scryfall" in capsys.readouterr().err


def test_main_defaults_to_the_target_decks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fx.write_snapshot(tmp_path)
    assert coverage_tool.main(["--data-dir", str(tmp_path)]) == 1  # fixture lacks their cards
    out = capsys.readouterr().out
    assert "== byrke_counters ==" in out
    assert "== gishath_dinosaurs ==" in out
    assert load_card_database(tmp_path).snapshot is not None


def test_redirected_report_with_oracle_text_is_written_as_utf8(tmp_path: Path) -> None:
    """Windows encodes redirected output as cp1252, which has no "\u2212" (U+2212), the minus
    sign of planeswalker abilities. ``PYTHONIOENCODING=cp1252`` recreates that; the whole report
    must still be written, as UTF-8."""
    walker = fx.simple_card(
        "Test Walker",
        "oid-test-walker",
        type_line="Legendary Planeswalker \u2014 Test",
        oracle_text="+1: Draw a card.\n\u22123: Exile target creature.",
        loyalty="4",
    )
    fx.write_snapshot(tmp_path / "data", cards=[fx.LLANOWAR_ELVES, walker])
    deck = write_deck(tmp_path, "Mainboard\n1 Test Walker\n9 Llanowar Elves\n")
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools" / "coverage.py"),
            "--oracle",
            "--data-dir",
            str(tmp_path / "data"),
            str(deck),
        ],
        cwd=REPO_ROOT,
        env=dict(os.environ, PYTHONIOENCODING="cp1252"),
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    report = completed.stdout.decode("utf-8").replace("\r\n", "\n")
    assert (
        "  1 Test Walker  [Mainboard]\n"
        "      Test Walker {1}\n"
        "      Legendary Planeswalker \u2014 Test\n"
        "      +1: Draw a card.\n"
        "      \u22123: Exile target creature.\n"
        "      Loyalty 4\n"
    ) in report
    assert report.endswith(
        "  9 Llanowar Elves  [Mainboard]\n"
        "      Llanowar Elves {G}\n"
        "      Creature \u2014 Elf Druid\n"
        "      {T}: Add {G}.\n"
        "      1/1\n"
        "\n"
    )
