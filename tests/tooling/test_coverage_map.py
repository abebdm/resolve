"""The rules coverage map (docs/roadmap.md) agrees with the pinned Comprehensive Rules.

The map has one row per numbered section of the CR (outside 701 and 702), one per keyword
action (701.2 onward) and one per keyword ability (702.2 onward), each as
``| CR | Name | Milestone | Tier | Notes |``. It is valid when:

- every heading of the pinned CR is a row exactly once, under the CR's own name, in the table
  for its kind, and no row names a rule that doesn't exist;
- the tier is E, S or X, except that rows with nothing to implement ("—") and rows that are out
  of scope have the tier "—";
- the milestone names real milestones (M0 to M9, or a step such as M2.1), "out of scope" or "—";
- every rule number the milestone and notes cite exists in the CR;
- every out-of-scope row gives its reason and is listed in the "Out of scope" table, whose
  numbers all exist.

The checks are run on the real map and, to prove each one can fail, on maps broken in one way.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from resolve.citations import RULE_LINE, cited_rules
from resolve.data.rules_text import PINNED_RULES_FILE, read_rules_text, rule_blocks
from tools.gaps import ENGINE_DIR, Gap, find_gaps

ROADMAP = Path(__file__).resolve().parents[2] / "docs" / "roadmap.md"

TABLES = {
    "### Numbered sections": "section",
    "### Keyword abilities (702)": "702",
    "### Keyword actions (701)": "701",
}
OUT_OF_SCOPE_HEADING = "### Out of scope"
TIERS = {"E", "S", "X", "—"}
MILESTONE = re.compile(r"\bM(\d)(?:\.\d+)?\b")
LISTED_NUMBER = re.compile(r"\b\d{3}(?:\.\d+[a-z]{0,2})?\b")


def headings(rules_text: str) -> dict[str, tuple[str, str]]:
    """The CR's headings by number: ``{number: (kind, name)}``, the kind being the table it
    belongs in (``"section"``, ``"701"`` or ``"702"``). 701 and 702 themselves are chapters of
    keywords, and 701.1 and 702.1 are introductions, not keywords."""
    found: dict[str, tuple[str, str]] = {}
    for number, block in rule_blocks(rules_text).items():
        match = RULE_LINE.match(block[0])
        assert match is not None
        name = str(match.group(2))
        if re.fullmatch(r"\d{3}", number) and number not in ("701", "702"):
            found[number] = ("section", name)
        elif re.fullmatch(r"70[12]\.\d+", number) and number not in ("701.1", "702.1"):
            found[number] = (number[:3], name)
    return found


def map_rows(map_text: str) -> list[tuple[str, list[str], str]]:
    """Every table row of the three tables: ``(kind, cells, line)`` with the five cells."""
    rows: list[tuple[str, list[str], str]] = []
    kind: str | None = None
    for line in map_text.splitlines():
        if line.startswith("#"):
            kind = TABLES.get(line.strip())
        elif kind is not None and line.startswith("| ") and not line.startswith("| CR "):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            rows.append((kind, cells, line))
    return rows


def out_of_scope_numbers(map_text: str) -> list[str]:
    """The rule numbers in the first column of the "Out of scope" table."""
    numbers: list[str] = []
    inside = False
    for line in map_text.splitlines():
        if line.startswith("#"):
            inside = line.strip() == OUT_OF_SCOPE_HEADING
        elif inside and line.startswith("| ") and not line.startswith("| Rows"):
            first = line.strip().strip("|").split("|")[0]
            first = re.sub(r"\([^)]*\)", "", first)  # "905 (the draft, 905.1-905.2)"
            numbers += LISTED_NUMBER.findall(first)
    return numbers


def map_problems(map_text: str, rules_text: str) -> list[str]:
    """Everything wrong with the map, as one sentence each; empty when it is valid."""
    problems: list[str] = []
    expected = headings(rules_text)
    blocks = rule_blocks(rules_text)
    seen: dict[str, int] = {}
    for kind, cells, line in map_rows(map_text):
        if len(cells) != 5:
            problems.append(f"row doesn't have five cells: {line}")
            continue
        number, name, milestone, tier, notes = cells
        seen[number] = seen.get(number, 0) + 1
        if number not in blocks:
            problems.append(f"{number} isn't a rule of the pinned CR")
        elif number not in expected or expected[number][0] != kind:
            problems.append(f"{number} isn't a heading of the {kind} table")
        elif name != expected[number][1]:
            problems.append(
                f"{number} is named {name!r}, but the CR names it {expected[number][1]!r}"
            )
        if tier not in TIERS:
            problems.append(f"{number} has the invalid tier {tier!r}")
        out_of_scope = milestone == "out of scope"
        if (tier == "—") != (out_of_scope or milestone == "—"):
            problems.append(f"{number}: tier {tier!r} doesn't fit milestone {milestone!r}")
        if not (out_of_scope or milestone == "—"):
            majors = [int(major) for major in MILESTONE.findall(milestone)]
            if not majors:
                problems.append(f"{number} has no valid milestone: {milestone!r}")
            if re.search(r"\bM\d{2,}\b", milestone):
                problems.append(f"{number} names a milestone that doesn't exist: {milestone!r}")
        if out_of_scope and not notes:
            problems.append(f"{number} is out of scope without a reason")
        for cited in cited_rules(f"{milestone} {notes}"):
            if cited not in blocks:
                problems.append(f"{number} cites {cited}, which isn't in the pinned CR")
    for number in expected:
        if seen.get(number, 0) == 0:
            problems.append(f"{number} ({expected[number][1]}) is missing from the map")
    for number, count in seen.items():
        if count > 1:
            problems.append(f"{number} appears {count} times")
    listed = out_of_scope_numbers(map_text)
    for number in listed:
        if number not in blocks:
            problems.append(f"the out-of-scope table names {number}, which isn't in the CR")
    for _, cells, _ in map_rows(map_text):
        if len(cells) == 5 and cells[2] == "out of scope" and cells[0] not in listed:
            problems.append(f"{cells[0]} is out of scope but isn't in the out-of-scope table")
    return problems


@pytest.fixture(scope="module")
def rules_text() -> str:
    return read_rules_text(PINNED_RULES_FILE)


@pytest.fixture(scope="module")
def map_text() -> str:
    return ROADMAP.read_text(encoding="utf-8")


def break_row(map_text: str, number: str, change: str) -> str:
    """``map_text`` with one row replaced by ``change`` (empty: removed); the row is found by
    its first cell."""
    lines = map_text.splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith(f"| {number} |"))
    if change:
        lines[index] = change
    else:
        del lines[index]
    return "\n".join(lines)


def test_the_real_map_matches_the_pinned_cr(map_text: str, rules_text: str) -> None:
    assert map_problems(map_text, rules_text) == []


def test_the_real_map_has_every_heading_once(map_text: str, rules_text: str) -> None:
    """The counts worked from the pinned CR: 145 numbered sections outside 701 and 702 (100 to
    999, 147 with those two), 70 keyword actions (701.2 to 701.71) and 194 keyword abilities
    (702.2 to 702.195)."""
    kinds = [kind for kind, _, _ in map_rows(map_text)]
    assert (kinds.count("section"), kinds.count("701"), kinds.count("702")) == (145, 70, 194)
    assert len(headings(rules_text)) == 145 + 70 + 194


def test_a_missing_section_fails(map_text: str, rules_text: str) -> None:
    problems = map_problems(break_row(map_text, "105", ""), rules_text)
    assert problems == ["105 (Colors) is missing from the map"]


def test_a_missing_keyword_fails(map_text: str, rules_text: str) -> None:
    for number in ("701.5", "702.8"):
        problems = map_problems(break_row(map_text, number, ""), rules_text)
        assert [p for p in problems if "is missing" in p] == [problems[0]]
        assert problems[0].startswith(f"{number} (")


def test_a_duplicated_row_fails(map_text: str, rules_text: str) -> None:
    line = next(line for line in map_text.splitlines() if line.startswith("| 105 |"))
    broken = map_text.replace(line, f"{line}\n{line}")
    assert map_problems(broken, rules_text) == ["105 appears 2 times"]


def test_a_bad_tier_fails(map_text: str, rules_text: str) -> None:
    line = next(line for line in map_text.splitlines() if line.startswith("| 105 |"))
    broken = break_row(map_text, "105", line.replace("| E |", "| Z |"))
    assert any("invalid tier 'Z'" in p for p in map_problems(broken, rules_text))


def test_a_wrong_name_fails(map_text: str, rules_text: str) -> None:
    line = next(line for line in map_text.splitlines() if line.startswith("| 105 |"))
    broken = break_row(map_text, "105", line.replace("Colors", "Colours"))
    assert map_problems(broken, rules_text) == [
        "105 is named 'Colours', but the CR names it 'Colors'"
    ]


def test_a_row_for_a_missing_rule_fails(map_text: str, rules_text: str) -> None:
    line = next(line for line in map_text.splitlines() if line.startswith("| 105 |"))
    broken = map_text.replace(line, f"{line}\n| 999 | Nothing | M2 | E |  |")
    assert "999 isn't a rule of the pinned CR" in map_problems(broken, rules_text)


def test_a_row_in_the_wrong_table_fails(map_text: str, rules_text: str) -> None:
    line = next(line for line in map_text.splitlines() if line.startswith("| 702.8 |"))
    broken = map_text.replace(line, f"{line}\n{line.replace('702.8', '701.5')}")
    problems = map_problems(broken, rules_text)
    assert "701.5 isn't a heading of the 702 table" in problems


def test_a_bad_milestone_fails(map_text: str, rules_text: str) -> None:
    for milestone in ("later", "M12", ""):
        broken = break_row(map_text, "105", f"| 105 | Colors | {milestone} | E |  |")
        assert map_problems(broken, rules_text), milestone


def test_an_out_of_scope_row_with_a_tier_fails(map_text: str, rules_text: str) -> None:
    line = next(line for line in map_text.splitlines() if line.startswith("| 211 |"))
    broken = break_row(map_text, "211", line.replace("| — |", "| E |"))
    assert any("tier 'E' doesn't fit" in p for p in map_problems(broken, rules_text))


def test_an_in_scope_row_without_a_tier_fails(map_text: str, rules_text: str) -> None:
    line = next(line for line in map_text.splitlines() if line.startswith("| 105 |"))
    broken = break_row(map_text, "105", line.replace("| E |", "| — |"))
    assert any("doesn't fit milestone" in p for p in map_problems(broken, rules_text))


def test_an_out_of_scope_row_without_a_reason_fails(map_text: str, rules_text: str) -> None:
    line = next(line for line in map_text.splitlines() if line.startswith("| 211 |"))
    broken = break_row(map_text, "211", line.replace("Vanguard", ""))
    assert "211 is out of scope without a reason" in map_problems(broken, rules_text)


def test_an_out_of_scope_row_missing_from_the_list_fails(map_text: str, rules_text: str) -> None:
    broken = break_row(map_text, "105", "| 105 | Colors | out of scope | — | a reason |")
    problems = map_problems(broken, rules_text)
    assert "105 is out of scope but isn't in the out-of-scope table" in problems


def test_a_citation_of_a_missing_rule_fails(map_text: str, rules_text: str) -> None:
    missing = "105." + "99"  # written in pieces: a citation checker reads this file too
    broken = break_row(map_text, "105", f"| 105 | Colors | M2 | E | see {missing} |")
    assert f"105 cites {missing}, which isn't in the pinned CR" in map_problems(broken, rules_text)


def test_the_out_of_scope_table_naming_a_missing_rule_fails(map_text: str, rules_text: str) -> None:
    broken = map_text.replace("| 713 |", "| 713, 799 |")
    assert "the out-of-scope table names 799, which isn't in the CR" in map_problems(
        broken, rules_text
    )


# --- The gaps and the map ----------------------------------------------------------------------

# A milestone not ticked off: "M4" without a following "✓". Steps ("M2.3") only say which step
# did a part.
OPEN_MILESTONE = re.compile(r"\bM\d\b(?!\.\d)(?! ✓)")


def gap_row(rule: str) -> str:
    """The map row a gap's rule belongs to: its keyword (701.x, 702.x) or its section."""
    keyword = re.match(r"70[12]\.\d+", rule)
    return keyword.group(0) if keyword else rule[:3]


