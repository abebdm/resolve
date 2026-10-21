"""Reading Comprehensive Rules text files, and comparing text word by word (for the update tools).

``tools/rules_diff.py``, ``tools/card_diff.py`` and ``tools/rule.py`` use these; the engine
doesn't.
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path

from resolve.citations import RULE_LINE

# The pinned Comprehensive Rules (docs/rules/README.md). Every tool and test that reads the pinned
# CR uses this path; src/resolve/data/rules_text.py -> parents[3] is the repository root.
PINNED_RULES_FILE = (
    Path(__file__).resolve().parents[3] / "docs" / "rules" / "MagicCompRules-20260925.txt"
)

# A chapter heading in the body and the contents list: "2. Parts of a Card".
_CHAPTER = re.compile(r"^\d\.\s")


def rule_blocks(text: str) -> dict[str, list[str]]:
    """Map each rule number in the CR text to its lines, exactly as written (stripped of padding).

    The first line is the rule's own (``"704.5a If a player..."``). A line that doesn't start a
    rule continues the rule before it: the "Example:" paragraphs and the few unnumbered
    paragraphs that follow a rule (for instance after 702.9b). Blank lines and chapter headings
    (``"2. Parts of a Card"``) are skipped. The contents list repeats the section numbers
    (``"103. Starting the Game"``) but has no subrules, and the body comes later in the file, so
    the last occurrence of a number wins. The text stops at the glossary (see ``parse_glossary``).
    """
    blocks: dict[str, list[str]] = {}
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
            blocks[current] = [line]
        elif line == "Glossary" and seen_subrule:
            break
        elif current is not None:
            blocks[current].append(line)
    return blocks


def parse_rules(text: str) -> dict[str, str]:
    """Map each rule number in the CR text to its text, without the number.

    The lines of ``rule_blocks`` joined by newlines, so a rule's examples and continuation
    paragraphs are part of its text. The glossary isn't included: it has no rule numbers, and its
    entries restate rules.
    """
    rules: dict[str, str] = {}
    for number, lines in rule_blocks(text).items():
        match = RULE_LINE.match(lines[0])
        assert match is not None
        rules[number] = "\n".join([str(match.group(2)), *lines[1:]])
    return rules


def parse_glossary(text: str) -> dict[str, str]:
    """Map each glossary term of the CR text to its definition (lines joined by newlines).

    The glossary is the text after the last line that reads ``"Glossary"`` (the contents list
    names it first) and before the last ``"Credits"`` after it, if any. Entries are separated by
    blank lines; an entry's first line is the term.
    """
    lines = [raw.strip() for raw in text.splitlines()]
    starts = [i for i, line in enumerate(lines) if line == "Glossary"]
    if not starts:
        return {}
    body = lines[starts[-1] + 1 :]
    ends = [i for i, line in enumerate(body) if line == "Credits"]
    if ends:
        body = body[: ends[-1]]
    glossary: dict[str, str] = {}
    entry: list[str] = []
    for line in [*body, ""]:
        if line:
            entry.append(line)
        elif entry:
            glossary[entry[0]] = "\n".join(entry[1:])
            entry = []
    return glossary


def read_rules_text(path: Path) -> str:
    """Read a CR text file (UTF-8, with or without a byte order mark; any line endings)."""
    return path.read_text(encoding="utf-8-sig")


def load_rules(path: Path) -> dict[str, str]:
    """The rules of a CR text file (see ``parse_rules`` and ``read_rules_text``)."""
    return parse_rules(read_rules_text(path))


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
