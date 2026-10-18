"""List the rules the engine doesn't implement yet: every ``NotImplementedRule`` in the source.

Usage::

    uv run python tools/gaps.py              # scan src/resolve
    uv run python tools/gaps.py some/dir     # scan another folder

The list is generated, never maintained by hand (CLAUDE.md, "Documentation requirements"). It is
sorted by CR number. A ``NotImplementedRule`` whose message isn't a string literal starting with
``"<CR number>: "`` can't be listed; the tool reports it and exits with status 1, so every gap
stays findable.
"""

from __future__ import annotations

import argparse
import ast
import io
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from resolve.citations import is_rule_reference

REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE_DIR = REPO_ROOT / "src" / "resolve"

_RULE_PARTS = re.compile(r"(\d+)(?:\.(\d+)([a-z]?))?")


@dataclass(frozen=True)
class Gap:
    """One ``NotImplementedRule`` raise site: the rule, what is missing, and where."""

    rule: str
    what: str
    path: Path
    line: int


@dataclass(frozen=True)
class UnlistableGap:
    """A ``NotImplementedRule`` whose message can't be read from the source."""

    path: Path
    line: int
    reason: str


def rule_sort_key(rule: str) -> tuple[int, int, str]:
    """Sort CR citations numerically: 103.5 < 103.10 < 104 < 104.3a."""
    match = _RULE_PARTS.fullmatch(rule)
    if match is None:
        return (sys.maxsize, 0, rule)
    section, number, letter = match.groups()
    return (int(section), -1 if number is None else int(number), letter or "")


def _message(node: ast.expr) -> str | None:
    """The literal text of a message argument, up to the first f-string placeholder."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr) and node.values:
        first = node.values[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
    return None


def _is_gap_call(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "NotImplementedRule"
    return isinstance(func, ast.Attribute) and func.attr == "NotImplementedRule"


def scan_file(path: Path) -> tuple[list[Gap], list[UnlistableGap]]:
    """The gaps raised in one Python file."""
    # Parsing the bytes decodes them as Python does: UTF-8 with or without a byte order mark
    # (which some Windows editors write), or the file's coding declaration (PEP 263).
    tree = ast.parse(path.read_bytes(), filename=str(path))
    gaps: list[Gap] = []
    unlistable: list[UnlistableGap] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_gap_call(node):
            continue
        message = _message(node.args[0]) if len(node.args) == 1 and not node.keywords else None
        if message is None:
            unlistable.append(UnlistableGap(path, node.lineno, "the message isn't a literal"))
            continue
        rule, separator, what = message.partition(": ")
        if not separator or not is_rule_reference(rule):
            unlistable.append(
                UnlistableGap(path, node.lineno, f"{message!r} doesn't start with '<CR number>: '")
            )
            continue
        gaps.append(Gap(rule, what, path, node.lineno))
    return gaps, unlistable


def find_gaps(root: Path) -> tuple[list[Gap], list[UnlistableGap]]:
    """All gaps under ``root``, sorted by rule, then file and line."""
    gaps: list[Gap] = []
    unlistable: list[UnlistableGap] = []
    for path in sorted(root.rglob("*.py")):
        file_gaps, file_unlistable = scan_file(path)
        gaps.extend(file_gaps)
        unlistable.extend(file_unlistable)
    gaps.sort(key=lambda gap: (rule_sort_key(gap.rule), str(gap.path), gap.line))
    return gaps, unlistable


def format_report(
    gaps: Sequence[Gap], unlistable: Sequence[UnlistableGap], *, relative_to: Path
) -> str:
    """The report printed by ``main``."""

    def where(path: Path, line: int) -> str:
        try:
            shown = path.relative_to(relative_to)
        except ValueError:
            shown = path
        return f"{shown.as_posix()}:{line}"

    lines = [f"NotImplementedRule gaps: {len(gaps)}"]
    lines += [f"  {gap.rule:<9} {gap.what}  ({where(gap.path, gap.line)})" for gap in gaps]
    if unlistable:
        lines.append(f"Gaps that can't be listed: {len(unlistable)}")
        lines += [f"  {where(u.path, u.line)}: {u.reason}" for u in unlistable]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Print the gap report; the exit status is 1 if any gap can't be listed."""
    parser = argparse.ArgumentParser(description="List the NotImplementedRule gaps.")
    parser.add_argument("root", nargs="?", type=Path, default=ENGINE_DIR, help="folder to scan")
    args = parser.parse_args(argv)
    root: Path = args.root.resolve()
    gaps, unlistable = find_gaps(root)
    print(format_report(gaps, unlistable, relative_to=REPO_ROOT))
    return 1 if unlistable else 0


if __name__ == "__main__":
    # Redirected output would use the locale's code page, cp1252 on Windows, which can't encode
    # every card or path name; write UTF-8 everywhere (CLAUDE.md, Platform).
    stdout = sys.stdout
    if isinstance(stdout, io.TextIOWrapper):
        stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