def gap_problems(map_text: str, gaps: list[Gap]) -> list[str]:
    """Each ``NotImplementedRule`` gap (``tools/gaps.py``) whose map row says its rules are all
    done: a row must leave room for the gap with a milestone not ticked off ("M4", "601.3b
    M6"), a set-mechanic or exotic tier (implemented in M9 unless a deck needs it), or "out of
    scope". One sentence per gap; empty when every gap has an open row."""
    rows = {cells[0]: cells for _, cells, _ in map_rows(map_text) if len(cells) == 5}
    problems: list[str] = []
    for gap in gaps:
        number = gap_row(gap.rule)
        cells = rows.get(number)
        if cells is None:
            problems.append(f"gap {gap.rule} ({gap.what}): no row {number} in the map")
            continue
        _, _, milestone, tier, _ = cells
        if OPEN_MILESTONE.search(milestone) or tier in ("S", "X") or milestone == "out of scope":
            continue
        problems.append(f"gap {gap.rule} ({gap.what}): row {number} is all done: {milestone!r}")
    return problems


def test_every_gap_has_an_open_row_in_the_map(map_text: str) -> None:
    """``tools/gaps.py`` agrees with the map (plan M2.11): every rule the engine raises
    ``NotImplementedRule`` for belongs to a row that leaves a milestone for it."""
    gaps, unlistable = find_gaps(ENGINE_DIR)
    assert unlistable == []
    assert gaps, "the engine has gaps to check"
    assert gap_problems(map_text, gaps) == []


