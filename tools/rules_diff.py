"""Compare two Comprehensive Rules text files by rule number, and find who cites what changed.

Usage::

    uv run python tools/rules_diff.py OLD.txt NEW.txt
    uv run python tools/rules_diff.py OLD.txt NEW.txt --scan src --scan tests   # other folders

Reports, in CR order:

- **changed** rules (same number, different text), with a word-level diff: ``[-old-]`` marks
  removed words and ``{+new+}`` added ones;
- **renumbered** rules: a removed number whose text is nearly the same as an added number's
  (matched by text similarity, best pairs first; ``--threshold`` sets the cut-off);
- **removed** and **added** rules (what is left after matching).

For every changed, removed or renumbered rule it then lists each place in ``src/``, ``tools/``
and ``tests/`` that cites it (exact number; a citation of a parent rule is not matched). Those
citations, and the tests next to them, are what to review against the new text
(docs/howto.md, "Update to a new Comprehensive Rules version"). The exit status is 0 whatever the
differences are, and 1 if a file can't be read.
"""

from __future__ import annotations

import argparse
import difflib
import io
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCAN_DIRS = ("src", "tools", "tests")
DEFAULT_THRESHOLD = 0.8

# "103. Starting the Game", "103.1. At the start...", "103.1a In a game..."
_RULE_LINE = re.compile(r"^(\d{3}(?:\.\d+[a-z]?)?)\.?\s+(\S.*)$")
# A dotted CR number in prose: three digits, a dot, a number, maybe a letter ("613.7m").
_DOTTED = re.compile(r"(?<![\w.])([1-9]\d{2}\.\d+[a-z]?)(?![\w.]*\d)")
_RULE_PARTS = re.compile(r"(\d+)(?:\.(\d+)([a-z]?))?")


@dataclass(frozen=True)
class Changed:
    """A rule whose number is in both files but whose text differs."""

    number: str
    old: str
    new: str


@dataclass(frozen=True)
class Renumbered:
    """A rule that moved: ``old_number`` in the old file looks like ``new_number`` in the new."""

    old_number: str
    new_number: str
    old: str
    new: str
    similarity: float


@dataclass(frozen=True)
class RulesDiff:
    """The differences between two versions of the CR."""

    changed: tuple[Changed, ...]
    renumbered: tuple[Renumbered, ...]
    removed: tuple[tuple[str, str], ...]
    added: tuple[tuple[str, str], ...]


def rule_sort_key(rule: str) -> tuple[int, int, str]:
    """Sort CR numbers numerically: 103.5 < 103.10 < 104 < 104.3a."""
    match = _RULE_PARTS.fullmatch(rule)
    if match is None:
        return (sys.maxsize, 0, rule)
    section, number, letter = match.groups()
    return (int(section), -1 if number is None else int(number), letter or "")


def parse_rules(text: str) -> dict[str, str]:
    """Map each rule number in the CR text to its text.

    Lines that don't start with a number continue the previous rule (the "Example:" paragraphs
    belong to the rule they follow). The contents list and the glossary have no rule numbers of
    the form 103.1, but the contents list repeats section numbers such as ``103.``: the body comes
    later in the file, so the last occurrence of a number wins.
    """
    rules: dict[str, str] = {}
    current: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = _RULE_LINE.match(line)
        if match:
            current = str(match.group(1))
            rules[current] = str(match.group(2))
        elif current is not None and line.startswith("Example:"):
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
    """How alike two rule texts are, from 0 to 1, comparing words."""
    return difflib.SequenceMatcher(None, a.split(), b.split(), autojunk=False).ratio()


