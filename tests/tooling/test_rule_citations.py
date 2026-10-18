"""Every CR number the engine cites exists in the pinned rules file (CLAUDE.md rules 2 and 3).

Citations are collected three ways, so a typo or a renumbered rule is caught wherever it is:

- statically, from the engine source: string constants in ``rules=`` arguments, every
  ``NotImplementedRule`` message (via ``tools/gaps.py``), and every dotted CR number such as
  ``613.7m`` in comments and docstrings;
- at run time, from the event log and decision requests of a game.
"""

from __future__ import annotations

import ast
import re
from functools import cache
from pathlib import Path

import pytest

from resolve.citations import is_rule_reference
from resolve.events.base import LogEntry
from tests.game_fixtures import choose_starting_player, request_of, start
from tools.gaps import find_gaps

REPO = Path(__file__).resolve().parents[2]
ENGINE = REPO / "src" / "resolve"
RULES_FILE = REPO / "docs" / "rules" / "MagicCompRules-20260925.txt"

# "103. Starting the Game", "103.1. At the start...", "103.1a In a game..."
_SECTION = re.compile(r"^(\d{3})\. ")
_RULE = re.compile(r"^(\d{3}\.\d+)\. ")
_SUBRULE = re.compile(r"^(\d{3}\.\d+[a-z]) ")
# A dotted CR number in prose: three digits, a dot, a number, maybe a letter ("613.7m").
_DOTTED = re.compile(r"(?<![\w.])([1-9]\d{2}\.\d+[a-z]?)(?![\w.]*\d)")


@cache
def pinned_rules() -> frozenset[str]:
    """Every section, rule and subrule number in the pinned CR."""
    numbers: set[str] = set()
    for line in RULES_FILE.read_text(encoding="utf-8").splitlines():
        for pattern in (_SECTION, _RULE, _SUBRULE):
            match = pattern.match(line)
            if match:
                numbers.add(match.group(1))
    return frozenset(numbers)


def structured_citations(source: str) -> list[str]:
    """String constants passed as ``rules=`` (a tuple or a single string)."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg != "rules":
                    continue
                values = (
                    keyword.value.elts if isinstance(keyword.value, ast.Tuple) else [keyword.value]
                )
                found += [
                    v.value
                    for v in values
                    if isinstance(v, ast.Constant) and isinstance(v.value, str)
                ]
    return found


def prose_citations(source: str) -> list[str]:
    """Dotted CR numbers anywhere in the text: comments, docstrings, messages."""
    return _DOTTED.findall(source)


def engine_citations() -> dict[str, list[str]]:
    """Each cited rule, with where it is cited."""
    cited: dict[str, list[str]] = {}
    for path in sorted(ENGINE.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        where = str(path.relative_to(REPO))
        for rule in structured_citations(source) + prose_citations(source):
            cited.setdefault(rule, []).append(where)
    gaps, unlistable = find_gaps(ENGINE)
    assert unlistable == []
    for gap in gaps:
        cited.setdefault(gap.rule, []).append(f"{gap.path.relative_to(REPO)}:{gap.line}")
    return cited


def test_the_rules_file_parses_into_sections_rules_and_subrules() -> None:
    rules = pinned_rules()
    assert {"103", "103.1", "103.1a", "613.7m", "701.24a", "903.10a"} <= rules
    assert "613.7l" not in rules, "the CR skips the letters l and o"
    assert len(rules) > 2500


def test_the_extractors_find_citations_in_all_their_forms() -> None:
    source = '''
"""Implements 613.7d and 400.7, not version 3.12 or 1.1.390."""
Event(rules=("103.1", "701.24a"))
NeedDecision(rules="117.1")
x = 0x1234  # 999.9z is a bad citation
'''
    assert structured_citations(source) == ["103.1", "701.24a", "117.1"]
    assert prose_citations(source) == ["613.7d", "400.7", "103.1", "701.24a", "117.1", "999.9z"]
    assert "999.9z" not in pinned_rules()


def test_every_rule_cited_in_the_engine_source_exists_in_the_pinned_cr() -> None:
    cited = engine_citations()
    assert {"103.1", "103.5", "701.24a"} <= set(cited), "the scan finds the engine's citations"
    malformed = {rule: where for rule, where in cited.items() if not is_rule_reference(rule)}
    assert malformed == {}
    missing = {rule: where for rule, where in cited.items() if rule not in pinned_rules()}
    assert missing == {}


@pytest.mark.parametrize("players", [2, 4])
def test_every_rule_cited_during_a_game_exists_in_the_pinned_cr(players: int) -> None:
    state = start(players)
    cited = set(request_of(state).rules)
    gap = choose_starting_player(state, 0)
    cited.add(gap.rule)
    entries: list[LogEntry] = state.event_log
    cited.update(rule for entry in entries for rule in entry.rules)
    assert len(entries) == 2 + players
    assert sorted(cited - pinned_rules()) == []
