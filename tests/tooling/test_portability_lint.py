"""The code runs the same on Windows and Linux (CLAUDE.md, "Platform: Windows first").

A source scan of ``src``, ``tools`` and ``tests``:

- every text-mode file open names its encoding. Without one, Python uses the locale's code page,
  which is cp1252 on a Western Windows machine and UTF-8 on Linux, so the same file reads or
  writes differently (PEP 597). This is how the README copy in the fetch_scryfall tests broke on
  Windows: ``write_text()`` wrote ``©`` as cp1252 and the tool read it back as UTF-8;
- subprocesses get a list of arguments, never a shell string, and decode their output explicitly;
- no POSIX-only modules or calls, and no hard-coded ``/tmp``.

CI also runs pytest with ``PYTHONWARNDEFAULTENCODING=1`` and turns ``EncodingWarning`` into an
error, which catches at run time what a scan of the source can't see.
"""

from __future__ import annotations

import ast
from pathlib import Path, PurePosixPath

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCANNED = sorted(
    path for folder in ("src", "tools", "tests") for path in (REPO_ROOT / folder).rglob("*.py")
)

# Functions and methods that open a file in text mode unless their mode says binary.
TEXT_METHODS = {"read_text", "write_text"}
COMPRESSED_MODULES = {"gzip", "bz2", "lzma"}  # their ``open`` defaults to binary
SUBPROCESS_CALLS = {"run", "Popen", "call", "check_call", "check_output"}
POSIX_ONLY_MODULES = {"fcntl", "termios", "pwd", "grp", "resource", "pty", "tty", "posix"}
POSIX_ONLY_OS_CALLS = {"fork", "forkpty", "setsid", "getuid", "geteuid", "getgid", "killpg"}


def _keywords(call: ast.Call) -> dict[str, ast.expr]:
    return {keyword.arg: keyword.value for keyword in call.keywords if keyword.arg is not None}


