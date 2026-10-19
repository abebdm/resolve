"""Print Comprehensive Rules text by rule number, so nobody has to open the whole file.

Usage (PowerShell or any shell)::

    uv run python tools/rule.py 704.5               # a rule with all its subrules
    uv run python tools/rule.py 704.5aa             # one subrule
    uv run python tools/rule.py 702.19 613.7        # several, in the order given
    uv run python tools/rule.py 704                 # a section: an outline of its rules
    uv run python tools/rule.py --glossary "mana value"
    uv run python tools/rule.py 704.5 --rules docs/rules/MagicCompRules-OTHER.txt

A rule prints with its subrules (704.5 prints 704.5a ... 704.5aa), and each with its examples
and continuation paragraphs, line for line as in the file. A section number alone prints the
section's heading and an outline: each rule's number and first line, truncated, and how many
subrules it has; a whole section can be thousands of lines. A glossary term is matched ignoring
case; with no exact match the closest terms are listed.

After the text, a "See also" line lists the other rule numbers the printed text cites (for an
outline, the truncated lines shown), in CR order: dotted numbers (``701.64``, ``704.6b``) and
sections named as "rule 509" or "section 4".

The default file is the pinned CR (``PINNED_RULES_FILE``). The exit status is 1 if a rule number
or glossary term isn't found (the nearest existing numbers or closest terms are named) or the
file can't be read; anything found is still printed.
"""

from __future__ import annotations

import argparse
import bisect
import difflib
import io
import re
import sys
from collections.abc import Sequence
from pathlib import Path

from resolve.citations import cited_rules, is_rule_reference, rule_sort_key
from resolve.data.rules_text import PINNED_RULES_FILE, parse_glossary, read_rules_text, rule_blocks

OUTLINE_WIDTH = 100
NEAREST = 3  # existing numbers named on each side of an unknown one
CLOSEST_TERMS = 5

# "rule 509", "rules 509", "section 4" (a chapter of the CR) in the text. Dotted numbers are left
# to ``cited_rules``; the lookahead rejects "rule 702.19".
_SECTION_CITATION = re.compile(r"\b(?:rules?\s+(\d{3})|section\s+(\d))(?!\d|\.\d)")


def rules_under(blocks: dict[str, list[str]], number: str) -> list[str]:
    """``number`` and its subrules, in file order: 704.5 gives 704.5, 704.5a, ..., 704.5aa.

    A subrule has none: 704.5a gives only 704.5a, not 704.5aa.
    """
    if number[-1].isalpha():
        return [number]
    return [
        n for n in blocks if n == number or (n.startswith(number) and n[len(number) :].isalpha())
    ]


def format_rules(blocks: dict[str, list[str]], numbers: list[str]) -> str:
    """The full text of each rule, a blank line between rules (as in the file)."""
    return "\n\n".join("\n".join(blocks[n]) for n in numbers)


def format_outline(blocks: dict[str, list[str]], section: str) -> str:
    """The section's heading, then each of its rules' number and first line, truncated."""
    lines = [blocks[section][0], ""]
    rules = [n for n in blocks if n.startswith(section + ".") and not n[-1].isalpha()]
    for rule in rules:
        first = _shorten(blocks[rule][0])
        subrules = len(rules_under(blocks, rule)) - 1
        lines.append(f"{first}  (+{subrules} subrules)" if subrules else first)
    if not rules:
        lines.append("(no rules)")
    return "\n".join(lines)


def _shorten(line: str) -> str:
    return line if len(line) <= OUTLINE_WIDTH else line[: OUTLINE_WIDTH - 1] + "…"


def see_also(text: str, printed: Sequence[str], sections: Sequence[str] = ()) -> list[str]:
    """The rule numbers ``text`` cites, once each, in CR order, leaving out what was printed.

    ``printed`` are the rules shown in full; ``sections`` are those shown as an outline, which
    cover every number in them (``704.5b`` is in the outline of 704 even if it doesn't exist).
    """
    found = cited_rules(text)
    for match in _SECTION_CITATION.finditer(text):
        found.append(match.group(1) or match.group(2))
    shown = set(printed)
    shown.update(sections)
    return sorted({n for n in found if n not in shown and n[:3] not in sections}, key=rule_sort_key)


