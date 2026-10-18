"""Comprehensive Rules citations (CLAUDE.md rule 2).

A citation names one section, rule or subrule of the pinned CR: ``"103"``, ``"103.1"`` or
``"701.24a"``. Events, decision requests and ``NotImplementedRule`` messages carry citations in
this form. ``tests/tooling/test_rule_citations.py`` checks that every citation in the engine
exists in the pinned rules file.
"""

from __future__ import annotations

import re

RULE_REFERENCE = re.compile(r"[1-9]\d{2}(?:\.[1-9]\d*[a-z]?)?")


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
