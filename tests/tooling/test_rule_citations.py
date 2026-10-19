"""Every CR number the engine cites exists in the pinned rules file (CLAUDE.md rules 2 and 3).

Citations are collected three ways, so a typo or a renumbered rule is caught wherever it is:

- statically, from the engine source: string constants in ``rules=`` arguments, every
  ``NotImplementedRule`` message (via ``tools/gaps.py``), and every dotted CR number such as
  ``613.7m`` in comments and docstrings;
- at run time, from the event log and decision requests of a game.
"""

from __future__ import annotations

import ast
from functools import cache
from pathlib import Path

import pytest

from resolve.agents.driver import play
from resolve.agents.random_agent import RandomAgent
from resolve.citations import cited_rules, is_rule_reference
from resolve.data.rules_text import PINNED_RULES_FILE, parse_rules
from resolve.errors import NotImplementedRule
from resolve.events.base import LogEntry
from tests.game_fixtures import request_of, start
from tools.gaps import find_gaps
from tools.rules_diff import find_citations

REPO = Path(__file__).resolve().parents[2]
ENGINE = REPO / "src" / "resolve"
RULES_FILE = PINNED_RULES_FILE


@cache
def pinned_rules() -> frozenset[str]:
    """Every section, rule and subrule number in the pinned CR."""
    return frozenset(parse_rules(RULES_FILE.read_text(encoding="utf-8")))


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
    return cited_rules(source)


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
    assert {"103", "103.1", "103.1a", "613.7m", "701.24a", "903.10a", "704.5aa"} <= rules
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
    assert {"103.1", "103.5", "121.2c", "701.24a"} <= set(cited), "the scan finds citations"
    malformed = {rule: where for rule, where in cited.items() if not is_rule_reference(rule)}
    assert malformed == {}
    missing = {rule: where for rule, where in cited.items() if rule not in pinned_rules()}
    assert missing == {}


@pytest.mark.parametrize("players", [2, 4])
def test_every_rule_cited_during_a_game_exists_in_the_pinned_cr(players: int) -> None:
    state = start(players)
    cited = set(request_of(state).rules)
    try:
        play(state, RandomAgent(players), max_answers=50)  # through the mulligans (103.5)
    except NotImplementedRule as gap:
        cited.add(gap.rule)
    if state.pending is not None:
        cited.update(state.pending.rules)
    entries: list[LogEntry] = state.event_log
    cited.update(rule for entry in entries for rule in entry.rules)
    cited.update(rule for entry in entries if entry.redacted for rule in entry.redacted.rules)
    assert {"103.5", "121.2c"} <= cited
    assert sorted(cited - pinned_rules()) == []


# Files that cite invented rule numbers on purpose, as test data for the citation tools.
_SYNTHETIC_CITATIONS = {
    "tests/tooling/test_rule_citations.py",
    "tests/tooling/test_rules_diff.py",
    "tests/tooling/test_rule_tool.py",
    "tests/tooling/test_gaps_tool.py",
    "tests/state/test_errors_and_citations.py",
}


def test_every_rule_cited_anywhere_in_src_tools_and_tests_exists_in_the_pinned_cr() -> None:
    """Catches a citation left behind by a CR update, in tests and tools as well as the engine."""
    files = [
        path
        for folder in ("src", "tools", "tests")
        for path in sorted((REPO / folder).rglob("*.py"))
        if path.relative_to(REPO).as_posix() not in _SYNTHETIC_CITATIONS
    ]
    cited = find_citations(files, relative_to=REPO)
    assert {"103.1", "704.5g"} <= set(cited), "the scan finds citations"
    missing = {rule: where for rule, where in cited.items() if rule not in pinned_rules()}
    assert missing == {}