def nearest_numbers(blocks: dict[str, list[str]], number: str) -> list[str]:
    """The existing numbers just before and after ``number`` in CR order."""
    ordered = sorted(blocks, key=rule_sort_key)
    keys = [rule_sort_key(n) for n in ordered]
    at = bisect.bisect_left(keys, rule_sort_key(number))
    return ordered[max(0, at - NEAREST) : at + NEAREST]


def closest_terms(glossary: dict[str, str], term: str) -> list[str]:
    """Glossary terms that contain ``term`` (ignoring case), then the most alike by spelling."""
    wanted = term.casefold()
    by_folded = {t.casefold(): t for t in glossary}
    containing = [t for t in glossary if wanted in t.casefold()]
    alike = difflib.get_close_matches(wanted, list(by_folded), n=CLOSEST_TERMS, cutoff=0.5)
    found = dict.fromkeys(containing + [by_folded[t] for t in alike])
    return list(found)[:CLOSEST_TERMS]


def look_up_rules(blocks: dict[str, list[str]], numbers: Sequence[str]) -> tuple[str, list[str]]:
    """The output for ``numbers``, and an error message for each one that isn't found."""
    parts: list[str] = []
    printed: list[str] = []
    sections: list[str] = []
    errors: list[str] = []
    for number in numbers:
        if not is_rule_reference(number):
            errors.append(
                f"not a rule number: {number!r} (expected a form like 704, 704.5, 704.5a)"
            )
            continue
        if number not in blocks:
            near = ", ".join(nearest_numbers(blocks, number))
            errors.append(f"no rule {number}; nearest existing numbers: {near}")
            continue
        if "." in number:
            shown = rules_under(blocks, number)
            text = format_rules(blocks, shown)
        else:
            shown = []
            sections.append(number)
            text = format_outline(blocks, number)
        parts.append(text)
        printed += shown
    output = "\n\n".join(parts)
    if parts:
        also = see_also(output, printed, sections)
        output += "\n\nSee also: " + (", ".join(also) if also else "(none)") + "\n"
    return output, errors


def look_up_term(glossary: dict[str, str], term: str) -> tuple[str, list[str]]:
    """The glossary entry for ``term`` and its "See also" line, or an error naming close terms."""
    exact = [t for t in glossary if t.casefold() == term.strip().casefold()]
    if not exact:
        close = closest_terms(glossary, term.strip())
        listed = "; ".join(close) if close else "(none)"
        return "", [f"no glossary entry {term!r}; closest entries: {listed}"]
    found = exact[0]
    text = found + "\n" + glossary[found]
    also = see_also(glossary[found], [])
    return text + "\n\nSee also: " + (", ".join(also) if also else "(none)") + "\n", []


def main(argv: Sequence[str] | None = None) -> int:
    """Print the rules or glossary entry asked for; 1 if anything isn't found or can't be read."""
    parser = argparse.ArgumentParser(
        description="Print Comprehensive Rules text by rule number, or a glossary entry."
    )
    parser.add_argument("numbers", nargs="*", help="rule numbers: 704, 704.5, 704.5aa")
    parser.add_argument("--glossary", metavar="TERM", help="print the glossary entry for TERM")
    parser.add_argument(
        "--rules",
        type=Path,
        default=PINNED_RULES_FILE,
        help="the rules file to read (default: the pinned CR)",
    )
    args = parser.parse_args(argv)
    if not args.numbers and args.glossary is None:
        parser.error("give one or more rule numbers, or --glossary TERM")
    try:
        text = read_rules_text(args.rules)
    except (OSError, UnicodeDecodeError) as error:
        print(
            f"error: {error}\n(the rules file must be UTF-8; re-save it as UTF-8 if it isn't)",
            file=sys.stderr,
        )
        return 1
    outputs: list[str] = []
    errors: list[str] = []
    if args.numbers:
        output, errors = look_up_rules(rule_blocks(text), args.numbers)
        outputs.append(output)
    if args.glossary is not None:
        output, more = look_up_term(parse_glossary(text), args.glossary)
        outputs.append(output)
        errors += more
    sys.stdout.write("\n".join(o for o in outputs if o))
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    # Redirected output would use the locale's code page, cp1252 on Windows, which can't encode
    # every character of the rules; write UTF-8 everywhere (CLAUDE.md, Platform).
    stdout = sys.stdout
    if isinstance(stdout, io.TextIOWrapper):
        stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
