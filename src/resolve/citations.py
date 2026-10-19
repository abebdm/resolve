"""Comprehensive Rules citations (CLAUDE.md rule 2).

A citation names one section, rule or subrule of the pinned CR: ``"103"``, ``"103.1"`` or
``"701.24a"``. Events, decision requests and ``NotImplementedRule`` messages carry citations in
this form. ``tests/tooling/test_rule_citations.py`` checks that every citation in the engine
exists in the pinned rules file.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterator

# A subrule's letters are one or two: 704.5z is followed by 704.5aa in the CR.
RULE_REFERENCE = re.compile(r"[1-9]\d{2}(?:\.[1-9]\d*[a-z]{0,2})?")


# One rule line of the CR text: "103. Starting the Game", "103.1. At the start...", "103.1a In a
# game..." (the number, an optional period, then the text).
RULE_LINE = re.compile(r"^(\d{3}(?:\.\d+[a-z]{0,2})?)\.?\s+(\S.*)$")

# Dotted CR numbers in prose: three digits, a dot, a number, up to two letters ("613.7m",
# "704.5aa"), optionally followed by more letters to share the number ("704.5a/b"). The lookaheads
# reject a longer token ("704.5abc") and a version number ("1.1.390").
_CITATION = re.compile(
    r"(?<![\w.])([1-9]\d{2}\.\d+)([a-z]{0,2})(?![a-z])((?:/[a-z]{1,2}(?![a-z]))*)(?![\w.]*\d)"
)
_RULE_PARTS = re.compile(r"(\d+)(?:\.(\d+)([a-z]*))?")


def cited_rules(text: str) -> list[str]:
    """Every dotted CR number cited in ``text``, in order (repeats kept).

    ``"704.5a/b"`` cites 704.5a and 704.5b. Used on comments, docstrings and documents; the
    section-only form ``"103"`` is too common as a plain number to find in prose.
    """
    found: list[str] = []
    for match in _CITATION.finditer(text):
        base, letters, more = match.groups()
        found.append(base + letters)
        found += [base + extra for extra in more.split("/")[1:]]
    return found


def rule_sort_key(rule: str) -> tuple[int, int, int, str]:
    """Sort CR numbers in rule order: 702.9 < 702.10 < 703 < 704.5a, and 704.5z < 704.5aa."""
    match = _RULE_PARTS.fullmatch(rule)
    if match is None:
        return (sys.maxsize, 0, 0, rule)
    section, number, letters = match.groups()
    return (int(section), -1 if number is None else int(number), len(letters or ""), letters or "")


def parent_rule(rule: str) -> str | None:
    """The rule a subrule belongs to (``"702.16e"`` -> ``"702.16"``), or ``None`` if it is one."""
    base = rule.rstrip("abcdefghijklmnopqrstuvwxyz")
    return base if base != rule else None


def rule_lines(text: str) -> Iterator[tuple[str, str]]:
    """The (number, rest of the line) of each line of ``text`` that starts a rule."""
    for line in text.splitlines():
        match = RULE_LINE.match(line.strip())
        if match:
            yield str(match.group(1)), str(match.group(2))


def is_rule_reference(text: str) -> bool:
    """Whether ``text`` is exactly one CR citation, such as ``"613.7m"``."""
    return RULE_REFERENCE.fullmatch(text) is not None


def check_rules(rules: tuple[str, ...]) -> None:
    """Raise ``ValueError`` unless ``rules`` is a non-empty tuple of CR citations."""
    if not isinstance(rules, tuple) or not rules:  # pyright: ignore[reportUnnecessaryIsInstance]
        raise ValueError(f"rules must be a non-empty tuple of CR citations, got {rules!r}")
    for rule in rules:
        if not isinstance(rule, str) or not is_rule_reference(rule):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValueError(f"not a CR citation: {rule!r}")