def _is_true(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _mode(call: ast.Call, position: int) -> str | None:
    """The mode argument if it is a string literal; ``None`` if absent or computed."""
    node = _keywords(call).get("mode")
    if node is None and len(call.args) > position:
        node = call.args[position]
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _opens_text(call: ast.Call) -> bool:
    """Whether ``call`` opens a file in text mode (or a mode the scan can't read)."""
    func = call.func
    if isinstance(func, ast.Name) and func.id == "open":
        mode = _mode(call, 1)
        return mode is None or "b" not in mode
    if isinstance(func, ast.Attribute) and func.attr == "open":
        if isinstance(func.value, ast.Name) and func.value.id in COMPRESSED_MODULES:
            mode = _mode(call, 1)
            return mode is not None and "t" in mode
        if isinstance(func.value, ast.Name) and func.value.id == "io":
            mode = _mode(call, 1)
            return mode is None or "b" not in mode
        # ``Path.open(mode)``: the mode is the first argument.
        mode = _mode(call, 0)
        return mode is None or "b" not in mode
    return isinstance(func, ast.Attribute) and func.attr in TEXT_METHODS


def portability_problems(source: str) -> list[str]:
    """Non-portable uses in Python source, as ``"line N: ..."`` strings."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in POSIX_ONLY_MODULES:
                    found.append(f"line {node.lineno}: POSIX-only module {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in POSIX_ONLY_MODULES:
                found.append(f"line {node.lineno}: POSIX-only module {node.module}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if PurePosixPath(node.value).parts[:2] == ("/", "tmp"):
                found.append(f"line {node.lineno}: hard-coded /tmp")
        elif isinstance(node, ast.Call):
            found.extend(_call_problems(node))
    return found


def _call_problems(call: ast.Call) -> list[str]:
    func = call.func
    keywords = _keywords(call)
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    line = call.lineno
    if (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id == "os"
        and func.attr in POSIX_ONLY_OS_CALLS
    ):
        return [f"line {line}: POSIX-only os.{func.attr}()"]
    if _opens_text(call) and "encoding" not in keywords:
        return [f"line {line}: {name}() in text mode without an encoding"]
    if name == "TextIOWrapper" and "encoding" not in keywords:
        return [f"line {line}: TextIOWrapper() without an encoding"]
    if (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id == "subprocess"
        and func.attr in SUBPROCESS_CALLS
    ):
        problems: list[str] = []
        if _is_true(keywords.get("shell")):
            problems.append(f"line {line}: subprocess.{func.attr}() with shell=True")
        if call.args and isinstance(call.args[0], ast.Constant | ast.JoinedStr):
            problems.append(f"line {line}: subprocess.{func.attr}() with a command string")
        text = _is_true(keywords.get("text")) or _is_true(keywords.get("universal_newlines"))
        if text and "encoding" not in keywords:
            problems.append(f"line {line}: subprocess.{func.attr}() decodes without an encoding")
        return problems
    return []


def test_the_scan_covers_src_tools_and_tests() -> None:
    names = {path.relative_to(REPO_ROOT).as_posix() for path in SCANNED}
    assert {
        "src/resolve/data/decklist.py",
        "tools/fetch_scryfall.py",
        "tests/tooling/test_fetch_scryfall_tool.py",
        "tests/scenario.py",
    } <= names


@pytest.mark.parametrize("path", SCANNED, ids=lambda path: path.relative_to(REPO_ROOT).as_posix())
def test_code_is_portable_to_windows(path: Path) -> None:
    assert portability_problems(path.read_text(encoding="utf-8")) == []


def test_the_scan_finds_text_io_without_an_encoding() -> None:
    source = (
        "readme.write_text(text)\n"
        "(root / 'a.txt').read_text()\n"
        "open(name)\n"
        "open(name, 'w')\n"
        "path.open()\n"
        "path.open('a')\n"
        "io.open(name, 'r')\n"
        "gzip.open(name, 'rt')\n"
        "io.TextIOWrapper(raw)\n"
    )
    assert portability_problems(source) == [
        "line 1: write_text() in text mode without an encoding",
        "line 2: read_text() in text mode without an encoding",
        "line 3: open() in text mode without an encoding",
        "line 4: open() in text mode without an encoding",
        "line 5: open() in text mode without an encoding",
        "line 6: open() in text mode without an encoding",
        "line 7: open() in text mode without an encoding",
        "line 8: open() in text mode without an encoding",
        "line 9: TextIOWrapper() without an encoding",
    ]


def test_the_scan_accepts_binary_io_and_explicit_encodings() -> None:
    source = (
        "readme.write_text(text, encoding='utf-8', newline='\\n')\n"
        "path.read_text(encoding='utf-8')\n"
        "path.read_bytes()\n"
        "open(name, 'rb')\n"
        "open(name, mode='wb')\n"
        "path.open('rb')\n"
        "gzip.open(name)\n"
        "gzip.open(name, 'rt', encoding='utf-8')\n"
        "open(name, 'w', encoding='utf-8')\n"
        "io.TextIOWrapper(raw, encoding='utf-8')\n"
        "urllib.request.urlopen(url)\n"
    )
    assert portability_problems(source) == []


def test_the_scan_finds_shell_subprocesses() -> None:
    source = (
        "subprocess.run('ls -l', shell=True)\n"
        "subprocess.check_output(f'git {cmd}')\n"
        "subprocess.run([sys.executable, '-c', code], text=True)\n"
        "subprocess.Popen(args, universal_newlines=True)\n"
        "subprocess.run([sys.executable, '-c', code], text=True, encoding='utf-8')\n"
        "subprocess.run([sys.executable, '-V'], capture_output=True)\n"
    )
    assert portability_problems(source) == [
        "line 1: subprocess.run() with shell=True",
        "line 1: subprocess.run() with a command string",
        "line 2: subprocess.check_output() with a command string",
        "line 3: subprocess.run() decodes without an encoding",
        "line 4: subprocess.Popen() decodes without an encoding",
    ]


def test_the_scan_finds_posix_only_features() -> None:
    source = (
        "import fcntl\n"
        "from pwd import getpwnam\n"
        "pid = os.fork()\n"
        "scratch = Path('/tmp/resolve')\n"
        "root = Path('/tmp')\n"
        "import os, signal\n"
        "where = 'see /tmp for details'\n"
    )
    assert portability_problems(source) == [
        "line 1: POSIX-only module fcntl",
        "line 2: POSIX-only module pwd",
        "line 3: POSIX-only os.fork()",
        "line 4: hard-coded /tmp",
        "line 5: hard-coded /tmp",
    ]
