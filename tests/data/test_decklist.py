"""Tests for the decklist parser (resolve.data.decklist)."""

from __future__ import annotations

import codecs
from pathlib import Path

import pytest

from resolve.data.decklist import (
    DeckEntry,
    Decklist,
    DecklistError,
    Section,
    load_decklist,
    parse_decklist,
)

DECKS_DIR = Path(__file__).resolve().parents[2] / "decks"

SAMPLE = """\
# A comment
# Format: '<count> <card name>' per line.

Commander
1 Gishath, Sun's Avatar

Mainboard
1 Akroma's Will
8 Forest
1 Fire // Ice

Sideboard
1 Bronzebeak Foragers
"""


def test_parses_sections_in_order() -> None:
    deck = parse_decklist(SAMPLE, name="sample")
    assert deck.name == "sample"
    assert deck.commander == (DeckEntry(1, "Gishath, Sun's Avatar"),)
    assert deck.mainboard == (
        DeckEntry(1, "Akroma's Will"),
        DeckEntry(8, "Forest"),
        DeckEntry(1, "Fire // Ice"),
    )
    assert deck.sideboard == (DeckEntry(1, "Bronzebeak Foragers"),)
    assert deck.section(Section.MAINBOARD) == deck.mainboard


def test_entries_exclude_sideboard_unless_asked() -> None:
    deck = parse_decklist(SAMPLE)
    assert deck.card_count() == 11
    assert deck.card_count(include_sideboard=True) == 12
    assert deck.unique_names() == (
        "Gishath, Sun's Avatar",
        "Akroma's Will",
        "Forest",
        "Fire // Ice",
    )
    assert deck.unique_names(include_sideboard=True)[-1] == "Bronzebeak Foragers"


def test_empty_text_is_an_empty_deck() -> None:
    deck = parse_decklist("")
    assert deck == Decklist()
    assert deck.card_count() == 0
    assert deck.unique_names() == ()


def test_section_headers_are_case_insensitive_and_whitespace_tolerant() -> None:
    deck = parse_decklist("  COMMANDER  \n1 Test Card\nmainboard\r\n 2   Forest \r\n")
    assert deck.commander == (DeckEntry(1, "Test Card"),)
    assert deck.mainboard == (DeckEntry(2, "Forest"),)


def test_missing_sections_are_empty() -> None:
    deck = parse_decklist("Mainboard\n60 Forest\n")
    assert deck.commander == ()
    assert deck.sideboard == ()


def test_repeated_card_lines_in_a_section_are_added_together() -> None:
    deck = parse_decklist("Mainboard\n3 Forest\n1 Plains\n4 Forest\n")
    assert deck.mainboard == (DeckEntry(7, "Forest"), DeckEntry(1, "Plains"))


def test_same_card_in_two_sections_stays_separate() -> None:
    deck = parse_decklist("Mainboard\n1 Test Card\nSideboard\n1 Test Card\n")
    assert deck.mainboard == (DeckEntry(1, "Test Card"),)
    assert deck.sideboard == (DeckEntry(1, "Test Card"),)
    assert deck.unique_names(include_sideboard=True) == ("Test Card",)


def test_card_names_are_kept_exactly() -> None:
    """Names are not normalized: lookup in the card data is exact (no approximation)."""
    deck = parse_decklist("Mainboard\n1 Lae'zel, Vlaakith's Champion\n1 forest\n")
    assert deck.unique_names() == ("Lae'zel, Vlaakith's Champion", "forest")


def test_hash_inside_a_name_is_not_a_comment() -> None:
    deck = parse_decklist("Mainboard\n1 Test #1 Card\n")
    assert deck.unique_names() == ("Test #1 Card",)