def diff_rules(
    old: dict[str, str], new: dict[str, str], *, threshold: float = DEFAULT_THRESHOLD
) -> RulesDiff:
    """Compare two rule maps; ``threshold`` is the least similarity that counts as a renumbering."""
    changed = tuple(
        Changed(number, old[number], new[number])
        for number in sorted(old.keys() & new.keys(), key=rule_sort_key)
        if old[number].split() != new[number].split()
    )
    gone = sorted(old.keys() - new.keys(), key=rule_sort_key)
    fresh = sorted(new.keys() - old.keys(), key=rule_sort_key)
    candidates = sorted(
        (
            (score, o, n)
            for o in gone
            for n in fresh
            if (score := similarity(old[o], new[n])) >= threshold
        ),
        # Best match first; ties go to the numbers that sit closest in CR order.
        key=lambda c: (-c[0], rule_sort_key(c[1]), rule_sort_key(c[2])),
    )
    moved: list[Renumbered] = []
    used_old: set[str] = set()
    used_new: set[str] = set()
    for score, o, n in candidates:
        if o in used_old or n in used_new:
            continue
        used_old.add(o)
        used_new.add(n)
        moved.append(Renumbered(o, n, old[o], new[n], score))
    moved.sort(key=lambda m: rule_sort_key(m.old_number))
    return RulesDiff(
        changed=changed,
        renumbered=tuple(moved),
        removed=tuple((o, old[o]) for o in gone if o not in used_old),
        added=tuple((n, new[n]) for n in fresh if n not in used_new),
    )


def python_files(root: Path) -> list[Path]:
    """Every ``.py`` file under ``root``, sorted by path."""
    return sorted(root.rglob("*.py"))


def find_citations(paths: Iterable[Path], *, relative_to: Path) -> dict[str, list[str]]:
    """Map each dotted CR number cited in the files to where: ``"path:line"``, in order."""
    cited: dict[str, list[str]] = {}
    for path in paths:
        try:
            shown = path.relative_to(relative_to).as_posix()
        except ValueError:
            shown = path.as_posix()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for rule in _DOTTED.findall(line):
                cited.setdefault(rule, []).append(f"{shown}:{number}")
    return cited


def _short(text: str, limit: int = 100) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def format_report(diff: RulesDiff, citations: dict[str, list[str]]) -> str:
    """The report described in the module docstring."""

    def cited_by(rule: str) -> list[str]:
        places = citations.get(rule, [])
        return [f"      cited at {place}" for place in places] or ["      (not cited)"]

    lines = [
        f"changed: {len(diff.changed)}, renumbered: {len(diff.renumbered)}, "
        f"removed: {len(diff.removed)}, added: {len(diff.added)}"
    ]
    lines += ["", f"== Changed rules ({len(diff.changed)}) =="]
    for item in diff.changed:
        lines.append(f"  {item.number}: {word_diff(item.old, item.new)}")
        lines += cited_by(item.number)
    lines += ["", f"== Probably renumbered ({len(diff.renumbered)}) =="]
    for moved in diff.renumbered:
        lines.append(
            f"  {moved.old_number} -> {moved.new_number} (similarity {moved.similarity:.2f}): "
            f"{word_diff(moved.old, moved.new)}"
        )
        lines += cited_by(moved.old_number)
    lines += ["", f"== Removed rules ({len(diff.removed)}) =="]
    for number, text in diff.removed:
        lines.append(f"  {number}: {_short(text)}")
        lines += cited_by(number)
    lines += ["", f"== Added rules ({len(diff.added)}) =="]
    lines += [f"  {number}: {_short(text)}" for number, text in diff.added]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """Print the report; the exit status is 1 if a rules file can't be read."""
    parser = argparse.ArgumentParser(description="Compare two Comprehensive Rules text files.")
    parser.add_argument("old", type=Path, help="the pinned rules file")
    parser.add_argument("new", type=Path, help="the new rules file")
    parser.add_argument(
        "--scan",
        action="append",
        type=Path,
        help=f"folder to search for citations (repeatable; default: {' '.join(DEFAULT_SCAN_DIRS)})",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help="least text similarity (0 to 1) that counts as a renumbering",
    )
    args = parser.parse_args(argv)
    try:
        old, new = load_rules(args.old), load_rules(args.new)
    except (OSError, UnicodeDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    roots: list[Path] = args.scan or [REPO_ROOT / name for name in DEFAULT_SCAN_DIRS]
    files = [path for root in roots for path in python_files(root)]
    citations = find_citations(files, relative_to=REPO_ROOT)
    sys.stdout.write(format_report(diff_rules(old, new, threshold=args.threshold), citations))
    return 0


if __name__ == "__main__":
    # Redirected output would use the locale's code page, cp1252 on Windows, which can't encode
    # every character of the rules; write UTF-8 everywhere (CLAUDE.md, Platform).
    stdout = sys.stdout
    if isinstance(stdout, io.TextIOWrapper):
        stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
