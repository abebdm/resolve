"""Reading Comprehensive Rules text files, and comparing text word by word (for the update tools).

``tools/rules_diff.py`` and ``tools/card_diff.py`` use these; the engine doesn't.
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path

from resolve.citations import RULE_LINE

# A chapter heading in the body and the contents list: "2. Parts of a Card".
_CHAPTER = re.compile(r"^\d\.\s")


def parse_rules(text: str) -> dict[str, str]:
    """Map each rule number in the CR text to its text.

    A line that doesn't start a rule continues the rule before it: the "Example:" paragraphs and
    the few unnumbered paragraphs that follow a rule (for instance after 702.9b). Chapter headings
    (``"2. Parts of a Card"``) are skipped. The contents list repeats the section numbers
    (``"103. Starting the Game"``) but has no subrules, and the body comes later in the file, so
    the last occurrence of a number wins. The text stops at the glossary, which isn't compared:
    the glossary has no rule numbers, and its entries restate rules.
    """
    rules: dict[str, str] = {}
    current: str | None = None
    seen_subrule = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or _CHAPTER.match(line):
            continue
        match = RULE_LINE.match(line)
        if match:
            current = str(match.group(1))
            seen_subrule = seen_subrule or "." in current
            rules[current] = str(match.group(2))
        elif line == "Glossary" and seen_subrule:
            break
        elif current is not None:
            rules[current] += "\n" + line
    return rules


def load_rules(path: Path) -> dict[str, str]:
    """Read a CR text file (UTF-8, with or without a byte order mark; any line endings)."""
    return parse_rules(path.read_text(encoding="utf-8-sig"))


def word_diff(old: str, new: str) -> str:
    """Show ``new`` against ``old`` word by word: ``[-removed-]`` and ``{+added+}``."""
    a, b = old.split(), new.split()
    parts: list[str] = []
    for op, a1, a2, b1, b2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            parts.append(" ".join(a[a1:a2]))
            continue
        if a2 > a1:
            parts.append("[-" + " ".join(a[a1:a2]) + "-]")
        if b2 > b1:
            parts.append("{+" + " ".join(b[b1:b2]) + "+}")
    return " ".join(parts)


def similarity(a: str, b: str) -> float:
    """How alike two texts are, from 0 to 1, comparing words."""
    return difflib.SequenceMatcher(None, a.split(), b.split(), autojunk=False).ratio()
