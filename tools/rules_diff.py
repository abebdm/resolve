"""Compare two Comprehensive Rules text files by rule number, and find who cites what changed.

Usage::

    uv run python tools/rules_diff.py OLD.txt NEW.txt
    uv run python tools/rules_diff.py OLD.txt NEW.txt --scan src --scan tests   # other folders

Reports, in CR order:

- **changed** rules (same number, different text), with a word-level diff: ``[-old-]`` marks
  removed words and ``{+new+}`` added ones;
- **renumbered** rules: a rule whose text now sits under another number, matched by text
  similarity (best pairs first; ``--threshold`` sets the cut-off). This covers a subrule inserted
  in the middle of a list, which shifts every later letter, as well as moves between sections;
- **removed** and **added** rules (what is left after matching).

For every changed, removed or renumbered rule (by its old number) it lists each place that cites
it, in two groups: code and tests (``.py`` files in ``src/``, ``tools/`` and ``tests/``), and
documents (``docs/**/*.md``, except ``docs/rules/``, and ``.claude/agents/*.md``). A citation
such as ``704.5a/b`` cites both rules. Citations of the *parent* of a flagged subrule (``702.16``
when 702.16e changed) are listed separately, because that code may rely on the changed subrule.
The exit status is 0 whatever the differences are, and 1 if a file can't be read. The glossary of
the CR is not compared.
"""

from __future__ import annotations

import argparse
import io
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from resolve.citations import cited_rules, parent_rule, rule_sort_key
from resolve.data.rules_text import load_rules, similarity, word_diff

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCAN = ("src", "tools", "tests", "docs", ".claude/agents")
DEFAULT_THRESHOLD = 0.8
RULES_DOCS = Path("docs") / "rules"


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


def _section(number: str) -> str:
    return number[:3]


def diff_rules(
    old: dict[str, str], new: dict[str, str], *, threshold: float = DEFAULT_THRESHOLD
) -> RulesDiff:
    """Compare two rule maps; ``threshold`` is the least similarity that counts as a renumbering.

    Rules with the same number and the same words are unchanged. Of the rest, an old rule is
    paired with a new rule under another number when their texts are alike (at least
    ``threshold``) and more alike than the old rule is to whatever now has its own number. Pairs
    are taken best first, each rule once. Within a section every leftover old rule is a candidate
    for every leftover new rule, which finds a subrule inserted mid-list (every later letter
    shifts); across sections only removed numbers are matched with added numbers. After that, a
    number whose old text found no partner is *changed* if its new text found none either,
    otherwise *removed* (its new text came from elsewhere); likewise a new number is *added*.
    """
    unchanged = {n for n in old.keys() & new.keys() if old[n].split() == new[n].split()}
    old_open = sorted(old.keys() - unchanged, key=rule_sort_key)
    new_open = sorted(new.keys() - unchanged, key=rule_sort_key)
    stay = {n: similarity(old[n], new[n]) for n in old_open if n in new}

    candidates: list[tuple[float, str, str]] = []
    for o in old_open:
        for n in new_open:
            if o == n:
                continue
            same_section = _section(o) == _section(n)
            if not same_section and (o in new or n in old):
                continue
            if not _could_match(old[o], new[n], threshold):
                continue
            score = similarity(old[o], new[n])
            if score >= threshold and score > stay.get(o, 0.0):
                candidates.append((score, o, n))
    # Best match first; ties go to the numbers that sit closest in CR order.
    candidates.sort(key=lambda c: (-c[0], rule_sort_key(c[1]), rule_sort_key(c[2])))

    moved: list[Renumbered] = []
    old_gone: set[str] = set()  # old numbers whose text moved elsewhere
    new_from: set[str] = set()  # new numbers whose text came from elsewhere
    for score, o, n in candidates:
        if o in old_gone or n in new_from:
            continue
        old_gone.add(o)
        new_from.add(n)
        moved.append(Renumbered(o, n, old[o], new[n], score))
    moved.sort(key=lambda m: rule_sort_key(m.old_number))

    changed: list[Changed] = []
    removed: list[tuple[str, str]] = []
    added: list[tuple[str, str]] = []
    for o in old_open:
        if o in old_gone:
            continue
        if o in new and o not in new_from:
            changed.append(Changed(o, old[o], new[o]))
        else:
            removed.append((o, old[o]))
    changed_numbers = {c.number for c in changed}
    for n in new_open:
        if n not in new_from and n not in changed_numbers:
            added.append((n, new[n]))
    return RulesDiff(tuple(changed), tuple(moved), tuple(removed), tuple(added))