@pytest.mark.parametrize(
    ("text", "line", "message"),
    [
        ("1 Forest\n", 1, "before any section header"),
        ("Mainboard\nForest\n", 2, "expected '<count> <card name>'"),
        ("Mainboard\nx1 Forest\n", 2, "expected '<count> <card name>'"),
        ("Mainboard\n1x Forest\n", 2, "expected '<count> <card name>'"),
        ("Mainboard\n-1 Forest\n", 2, "expected '<count> <card name>'"),
        ("Mainboard\n1\n", 2, "expected '<count> <card name>'"),
        ("Mainboard\n0 Forest\n", 2, "count must be at least 1"),
        ("Mainboard\n1 Forest\n\nMainboard\n", 4, "appears more than once"),
        ("Main deck\n1 Forest\n", 1, "expected '<count> <card name>'"),
    ],
)
def test_malformed_lines_are_rejected_with_their_line_number(
    text: str, line: int, message: str
) -> None:
    with pytest.raises(DecklistError, match=message) as caught:
        parse_decklist(text, name="bad")
    assert caught.value.line == line
    assert caught.value.source == "bad"
    assert str(caught.value).startswith(f"bad:{line}: ")


def test_error_without_deck_name_still_reports_line() -> None:
    with pytest.raises(DecklistError, match=r"^line 1: "):
        parse_decklist("1 Forest\n")


def test_load_decklist_names_deck_after_file(tmp_path: Path) -> None:
    path = tmp_path / "my_deck.txt"
    path.write_text("Mainboard\n1 Forest\n", encoding="utf-8")
    assert load_decklist(path).name == "my_deck"


WINDOWS_DECK = "Commander\r\n1 Lim-D\u00fbl the Necromancer\r\n\r\nMainboard\r\n8 Forest\r\n"


@pytest.mark.parametrize(
    "encoded",
    [
        WINDOWS_DECK.encode("utf-8"),
        codecs.BOM_UTF8 + WINDOWS_DECK.encode("utf-8"),
        codecs.BOM_UTF16_LE + WINDOWS_DECK.encode("utf-16-le"),
        codecs.BOM_UTF16_BE + WINDOWS_DECK.encode("utf-16-be"),
    ],
    ids=["utf-8", "utf-8 with BOM", "utf-16-le with BOM", "utf-16-be with BOM"],
)
def test_load_decklist_reads_the_encodings_windows_tools_write(
    tmp_path: Path, encoded: bytes
) -> None:
    """Notepad and PowerShell 5.1 (``Out-File -Encoding utf8``) save UTF-8 with a byte order
    mark, and PowerShell 5.1's ``>`` saves UTF-16 with one. The mark isn't part of the text, so
    the first line is still a section header and the card name keeps its accent."""
    path = tmp_path / "windows_deck.txt"
    path.write_bytes(encoded)
    deck = load_decklist(path)
    assert deck.commander == (DeckEntry(1, "Lim-D\u00fbl the Necromancer"),)
    assert deck.mainboard == (DeckEntry(8, "Forest"),)


def test_load_decklist_refuses_text_that_is_not_utf8(tmp_path: Path) -> None:
    """A deck saved as "ANSI" (cp1252) isn't guessed at: the same bytes mean different names in
    different code pages. The error is a DecklistError that names the file, not a traceback."""
    path = tmp_path / "ansi_deck.txt"
    path.write_bytes("Mainboard\r\n1 Lim-D\u00fbl the Necromancer\r\n".encode("cp1252"))
    with pytest.raises(DecklistError, match=r"ansi_deck\.txt.*UTF-8") as caught:
        load_decklist(path)
    assert caught.value.source == "ansi_deck"


@pytest.mark.parametrize(
    ("file_name", "commander", "unique_mainboard"),
    [
        ("gishath_dinosaurs.txt", "Gishath, Sun's Avatar", 86),
        ("byrke_counters.txt", "Byrke, Long Ear of the Law", 81),
    ],
)
def test_target_decks_parse_as_100_card_commander_decks(
    file_name: str, commander: str, unique_mainboard: int
) -> None:
    """The target decks (docs/roadmap.md): one commander plus 99 cards, sideboard separate."""
    deck = load_decklist(DECKS_DIR / file_name)
    assert deck.commander == (DeckEntry(1, commander),)
    assert deck.card_count() == 100
    assert len(deck.mainboard) == unique_mainboard
