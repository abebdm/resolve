"""The rules coverage map (docs/roadmap.md) stays in step with the pinned CR (M2.1).

From the approved plan (M2.1) and CLAUDE.md ("Planning a milestone"): the map lists every
numbered section of the pinned CR outside 701 and 702, and every keyword action (701.x) and
keyword ability (702.x), exactly once and with its CR name; each row has a valid milestone and
tier, and every out-of-scope row a reason; no row names a rule the CR doesn't have.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from resolve.data.coverage_map import MapRow, map_problems, parse_map, rule_headings
from resolve.data.rules_text import PINNED_RULES_FILE, read_rules_text

ROADMAP = Path(__file__).resolve().parents[2] / "docs" / "roadmap.md"

HEADINGS = rule_headings(read_rules_text(PINNED_RULES_FILE))
ROWS = parse_map(ROADMAP.read_text(encoding="utf-8-sig"))


def broken(rows: list[MapRow], at: int, **changes: str) -> list[MapRow]:
    """``rows`` with row ``at`` changed."""
    return [dataclasses.replace(row, **changes) if i == at else row for i, row in enumerate(rows)]


def test_the_pinned_cr_has_the_expected_headings() -> None:
    """The handoff counts: 145 sections outside 701 and 702, 194 keyword abilities, 70 keyword
    actions."""
    sections = [n for n in HEADINGS if "." not in n]
    assert len(sections) == 145
    assert len([n for n in HEADINGS if n.startswith("702.")]) == 194
    assert len([n for n in HEADINGS if n.startswith("701.")]) == 70
    assert HEADINGS["100"] == "General"
    assert HEADINGS["702.2"] == "Deathtouch"
    assert "701" not in HEADINGS and "702.1" not in HEADINGS and "701.1" not in HEADINGS


def test_the_coverage_map_matches_the_pinned_cr() -> None:
    assert map_problems(ROWS, HEADINGS) == []
    assert len(ROWS) == len(HEADINGS)


def test_a_missing_section_fails() -> None:
    rows = [row for row in ROWS if row.cr != "305"]
    assert map_problems(rows, HEADINGS) == ["305 (Lands) is missing"]


def test_a_missing_keyword_fails() -> None:
    rows = [row for row in ROWS if row.cr != "702.9"]
    assert map_problems(rows, HEADINGS) == [f"702.9 ({HEADINGS['702.9']}) is missing"]


def test_a_duplicated_row_fails() -> None:
    index = next(i for i, row in enumerate(ROWS) if row.cr == "704")
    assert map_problems([*ROWS, ROWS[index]], HEADINGS) == ["704 is listed 2 times"]


def test_a_bad_tier_fails() -> None:
    problems = map_problems(broken(ROWS, 0, tier="Z"), HEADINGS)
    assert problems == [f"{ROWS[0].cr} has the invalid tier 'Z'"]


def test_a_bad_milestone_fails() -> None:
    problems = map_problems(broken(ROWS, 0, milestone="soon"), HEADINGS)
    assert problems == [f"{ROWS[0].cr} has the invalid milestone 'soon'"]


def test_a_row_naming_a_missing_rule_fails() -> None:
    extra = MapRow("999", "Nothing", "M9", "X", "")
    assert map_problems([*ROWS, extra], HEADINGS) == ["999 isn't a heading of the pinned rules"]


def test_a_wrong_name_fails() -> None:
    problems = map_problems(broken(ROWS, 0, name="Something else"), HEADINGS)
    assert problems == [f"{ROWS[0].cr} is named 'Something else', but the CR calls it 'General'"]


def test_an_out_of_scope_row_needs_a_reason() -> None:
    index = next(i for i, row in enumerate(ROWS) if row.milestone == "out of scope")
    problems = map_problems(broken(ROWS, index, notes=""), HEADINGS)
    assert problems == [f"{ROWS[index].cr} is out of scope without a reason"]


def test_a_row_with_no_work_has_no_tier() -> None:
    index = next(i for i, row in enumerate(ROWS) if row.milestone == "—")
    assert map_problems(broken(ROWS, index, tier="E"), HEADINGS) == [
        f"{ROWS[index].cr} has no work, so its tier must be —"
    ]


def test_a_row_with_work_needs_a_real_tier() -> None:
    index = next(i for i, row in enumerate(ROWS) if row.milestone.startswith("M"))
    assert map_problems(broken(ROWS, index, tier="—"), HEADINGS) == [
        f"{ROWS[index].cr} has the invalid tier '—'"
    ]


def test_the_tables_parse_into_rows_in_order() -> None:
    text = "| CR | Name |\n|---|---|\n| 100 | General | M0 ✓ | E |  |\n| 1.2 | no | a | b | c |\n"
    assert parse_map(text) == [MapRow("100", "General", "M0 ✓", "E", "")]
