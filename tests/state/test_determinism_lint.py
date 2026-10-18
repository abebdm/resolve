"""The engine code can't reach outside randomness, clocks or object identity (CLAUDE.md rule 6).

A source scan of the engine packages: no imports of clocks or other random sources, and no calls
to ``id()`` or ``hash()``, whose values change between runs. Iteration over sets can't be found
by a scan; the purity check keeps sets out of the state instead.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[2] / "src" / "resolve"
# The data package reads files and dates snapshots; it isn't part of a game's computation.
# Agents are scanned too: a fuzz game must be reproducible from its seeds.
PACKAGES = ("state", "engine", "events", "decisions", "effects", "agents")
MODULES = ("tasks.py", "values.py", "errors.py", "citations.py")
SCANNED = sorted(path for package in PACKAGES for path in (ENGINE / package).rglob("*.py")) + [
    ENGINE / name for name in MODULES
]

BANNED_MODULES = {"time", "datetime", "random", "uuid", "secrets", "os", "threading"}
BANNED_CALLS = {"id", "hash"}


def banned_uses(source: str) -> list[str]:
    """Banned imports and calls in Python source, as ``"line N: ..."`` strings."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in BANNED_MODULES:
                    found.append(f"line {node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in BANNED_MODULES:
                found.append(f"line {node.lineno}: from {node.module} import ...")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in BANNED_CALLS
        ):
            found.append(f"line {node.lineno}: {node.func.id}()")
    return found


def test_the_scan_covers_the_engine() -> None:
    names = {path.name for path in SCANNED}
    assert {"game.py", "rng.py", "loop.py", "pipeline.py", "spaces.py", "tasks.py"} <= names
    assert {"random_agent.py", "scripted.py", "driver.py", "text.py"} <= names


@pytest.mark.parametrize("path", SCANNED, ids=lambda path: str(path.relative_to(ENGINE)))
def test_engine_code_uses_no_clock_outside_randomness_or_object_identity(path: Path) -> None:
    assert banned_uses(path.read_text(encoding="utf-8")) == []


def test_the_scan_finds_banned_uses() -> None:
    source = "import time\nfrom random import shuffle\nimport os.path\nx = id(1) + hash(2)\n"
    assert banned_uses(source) == [
        "line 1: import time",
        "line 2: from random import ...",
        "line 3: import os.path",
        "line 4: id()",
        "line 4: hash()",
    ]
