"""Tests for tools/rules_diff.py, on small hand-made rules files (one of each kind of change)."""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from resolve.citations import cited_rules, parent_rule, rule_sort_key
from resolve.data.rules_text import parse_rules, word_diff
from tools import rules_diff as tool
from tools.rules_diff import diff_rules, find_citations

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
    cited = find_citations(tool.scan_files([tmp_path]), relative_to=tmp_path)
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
    assert text.count("cited in code/tests at ") == 3  # 100.3, 100.4 and 100.5; 100.1 is unchanged
    assert "100.2:" in text
    assert "(not cited)" in text, "changed rule 100.2 is cited nowhere"
    assert "100.6: A brand new rule." in text


def test_a_missing_rules_file_is_an_error(tmp_path: Path) -> None:
    status, _ = run(str(tmp_path / "nope.txt"), str(tmp_path / "nope2.txt"))
    assert status == 1


# A list of subrules with a new one inserted in the middle: 100.7b is new and the old b and c
# become c and d, so every later letter shifts (the commonest renumbering in a real update).
LIST_OLD = """\
100. General

100.7. Things that happen.

100.7a A player draws a card at the start of the turn.

100.7b A player with no cards in their library loses the game when they next draw.

100.7c A creature with toughness 0 is put into its owner's graveyard.

100.7z The last letter of a list.

100.7aa A rule after z, which has two letters.
"""

LIST_NEW = """\
100. General

100.7. Things that happen.

100.7a A player draws a card at the start of the turn.

100.7b A player who has gained life this turn may cast an instant.

100.7c A player with no cards in their library loses the game when they next draw.

100.7d A creature with toughness 0 is put into its owner's graveyard.

100.7z The last letter of a list.

100.7aa A rule after z, which has two letters.
"""


def test_a_subrule_inserted_mid_list_renumbers_the_later_ones_and_adds_the_new_one() -> None:
    diff = diff_rules(parse_rules(LIST_OLD), parse_rules(LIST_NEW))
    assert [(m.old_number, m.new_number) for m in diff.renumbered] == [
        ("100.7b", "100.7c"),
        ("100.7c", "100.7d"),
    ]
    assert diff.changed == ()
    assert diff.removed == ()
    assert [n for n, _ in diff.added] == ["100.7b"]


def test_two_letter_subrules_are_parsed_cited_and_ordered() -> None:
    assert parse_rules(LIST_OLD)["100.7aa"].startswith("A rule after z")
    assert cited_rules("see 704.5aa, not 704.5a") == ["704.5aa", "704.5a"]
    assert cited_rules("the 704.5abc token") == []
    assert sorted(["704.5aa", "704.5z", "704.5a"], key=rule_sort_key) == [
        "704.5a",
        "704.5z",
        "704.5aa",
    ]
    assert parent_rule("702.16e") == "702.16" and parent_rule("704.5aa") == "704.5"
    assert parent_rule("702.16") is None


def test_a_change_to_a_two_letter_subrule_is_reported() -> None:
    new = LIST_OLD.replace("which has two letters", "which still has two letters")
    diff = diff_rules(parse_rules(LIST_OLD), parse_rules(new))
    assert [c.number for c in diff.changed] == ["100.7aa"]


def test_a_slash_citation_cites_each_rule_and_a_repeat_on_a_line_counts_once(
    tmp_path: Path,
) -> None:
    assert cited_rules("704.5a/b and 704.5a/b/aa") == [
        "704.5a",
        "704.5b",
        "704.5a",
        "704.5b",
        "704.5aa",
    ]
    (tmp_path / "a.py").write_text("# 704.5a, 704.5a/b\n", encoding="utf-8")
    cited = find_citations([tmp_path / "a.py"], relative_to=tmp_path)
    assert cited == {"704.5a": ["a.py:1"], "704.5b": ["a.py:1"]}


CONTINUATION_OLD = """\
100.1. First rule.
It continues in a paragraph without a number.

2. Parts of a Card

100.2. Second rule.
Example: An example.

A paragraph after the example.

Glossary

Absorb A keyword.
"""


def test_unnumbered_continuation_paragraphs_belong_to_the_rule_before_them() -> None:
    rules = parse_rules(CONTINUATION_OLD)
    assert rules["100.1"] == "First rule.\nIt continues in a paragraph without a number."
    assert rules["100.2"] == "Second rule.\nExample: An example.\nA paragraph after the example."
    assert "2" not in rules and all("Absorb" not in text for text in rules.values())


def test_a_change_in_a_continuation_paragraph_is_reported() -> None:
    new = CONTINUATION_OLD.replace("without a number", "with no number at all")
    diff = diff_rules(parse_rules(CONTINUATION_OLD), parse_rules(new))
    assert [c.number for c in diff.changed] == ["100.1"]
    assert word_diff(diff.changed[0].old, diff.changed[0].new) == (
        "First rule. It continues in a paragraph [-without a number.-] {+with no number at all.+}"
    )


def test_the_report_lists_doc_citations_and_parent_citations_separately(tmp_path: Path) -> None:
    old, new = tmp_path / "old.txt", tmp_path / "new.txt"
    old.write_text(LIST_OLD, encoding="utf-8")
    new.write_text(LIST_NEW.replace("start of the turn", "start of their turn"), encoding="utf-8")
    code = tmp_path / "src"
    docs = tmp_path / "docs"
    code.mkdir()
    docs.mkdir()
    (docs / "rules").mkdir()
    (code / "engine.py").write_text("# 100.7a changed, 100.7 the parent\n", encoding="utf-8")
    (docs / "notes.md").write_text("Cites 100.7b and 100.7a/b.\n", encoding="utf-8")
    (docs / "rules" / "readme.md").write_text("100.7b is in a skipped folder\n", encoding="utf-8")
    status, text = run(str(old), str(new), "--scan", str(code), "--scan", str(docs))
    assert status == 0
    assert "100.7a: A player draws a card at the start of [-the-] {+their+} turn." in text
    assert "cited in code/tests at " in text and "engine.py:1" in text
    assert "cited in docs at " in text and "notes.md:1" in text
    assert "readme.md" not in text
    # 100.7 is cited in code, and is the parent of the flagged 100.7a, 100.7b and 100.7c.
    parents = text.split("== Citations of the parent rule", 1)[1]
    assert "100.7 (parent of 100.7a, 100.7b, 100.7c" in parents
    assert parents.count("engine.py:1") == 1


def test_a_rules_file_that_is_not_utf8_is_an_error_that_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "bad.txt"
    bad.write_bytes(b"100.1. caf\xe9 and \x93quotes\x94\n")  # cp1252, not UTF-8
    good = tmp_path / "good.txt"
    good.write_text("100.1. text\n", encoding="utf-8")
    status, _ = run(str(bad), str(good))
    assert status == 1
    assert "UTF-8" in capsys.readouterr().err