def _could_match(a: str, b: str, threshold: float) -> bool:
    """A cheap test that rules out most pairs before the real similarity is computed."""
    words_a, words_b = len(a.split()), len(b.split())
    return 2 * min(words_a, words_b) >= threshold * (words_a + words_b)


def scan_files(roots: Iterable[Path]) -> list[Path]:
    """The ``.py`` and ``.md`` files under the roots, sorted, without ``docs/rules/``."""
    files: set[Path] = set()
    for root in roots:
        for pattern in ("*.py", "*.md"):
            files.update(root.rglob(pattern))
    return sorted(f for f in files if not _in_rules_folder(f))


def _in_rules_folder(path: Path) -> bool:
    """Whether the path is in a ``docs/rules`` folder, which holds the CR text itself."""
    parts = path.parts
    return any(parts[i : i + 2] == RULES_DOCS.parts for i in range(len(parts) - 1))


def find_citations(paths: Iterable[Path], *, relative_to: Path) -> dict[str, list[str]]:
    """Map each dotted CR number cited in the files to where: ``"path:line"``, in order.

    A line citing a rule more than once is listed once for it; ``704.5a/b`` cites both rules.
    """
    cited: dict[str, list[str]] = {}
    for path in paths:
        try:
            shown = path.relative_to(relative_to).as_posix()
        except ValueError:
            shown = path.as_posix()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for rule in dict.fromkeys(cited_rules(line)):
                cited.setdefault(rule, []).append(f"{shown}:{number}")
    return cited


def _short(text: str, limit: int = 100) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def format_report(diff: RulesDiff, code: dict[str, list[str]], docs: dict[str, list[str]]) -> str:
    """The report described in the module docstring.

    ``code`` and ``docs`` map a rule to where it is cited in code and tests, and in documents.
    """

    def cited_by(rule: str, indent: str = "      ") -> list[str]:
        lines = [f"{indent}cited in code/tests at {place}" for place in code.get(rule, [])]
        lines += [f"{indent}cited in docs at {place}" for place in docs.get(rule, [])]
        return lines or [f"{indent}(not cited)"]

    flagged = (
        [c.number for c in diff.changed]
        + [m.old_number for m in diff.renumbered]
        + [number for number, _ in diff.removed]
    )
    lines = [
        f"changed: {len(diff.changed)}, renumbered: {len(diff.renumbered)}, "
        f"removed: {len(diff.removed)}, added: {len(diff.added)}"
    ]
    lines += ["", f"== Changed rules ({len(diff.changed)}) =="]
    for item in diff.changed:
        lines.append(f"  {item.number}: {word_diff(item.old, item.new)}")
        lines += cited_by(item.number)
    lines += ["", f"== Probably renumbered ({len(diff.renumbered)}) =="]
    lines.append("  (citations are listed under the old number; change them to the new one)")
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

    children: dict[str, list[str]] = {}
    for number in flagged:
        parent = parent_rule(number)
        if parent is not None and parent not in flagged:
            children.setdefault(parent, []).append(number)
    parents = sorted((p for p in children if p in code or p in docs), key=rule_sort_key)
    lines += ["", f"== Citations of the parent rule of a flagged subrule ({len(parents)}) =="]
    for parent in parents:
        shown = ", ".join(sorted(children[parent], key=rule_sort_key)[:6])
        more = " ..." if len(children[parent]) > 6 else ""
        lines.append(f"  {parent} (parent of {shown}{more}):")
        lines += cited_by(parent)
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
        help=f"folder to search for citations in .py and .md files (repeatable; default: "
        f"{' '.join(DEFAULT_SCAN)})",
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
        print(
            f"error: {error}\n(the rules file must be UTF-8; re-save it as UTF-8 if it isn't)",
            file=sys.stderr,
        )
        return 1
    roots: list[Path] = args.scan or [REPO_ROOT / name for name in DEFAULT_SCAN]
    files = scan_files(root for root in roots if root.exists())
    citations = find_citations(files, relative_to=REPO_ROOT)
    code = {r: [w for w in where if ".py:" in w] for r, where in citations.items()}
    docs = {r: [w for w in where if ".md:" in w] for r, where in citations.items()}
    diff = diff_rules(old, new, threshold=args.threshold)
    sys.stdout.write(format_report(diff, code, docs))
    return 0


if __name__ == "__main__":
    # Redirected output would use the locale's code page, cp1252 on Windows, which can't encode
    # every character of the rules; write UTF-8 everywhere (CLAUDE.md, Platform).
    stdout = sys.stdout
    if isinstance(stdout, io.TextIOWrapper):
        stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
