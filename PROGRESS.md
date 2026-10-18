# PROGRESS: get PR #11 (windows-first-class) green on Windows

Task: PR #11 adds Windows and Python 3.14 to CI; fix every failure at the root, fix the whole
class of problem, update the PR description. https://github.com/abebdm/resolve/pull/11

## Findings

- CI run 39107496881: all three Windows jobs fail at pytest, Linux passes. Same 2 tests each:
  `test_cli_import_installs_and_records`, `test_cli_refuses_to_replace_a_pinned_snapshot_without_update`
  (tests/tooling/test_fetch_scryfall_tool.py). `UnicodeDecodeError: byte 0xa9`.
- Root cause: the test helper `readme_copy` writes the rules README with `write_text()` and no
  encoding, so Windows writes cp1252 (`©` = 0xa9); the tool then reads it as UTF-8, correctly.
  Reproduced on Linux with `LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=0 uv run pytest`.
- `PYTHONWARNDEFAULTENCODING=1 uv run pytest -W error::EncodingWarning` finds 13 tests using the
  locale encoding (all in test code, none in src/tools).
- Same class, latent: tools write stdout in the locale encoding when redirected; on Windows that is
  cp1252, which can't encode `−` (U+2212, planeswalker abilities). `coverage.py --oracle > f`
  crashes. Reproduced with `PYTHONIOENCODING=cp1252`.
- Same class, latent: `load_decklist` rejects a UTF-8 BOM (Notepad / PowerShell 5.1) and crashes
  with UnicodeDecodeError on UTF-16 (PowerShell 5.1 `>`).
- Tools write tracked files (rules README) with platform newlines: CRLF on Windows.
- Clean: paths, subprocess use, file names, exec bits, doc commands.

## Plan / status

- [ ] fixture encodings in tests (explicit utf-8)
- [ ] portability lint test (text I/O without encoding, shell subprocess) over src/tools/tests
- [ ] CI: PYTHONWARNDEFAULTENCODING=1 + filterwarnings error::EncodingWarning
- [ ] tools: UTF-8 stdout; newline="\n" for written files; tests
- [ ] load_decklist: BOM / UTF-16 / undecodable -> DecklistError; tests first
- [ ] docs: decisions.md, CLAUDE.md platform section, howto
- [ ] push, CI green on all 6 combos, PR description, delete PROGRESS.md
