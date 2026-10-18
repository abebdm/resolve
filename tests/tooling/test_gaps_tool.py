"""Tests for tools/gaps.py: the generated list of NotImplementedRule gaps."""

from __future__ import annotations

import codecs
from pathlib import Path

import pytest

from tools import gaps as gaps_tool
from tools.gaps import find_gaps, rule_sort_key

SOURCE = """
from resolve.errors import NotImplementedRule
from resolve import errors

def a():
    raise NotImplementedRule("613.7m: ordering simultaneous timestamps")

def b(n):
    raise errors.NotImplementedRule(f"103.5: mulligan number {n}")

def c():
    raise NotImplementedRule("103.10: an invented later rule")
"""


def write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_finds_literal_and_f_string_gaps_sorted_by_rule(tmp_path: Path) -> None:
    write(tmp_path, "pkg/mod.py", SOURCE)
    write(tmp_path, "other.py", 'raise NotImplementedRule("104.3a: conceding")\n')
    gaps, unlistable = find_gaps(tmp_path)
    assert unlistable == []
    assert [(gap.rule, gap.what, gap.path.name, gap.line) for gap in gaps] == [
        ("103.5", "mulligan number ", "mod.py", 9),
        ("103.10", "an invented later rule", "mod.py", 12),
        ("104.3a", "conceding", "other.py", 1),
        ("613.7m", "ordering simultaneous timestamps", "mod.py", 6),
    ]


def test_gaps_whose_message_cannot_be_read_are_reported(tmp_path: Path) -> None:
    write(
        tmp_path,
        "bad.py",
        "msg = 'x'\nraise NotImplementedRule(msg)\nraise NotImplementedRule('no rule here')\n"
        "raise NotImplementedRule(f'{msg}: dynamic rule')\n",
    )
    gaps, unlistable = find_gaps(tmp_path)
    assert gaps == []
    assert [(u.line, u.reason) for u in unlistable] == [
        (2, "the message isn't a literal"),
        (3, "'no rule here' doesn't start with '<CR number>: '"),
        (4, "the message isn't a literal"),
    ]


def test_an_empty_folder_has_no_gaps(tmp_path: Path) -> None:
    assert find_gaps(tmp_path) == ([], [])


def test_rules_sort_numerically() -> None:
    rules = ["104", "103.10", "613.7m", "103.5", "103.5c", "104.3a", "103"]
    assert sorted(rules, key=rule_sort_key) == [
        "103", "103.5", "103.5c", "103.10", "104", "104.3a", "613.7m",
    ]  # fmt: skip


def test_main_prints_the_report_and_fails_on_unlistable_gaps(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tmp_path, "mod.py", SOURCE)
    assert gaps_tool.main([str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "NotImplementedRule gaps: 3"
    assert "613.7m    ordering simultaneous timestamps" in out
    write(tmp_path, "bad.py", "raise NotImplementedRule(x)\n")
    assert gaps_tool.main([str(tmp_path)]) == 1
    assert "Gaps that can't be listed: 1" in capsys.readouterr().out


def test_the_engine_gaps_are_all_listable_and_include_601_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert gaps_tool.main([]) == 0
    out = capsys.readouterr().out
    assert "601.2     casting a spell" in out
    assert "src/resolve/engine/priority.py:" in out


def test_reads_sources_the_way_python_does(tmp_path: Path) -> None:
    """Some Windows editors save Python files as UTF-8 with a byte order mark, and Python runs
    them; so does the scan. A ``coding`` declaration (PEP 263) is honored too."""
    raise_gap = 'raise NotImplementedRule("104.3a: conceding — any time")\n'
    (tmp_path / "bom.py").write_bytes(codecs.BOM_UTF8 + raise_gap.encode("utf-8"))
    (tmp_path / "latin.py").write_bytes(
        b"# -*- coding: latin-1 -*-\n"
        + 'raise NotImplementedRule("103.5: Lûm")\n'.encode("latin-1")
    )
    gaps, unlistable = find_gaps(tmp_path)
    assert unlistable == []
    assert [(gap.rule, gap.what, gap.path.name) for gap in gaps] == [
        ("103.5", "Lûm", "latin.py"),
        ("104.3a", "conceding — any time", "bom.py"),
    ]
