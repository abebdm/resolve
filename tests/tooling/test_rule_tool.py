"""Tests for tools/rule.py, mostly on a small hand-made rules file (one of each edge case)."""

from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from resolve.data.rules_text import PINNED_RULES_FILE, parse_glossary, parse_rules, rule_blocks
from tools import rule as tool

# The shape of the real file: a contents list naming the sections, the glossary and the credits;
# chapter headings; lines holding a single space between rules; examples; an unnumbered
# paragraph continuing a subrule; letters skipping l and o; a two-letter subrule; a glossary
# whose entries cite rules; credits.
RULES = """\
Magic: The Gathering Comprehensive Rules

Contents

1. Game Concepts
100. General
704. State-Based Actions
Glossary
Credits

1. Game Concepts

100. General

100.1. These rules apply to any game. See rule 704, "State-Based Actions."

100.2. A player's deck is their library.

7. Additional Rules

704. State-Based Actions

704.1. State-based actions are game actions that happen automatically whenever certain conditions are met. This first line is long enough to be truncated in an outline.

704.2. State-based actions are checked whenever a player would receive priority.
Example: A creature with 0 toughness is put into its owner's graveyard. See rule 100.2.

704.5. The state-based actions are as follows:

704.5a If a player has 0 or less life, that player loses the game.

704.5k If two or more legendary permanents have the same name, their controller chooses one of them.
This paragraph continues 704.5k, as some do after a list (see rule 702.9b).

704.5m If an Aura is attached to an illegal object, it goes to its owner's graveyard.

704.5z If a permanent has more than one Role, all but the newest go to the graveyard.

704.5aa If a player has no speed, that player's speed becomes 1. See rule 702.179 and section 1.

704.6. Some variant games include additional state-based actions. See rule 704.5a/b.

704.6a In a Two-Headed Giant game, a team with 0 or less life loses the game.

Glossary

Mana
The primary resource in the game. See rule 106.

Mana Value
The total amount of mana in a mana cost, regardless of color. See rule 202.3.

State-Based Actions
Game actions that happen automatically. See rule 704.

Credits

Magic: The Gathering Original Game Design: Richard Garfield
"""  # noqa: E501 (704.1's first line is long on purpose, to be truncated in the outline)


@pytest.fixture
def rules_file(tmp_path: Path) -> Path:
    path = tmp_path / "rules.txt"
    path.write_text(RULES, encoding="utf-8", newline="\n")
    return path


