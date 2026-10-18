# Progress: meaningful default fuzz run

Task (user prompt, no PR yet): make `uv run python tools/fuzz.py` default to basic-land decks
(no snapshot needed), keep empty decks as an explicit option, have the summary show answers per
game (min/avg/max), turns per game and endings by type (decked, life total, concession, draw,
rules gap), add tests (a default run reaches later turns, plays lands, taps for mana; summary
numbers checked), document defaults and flags in `docs/howto.md` with PowerShell commands, record
the card-data choice in `docs/decisions.md`, follow CLAUDE.md, open a PR.

Paused at the user's request (usage limit). Work is committed on `claude/gallant-hawking-bv7f0u`.

## Done (committed)
- `tools/excerpts/basic_lands.json`: the five basic lands, copied (not hand-written) from the
  Scryfall snapshot of 2026-10-18 by the new `tools/card_excerpt.py` (write with names; `--check`
  compares an excerpt with `data/`). Records are trimmed to `EXCERPT_CARD_FIELDS`; the excerpt
  stores the source manifest under `taken_from`. Basic lands have no rulings.
- `resolve.data.cards`: `EXCERPT_FORMAT`, `EXCERPT_CARD_FIELDS`, `load_card_excerpt(path)`, and
  `parse_snapshot_info` (factored out of `load_snapshot_info`). Exported from `resolve.data`.
- `tools/fuzz.py` (written, ruff and pyright clean, **no tests run yet**):
  - `fuzz_run`/`fuzz_game` take `check_every` (default 1, i.e. unchanged for tests): full checks
    (state_problems, copies, invalid-answer probes, rejected-answer snapshot) only when
    `answers % check_every == 0` and on the final state; `invariant_violations` every decision;
    replay always. A rejected answer that changes state between checks is still caught by the
    replay (it never submits rejected answers).
  - Summary: `ending(result)` (ENDINGS = decked/life total/concession/draw/rules gap, else
    `other (<rule>)`; named after the last `PlayerLost`), `GameStats.of(result)` (answers,
    rejected, turns, ending, lands played, mana abilities = `ManaAdded` count),
    `summary_lines(games)`.
  - CLI: default decks `basic_land_deck()` = 8 of each basic (40), `--empty-decks` (mutually
    exclusive with `--deck`), `--check-every N` (default `DEFAULT_CHECK_EVERY = 10`), prints a
    `Decks:` line and the summary.

## In progress: the defaults are too slow and too concession-heavy
Measurements (this container):
- Full checks are quadratic in game length: they walk/copy/compare the whole event log each
  decision (`_walk_immutable`, `_walk_pure` and `dataclasses.fields` dominate the profile, then
  `pickle.loads`, `deepcopy`). A 3-player 40-card game of 498 answers took 90 s with
  `check_every=1`.
- With `check_every=10`: 10 default games took 78 s (0.13 games/s); 200 games would take ~26 min.
- Without any state checks, 20 games (2-6 players, both formats): 40-card decks with
  concessions 1/200 → all 20 end by concession, answers 64/652/1952, turns 4/22/49, 64 s;
  1/1000 → 13 concession, 7 decked, answers avg 2529 (max 5000), 746 s; 20-card decks (4 each)
  with 1/200 → 17 concession, 3 decked, 53 s; 20-card with 1/500 → 11 decked, 9 concession,
  answers avg 1093 (max 2651), 140 s.

Options to decide (ask the user if unsure; they asked for "for example, 40 basic lands"):
1. Make the checks cheaper: cache `dataclasses.fields` per type and build paths lazily in
   `resolve.state.invariants` (pure speed-up), and/or check log entries incrementally (each entry
   once, then verify the prefix by identity).
2. Lower the CLI's default `--games` (e.g. 20: two of each player count and format) and/or deck
   size, and lower the default concession chance so decking shows up in the endings.
3. Watch `MAX_ANSWERS` (10,000): a 6-player 40-card game with `--concessions 0` may exceed it.

## Next
- Pick the defaults (above), then run `uv run python tools/fuzz.py` and record its timing.
- Tests: `tests/tooling/test_card_excerpt_tool.py` (write/check with `scryfall_fixtures.
  write_snapshot`, missing/ambiguous names, malformed excerpt), `load_card_excerpt` tests in
  `tests/data/`, the committed excerpt parses to the five basics matching their definitions,
  `check_every` in `tests/fuzz/` (full checks still catch broken engines when they run;
  invariants every decision), `ending`/`GameStats`/`summary_lines` with expected values written
  out, and a default-run test (`main([...])` on a few games, stdout parsed: later turns, lands,
  mana abilities, numbers consistent). Add `card_excerpt.py` to
  `test_tool_output_encoding.py`'s expected names.
- Docs: howto.md "Run the fuzz harness" (defaults, `--empty-decks`, `--check-every`,
  `--concessions`, PowerShell commands) and a recipe for `tools/card_excerpt.py`; decisions.md
  entries (excerpt choice; check schedule; ending classification); update the 2026-10-18 fuzz
  entry ("The CLI defaults to empty decks" is now superseded); data/README.md mention of excerpts;
  CLAUDE.md status line for tools.
- Run `uv run pytest`, `uv run ruff check .`, `uv run pyright`; test-reviewer only if game
  behavior changes (it doesn't so far); delete PROGRESS.md; open the PR.

## Decisions not yet in docs
- Excerpt rather than hand-written records (tools never invent cards) or importing
  `tests/scryfall_fixtures.py` (tools can't import tests/). The loader lives in `resolve.data`
  because tools run as scripts can't import `tools.*`.
- The excerpt was taken from the current Scryfall snapshot (2026-10-18), not the pinned
  2026-10-17 one, which Scryfall no longer serves; basic lands' Oracle data doesn't change.

## Open questions for the user
- Acceptable run time for the default `tools/fuzz.py` run, and whether to trade game count,
  deck size or check density for it.
