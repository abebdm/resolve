"""The rules coverage map (docs/roadmap.md) and the checks that keep it true to the pinned CR.

The map has one row per numbered section of the CR (outside 701 and 702, which the keyword
action and keyword ability rows below them cover), per keyword action (701.x) and per keyword
ability (702.x): ``| CR | Name | Milestone | Tier | Notes |``. ``map_problems`` lists everything
wrong with a map; ``tests/tooling/test_coverage_map.py`` requires none. The engine doesn't use
this module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# "100. General" (a section) and "702.2. Deathtouch" (a keyword): headings, unlike the rules
# "100.1. These Magic rules..." that share their shape, have a name and no further text. The
# sections 701 and 702 and the introductions 701.1 and 702.1 have no row of their own.
_SECTION = re.compile(r"^(\d{3})\.\s+(\S.*)$")
_KEYWORD = re.compile(r"^(70[12]\.\d+)\.\s+(\S.*)$")
_ROW_NUMBER = re.compile(r"^\d{3}(\.\d+)?$")
_MILESTONE = re.compile(r"^(M\d\b.*|—|out of scope)$")

OUT_OF_SCOPE = "out of scope"
TIERS = ("E", "S", "X")
NO_TIER = "—"


@dataclass(frozen=True)
class MapRow:
    """One row of the coverage map."""

    cr: str
    name: str
    milestone: str
    tier: str
    notes: str


def rule_headings(rules_text: str) -> dict[str, str]:
    """The headings a coverage map must list, by number: every numbered section except 701 and
    702, and every keyword action and keyword ability (701.2 and up, 702.2 and up)."""
    headings: dict[str, str] = {}
    for raw in rules_text.splitlines():
        line = raw.strip()
        match = _KEYWORD.match(line)
        if match:
            if match.group(1).split(".")[1] != "1":
                headings[match.group(1)] = match.group(2)
            continue
        match = _SECTION.match(line)
        if match and match.group(1) not in ("701", "702"):
            headings[match.group(1)] = match.group(2)
    return headings


def parse_map(markdown: str) -> list[MapRow]:
    """The rows of every table in ``markdown``, in order. A row is a line of five cells whose
    first is a rule number (``100`` or ``702.2``); the header, the separator and the tables of
    other shapes (the out-of-scope list) don't count."""
    rows: list[MapRow] = []
    for line in markdown.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == 5 and _ROW_NUMBER.match(cells[0]):
            rows.append(MapRow(*cells))
    return rows


def map_problems(rows: list[MapRow], headings: dict[str, str]) -> list[str]:
    """Everything wrong with ``rows``: against ``headings`` (every heading exactly once, with
    its CR name, and no row for a rule that doesn't exist), and in itself (a milestone, a tier,
    and a reason for each out-of-scope row)."""
    problems: list[str] = []
    seen: dict[str, int] = {}
    for row in rows:
        seen[row.cr] = seen.get(row.cr, 0) + 1
    for number, count in seen.items():
        if count > 1:
            problems.append(f"{number} is listed {count} times")
        if number not in headings:
            problems.append(f"{number} isn't a heading of the pinned rules")
    for number in headings:
        if number not in seen:
            problems.append(f"{number} ({headings[number]}) is missing")
    for row in rows:
        if row.cr in headings and row.name != headings[row.cr]:
            problems.append(
                f"{row.cr} is named {row.name!r}, but the CR calls it {headings[row.cr]!r}"
            )
        if not _MILESTONE.match(row.milestone):
            problems.append(f"{row.cr} has the invalid milestone {row.milestone!r}")
        elif row.milestone in (OUT_OF_SCOPE, "—"):
            if row.tier != NO_TIER:
                problems.append(f"{row.cr} has no work, so its tier must be {NO_TIER}")
            if row.milestone == OUT_OF_SCOPE and not row.notes:
                problems.append(f"{row.cr} is out of scope without a reason")
        elif row.tier not in TIERS:
            problems.append(f"{row.cr} has the invalid tier {row.tier!r}")
    return problems