def run(*args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        status = tool.main(list(args))
    return status, out.getvalue(), err.getvalue()


def test_rule_prints_all_subrules_with_examples_and_continuations(rules_file: Path) -> None:
    status, out, err = run("704.5", "--rules", str(rules_file))
    assert (status, err) == (0, "")
    assert out == (
        "704.5. The state-based actions are as follows:\n"
        "\n"
        "704.5a If a player has 0 or less life, that player loses the game.\n"
        "\n"
        "704.5k If two or more legendary permanents have the same name, their controller chooses"
        " one of them.\n"
        "This paragraph continues 704.5k, as some do after a list (see rule 702.9b).\n"
        "\n"
        "704.5m If an Aura is attached to an illegal object, it goes to its owner's graveyard.\n"
        "\n"
        "704.5z If a permanent has more than one Role, all but the newest go to the graveyard.\n"
        "\n"
        "704.5aa If a player has no speed, that player's speed becomes 1. See rule 702.179 and"
        " section 1.\n"
        "\n"
        "See also: 1, 702.9b, 702.179\n"
    )


def test_two_letter_subrule_prints_alone(rules_file: Path) -> None:
    status, out, _ = run("704.5aa", "--rules", str(rules_file))
    assert status == 0
    assert out == (
        "704.5aa If a player has no speed, that player's speed becomes 1. See rule 702.179 and"
        " section 1.\n\nSee also: 1, 702.179\n"
    )


def test_one_letter_subrule_does_not_take_its_two_letter_neighbours(rules_file: Path) -> None:
    """704.5a is a prefix of 704.5aa as text, but 704.5aa is not a subrule of 704.5a."""
    _, out, _ = run("704.5a", "--rules", str(rules_file))
    assert out.startswith("704.5a If a player has 0 or less life")
    assert "704.5aa" not in out


def test_rule_with_an_example_prints_it(rules_file: Path) -> None:
    _, out, _ = run("704.2", "--rules", str(rules_file))
    assert out == (
        "704.2. State-based actions are checked whenever a player would receive priority.\n"
        "Example: A creature with 0 toughness is put into its owner's graveyard. See rule 100.2.\n"
        "\n"
        "See also: 100.2\n"
    )


def test_rule_numbers_print_in_the_order_given_with_one_see_also_line(rules_file: Path) -> None:
    status, out, _ = run("704.6", "100.1", "--rules", str(rules_file))
    assert status == 0
    assert out == (
        "704.6. Some variant games include additional state-based actions. See rule 704.5a/b.\n"
        "\n"
        "704.6a In a Two-Headed Giant game, a team with 0 or less life loses the game.\n"
        "\n"
        '100.1. These rules apply to any game. See rule 704, "State-Based Actions."\n'
        "\n"
        "See also: 704, 704.5a, 704.5b\n"
    )


def test_see_also_leaves_out_what_was_printed(rules_file: Path) -> None:
    """704.2 cites 100.2; printing both leaves nothing else to look up."""
    _, out, _ = run("704.2", "100.2", "--rules", str(rules_file))
    assert out.endswith("\nSee also: (none)\n")


def test_section_prints_an_outline_not_the_full_text(rules_file: Path) -> None:
    """The outline's own citations (704.5a/b) are in the section, so "See also" leaves them out."""
    status, out, _ = run("704", "--rules", str(rules_file))
    assert status == 0
    first = (
        "704.1. State-based actions are game actions that happen automatically whenever certain"
        " conditions a"
    )
    assert len(first) == tool.OUTLINE_WIDTH - 1
    assert out == (
        "704. State-Based Actions\n"
        "\n"
        f"{first}…\n"
        "704.2. State-based actions are checked whenever a player would receive priority.\n"
        "704.5. The state-based actions are as follows:  (+5 subrules)\n"
        "704.6. Some variant games include additional state-based actions. See rule 704.5a/b."
        "  (+1 subrules)\n"
        "\n"
        "See also: (none)\n"
    )


def test_section_heading_comes_from_the_body_not_the_contents_list(rules_file: Path) -> None:
    _, out, _ = run("100", "--rules", str(rules_file))
    assert out.startswith("100. General\n\n100.1. These rules apply")
    assert out.endswith("\nSee also: 704\n")


def test_unknown_rule_exits_1_and_names_the_nearest_numbers(rules_file: Path) -> None:
    status, out, err = run("704.5b", "--rules", str(rules_file))
    assert (status, out) == (1, "")
    assert err == (
        "error: no rule 704.5b; nearest existing numbers: 704.2, 704.5, 704.5a, 704.5k, 704.5m,"
        " 704.5z\n"
    )


def test_unknown_rule_among_known_ones_prints_the_known_and_exits_1(rules_file: Path) -> None:
    status, out, err = run("704.9", "704.6a", "--rules", str(rules_file))
    assert status == 1
    assert out.startswith("704.6a In a Two-Headed Giant game")
    assert err == "error: no rule 704.9; nearest existing numbers: 704.5aa, 704.6, 704.6a\n"


@pytest.mark.parametrize("bad", ["70", "704.5abc", "rule", "704.05"])
def test_text_that_is_not_a_rule_number_exits_1(rules_file: Path, bad: str) -> None:
    status, out, err = run(bad, "--rules", str(rules_file))
    assert (status, out) == (1, "")
    assert err.startswith(f"error: not a rule number: {bad!r}")


def test_glossary_hit_ignores_case_and_ends_with_see_also(rules_file: Path) -> None:
    status, out, _ = run("--glossary", "mana value", "--rules", str(rules_file))
    assert status == 0
    assert out == (
        "Mana Value\nThe total amount of mana in a mana cost, regardless of color. See rule 202.3."
        "\n\nSee also: 202.3\n"
    )


def test_glossary_term_matches_exactly_not_by_prefix(rules_file: Path) -> None:
    _, out, _ = run("--glossary", "Mana", "--rules", str(rules_file))
    assert out == "Mana\nThe primary resource in the game. See rule 106.\n\nSee also: 106\n"


def test_glossary_miss_exits_1_and_lists_the_closest_entries(rules_file: Path) -> None:
    status, out, err = run("--glossary", "mana valeu", "--rules", str(rules_file))
    assert (status, out) == (1, "")
    assert err == "error: no glossary entry 'mana valeu'; closest entries: Mana Value; Mana\n"


def test_glossary_miss_with_nothing_close(rules_file: Path) -> None:
    status, _, err = run("--glossary", "zzzz", "--rules", str(rules_file))
    assert status == 1
    assert err == "error: no glossary entry 'zzzz'; closest entries: (none)\n"


def test_no_arguments_is_a_usage_error(rules_file: Path) -> None:
    with pytest.raises(SystemExit) as raised, redirect_stderr(io.StringIO()):
        tool.main(["--rules", str(rules_file)])
    assert raised.value.code == 2


def test_unreadable_rules_file_exits_1(tmp_path: Path) -> None:
    status, out, err = run("704.5", "--rules", str(tmp_path / "missing.txt"))
    assert (status, out) == (1, "")
    assert err.startswith("error: ")


def test_windows_files_read_the_same(tmp_path: Path) -> None:
    """A copy saved on Windows may have a byte order mark and CRLF line endings."""
    path = tmp_path / "rules-bom.txt"
    path.write_bytes(b"\xef\xbb\xbf" + RULES.replace("\n", "\r\n").encode("utf-8"))
    status, out, _ = run("704.5aa", "--rules", str(path))
    assert status == 0
    assert out.startswith("704.5aa If a player has no speed")


def test_rule_blocks_keep_each_line_and_parse_rules_drops_the_number() -> None:
    blocks = rule_blocks(RULES)
    assert blocks["704.5k"] == [
        "704.5k If two or more legendary permanents have the same name, their controller chooses"
        " one of them.",
        "This paragraph continues 704.5k, as some do after a list (see rule 702.9b).",
    ]
    assert blocks["704"] == ["704. State-Based Actions"]
    assert "7" not in blocks, "chapter headings are not rules"
    assert parse_rules(RULES)["704.2"] == (
        "State-based actions are checked whenever a player would receive priority.\n"
        "Example: A creature with 0 toughness is put into its owner's graveyard. See rule 100.2."
    )


def test_parse_glossary_reads_the_body_glossary_up_to_the_credits() -> None:
    assert parse_glossary(RULES) == {
        "Mana": "The primary resource in the game. See rule 106.",
        "Mana Value": (
            "The total amount of mana in a mana cost, regardless of color. See rule 202.3."
        ),
        "State-Based Actions": "Game actions that happen automatically. See rule 704.",
    }
    assert parse_glossary("100.1. No glossary here.\n") == {}


def test_default_file_is_the_pinned_rules() -> None:
    """The real pinned CR: two subrules quoted from docs/rules/MagicCompRules-20260925.txt."""
    status, out, _ = run("704.5aa", "702.186b")
    assert status == 0
    assert out == (
        "704.5aa If a player controls a permanent with start your engines! and that player has no"
        " speed, that player’s speed becomes 1. See rule 702.179, “Start Your Engines!”\n"  # noqa: RUF001
        "\n"
        "702.186b “∞ — [Ability]” means “As long as this permanent is harnessed, it has"
        " [ability].” See rule 701.64, “Harness.”\n"
        "\n"
        "See also: 701.64, 702.179\n"
    )
    assert PINNED_RULES_FILE.name == "MagicCompRules-20260925.txt"


def test_pinned_glossary_entry() -> None:
    status, out, _ = run("--glossary", "Mana Value")
    assert status == 0
    assert out == (
        "Mana Value\n"
        "The total amount of mana in a mana cost, regardless of color. See rule 202.3.\n"
        "\n"
        "See also: 202.3\n"
    )
