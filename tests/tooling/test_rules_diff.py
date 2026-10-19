"""Tests for tools/rules_diff.py, on small hand-made rules files (one of each kind of change)."""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from pathlib import Path

from tools import rules_diff as tool
from tools.rules_diff import diff_rules, find_citations, parse_rules, rule_sort_key, word_diff

OLD = """\
Contents
1. Game Concepts
100. General

1. Game Concepts

100. General

100.1. These rules apply to any game.

100.2. Each player has a library.
Example: A player's library is their deck.

100.3. A creature with lethal damage is destroyed by the state-based action.

100.4. This rule is going away entirely.

100.5. A player with zero or less life loses the game.

101.1a Subrule text that stays.

Glossary

Absorb 702.64a
"""

NEW = """\
Contents
1. Game Concepts

100. General

100.1. These rules apply to any game.

100.2. Each player has a library.
Example: A player's library is their hand.

100.3. A creature with lethal damage is destroyed by a state-based action.

100.4a. A player with zero or less life loses the game.

100.6. A brand new rule.

101.1a Subrule text that stays.
"""


def test_parse_rules_reads_sections_rules_subrules_and_examples() -> None:
    rules = parse_rules(OLD)
    assert rules["100"] == "General"
    assert rules["100.1"] == "These rules apply to any game."
    assert rules["100.2"].endswith("\nExample: A player's library is their deck.")
    assert rules["101.1a"] == "Subrule text that stays."
    assert "702.64a" not in rules
    assert "1" not in rules, "one-digit contents entries are not rules"


def test_parse_rules_accepts_crlf_line_endings() -> None:
    assert parse_rules(OLD.replace("\n", "\r\n")) == parse_rules(OLD)


def test_word_diff_marks_removed_and_added_words() -> None:
    assert word_diff("a b c d", "a x c d e") == "a [-b-] {+x+} c d {+e+}"
    assert word_diff("same text", "same  text") == "same text"


def test_rule_sort_key_orders_numerically() -> None:
    rules = ["104.3a", "103.10", "103.5", "104", "103.5a"]
    assert sorted(rules, key=rule_sort_key) == ["103.5", "103.5a", "103.10", "104", "104.3a"]


def test_diff_reports_changed_renumbered_removed_and_added_rules() -> None:
    diff = diff_rules(parse_rules(OLD), parse_rules(NEW))
    assert [c.number for c in diff.changed] == ["100.2", "100.3"]
    assert word_diff(diff.changed[1].old, diff.changed[1].new) == (
        "A creature with lethal damage is destroyed by [-the-] {+a+} state-based action."
    )
    assert [(m.old_number, m.new_number) for m in diff.renumbered] == [("100.5", "100.4a")]
    assert diff.renumbered[0].similarity == 1.0
    assert [number for number, _ in diff.removed] == ["100.4"]
    assert [number for number, _ in diff.added] == ["100.6"]


def test_unchanged_rules_and_whitespace_only_changes_are_not_reported() -> None:
    old = {"100.1": "Same   text."}
    new = {"100.1": "Same text."}
    diff = diff_rules(old, new)
    assert (diff.changed, diff.renumbered, diff.removed, diff.added) == ((), (), (), ())


def test_a_dissimilar_removed_and_added_rule_are_not_matched_as_renumbered() -> None:
    diff = diff_rules({"100.1": "one two three four"}, {"100.2": "five six seven eight"})
    assert diff.renumbered == ()
    assert [n for n, _ in diff.removed] == ["100.1"]
    assert [n for n, _ in diff.added] == ["100.2"]


def test_each_rule_is_matched_to_only_one_renumbered_rule() -> None:
    text = "Identical text of a rule that appears twice in the new file."
    diff = diff_rules({"100.1": text}, {"100.2": text, "100.3": text})
    assert [(m.old_number, m.new_number) for m in diff.renumbered] == [("100.1", "100.2")]
    assert [n for n, _ in diff.added] == ["100.3"]


def test_a_threshold_changes_what_counts_as_renumbered() -> None:
    old = {"100.1": "a b c d e f g h i j"}
    new = {"100.2": "a b c d e f g x y z"}
    assert diff_rules(old, new, threshold=0.9).renumbered == ()
    assert len(diff_rules(old, new, threshold=0.5).renumbered) == 1


def test_find_citations_lists_each_place_a_rule_is_cited(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text('x = 1\n# 100.3 and 100.5\n"""See 100.3."""\n', encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.py").write_text("y = 'version 3.12'  # 100.5a\n", encoding="utf-8")
    cited = find_citations(tool.python_files(tmp_path), relative_to=tmp_path)
    assert cited == {
        "100.3": ["a.py:2", "a.py:3"],
        "100.5": ["a.py:2"],
        "100.5a": ["sub/b.py:1"],
    }


def run(*args: str) -> tuple[int, str]:
    output = io.StringIO()
    with redirect_stdout(output):
        status = tool.main(list(args))
    return status, output.getvalue()


def test_the_report_lists_citations_of_changed_removed_and_renumbered_rules(
    tmp_path: Path,
) -> None:
    old, new = tmp_path / "old.txt", tmp_path / "new.txt"
    old.write_text(OLD, encoding="utf-8")
    new.write_text("﻿" + NEW, encoding="utf-8")  # a byte order mark is accepted
    code = tmp_path / "code"
    code.mkdir()
    (code / "engine.py").write_text(
        "# 100.3 changed\n# 100.4 removed\n# 100.5 renumbered\n# 100.1 unchanged\n",
        encoding="utf-8",
    )
    status, text = run(str(old), str(new), "--scan", str(code))
    assert status == 0
    assert text.startswith("changed: 2, renumbered: 1, removed: 1, added: 1")
    assert "100.3: A creature with lethal damage is destroyed by [-the-] {+a+} state-based" in text
    assert "100.5 -> 100.4a (similarity 1.00)" in text
    assert text.count("cited at ") == 3  # 100.3, 100.4 and 100.5; 100.1 is unchanged
    assert "100.2:" in text
    assert "(not cited)" in text, "changed rule 100.2 is cited nowhere"
    assert "100.6: A brand new rule." in text


def test_a_missing_rules_file_is_an_error(tmp_path: Path) -> None:
    status, _ = run(str(tmp_path / "nope.txt"), str(tmp_path / "nope2.txt"))
    assert status == 1
