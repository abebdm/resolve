"""Every tool writes UTF-8 to standard output, whatever the platform (CLAUDE.md, Platform).

When output goes to a file or a pipe (``uv run python tools/coverage.py > report.txt``), Python
encodes it with the locale's code page. On Windows that is cp1252, which has no minus sign (U+2212,
used by every planeswalker ability) and no characters outside Western European scripts, so a
report or a path could crash the tool halfway. ``PYTHONIOENCODING=cp1252`` recreates that on any
platform.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS = sorted(path for path in (REPO_ROOT / "tools").glob("*.py") if path.name != "__init__.py")

# Runs a tool as a script (its ``__main__`` block) with --help, then prints a character cp1252
# can't encode through the same standard output.
PROBE = """\
import runpy, sys
tool = sys.argv[1]
sys.argv = [tool, "--help"]
try:
    runpy.run_path(tool, run_name="__main__")
except SystemExit:
    pass
print("\\u2212", end="")
"""


def test_every_tool_is_probed() -> None:
    names = {path.name for path in TOOLS}
    assert {"coverage.py", "fetch_scryfall.py", "fuzz.py", "gaps.py", "play_cli.py"} <= names


@pytest.mark.parametrize("tool", TOOLS, ids=lambda path: path.name)
def test_tool_output_is_utf8_when_the_locale_is_cp1252(tool: Path) -> None:
    completed = subprocess.run(
        [sys.executable, "-c", PROBE, str(tool)],
        cwd=REPO_ROOT,
        env=dict(os.environ, PYTHONIOENCODING="cp1252"),
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    assert completed.stdout.startswith(b"usage: ")
    assert completed.stdout.endswith("\u2212".encode())