def test_a_gap_in_a_row_ticked_off_fails(map_text: str) -> None:
    """508.1 (declaring attackers) is a gap; a map claiming 508 done in M3 is wrong."""
    gap = Gap("508.1", "declaring attackers", ENGINE_DIR / "engine" / "turns.py", 1)
    broken = break_row(map_text, "508", "| 508 | Declare Attackers Step | M3 ✓ | E |  |")
    assert gap_problems(broken, [gap]) == [
        "gap 508.1 (declaring attackers): row 508 is all done: 'M3 ✓'"
    ]
    assert gap_problems(map_text, [gap]) == []


def test_a_gap_of_a_keyword_is_checked_against_the_keywords_row(map_text: str) -> None:
    """702.11d (a player with hexproof from a quality) belongs to the hexproof row (702.11), not
    to the section 702; a set-mechanic row (702.102, fuse) leaves room for its gaps."""
    gap = Gap("702.11d", "a player with hexproof from", ENGINE_DIR / "rules" / "legality.py", 1)
    broken = break_row(map_text, "702.11", "| 702.11 | Hexproof | M2 ✓ (M2.8) | E | D |")
    assert gap_problems(broken, [gap]) == [
        "gap 702.11d (a player with hexproof from): row 702.11 is all done: 'M2 ✓ (M2.8)'"
    ]
    fuse = Gap("702.102", "casting a fused split spell", ENGINE_DIR / "engine" / "casting.py", 1)
    assert gap_problems(map_text, [fuse]) == []
