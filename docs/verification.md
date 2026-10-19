# Verifying a milestone by hand

At the end of each milestone (M0, M1, ...) the user checks on their own Windows machine that
everything works. This page is that checklist. Agents run the quick checks on every change
(CLAUDE.md, "Testing requirements"); this page holds the long, `--thorough` runs they don't.

## Note for the coordinating agent

The user works with an agent that coordinates the coding agents and helps them run checks. That
agent should know:

- **Coding agents run the quick defaults:** `uv run pytest`, `uv run ruff check .`,
  `uv run pyright` and, for engine changes, `uv run python tools/fuzz.py` (about a minute). They
  don't run `--thorough` presets unless asked; that is expected, not a gap.
- **The user's milestone check uses the `--thorough` presets** listed below, never the quick
  defaults. Point the user to the checklist below and help read the output. A milestone isn't
  verified until every step passes.
- **The rule** (CLAUDE.md, "Quick runs for agents, thorough runs for the user's milestone
  checks"): any run whose length is a trade-off has a quick default and a `--thorough` preset,
  and every `--thorough` run is listed here with what to look for. When reviewing a PR that adds
  or changes such a run, check that it updated this page.
- **A failure** prints a line starting `FAILED:` with a command that reproduces that one game.
  Hand that line, and the options of the run, to a coding agent; it reproduces the failure, turns
  it into a failing test and fixes the engine (`docs/howto.md`, "Run the fuzz harness").

## The checklist

Run these in PowerShell from the repository root, on an up-to-date checkout of `main`.

1. **Update:** `git pull`, then `uv sync`.
2. **Tests, with the encoding check CI uses:** `$env:PYTHONWARNDEFAULTENCODING = "1"; uv run pytest`.
   Every test passes; none is skipped.
3. **Lint and types:** `uv run ruff check .` and `uv run pyright`. Both report no problems.
4. **The thorough fuzz run:** `uv run python tools/fuzz.py --thorough`. It takes THOROUGH_TIME;
   the summary prints at the end. Check that:
   - the first line says `Run: thorough preset;` and `THOROUGH_GAMES games passed`, and nothing
     says `FAILED:`;
   - `Endings:` shows both `decked` and `concession` games, `life total x0` and `draw x0`
     (nothing in M1's basic-land decks can change a life total, and a game ends before two
     players can deck out at once), and `rules gap x0` (basic lands never reach a rules gap);
   - `Turns per game:` reaches a maximum above 50, and `Played:` shows thousands of lands and
     mana abilities.
   The exact numbers depend on the engine and change from milestone to milestone; a run with the
   same code always prints the same numbers, except the timing.
5. **The quick run** (what agents run): `uv run python tools/fuzz.py`. Under a minute; the same
   checks as step 4 on 10 games, except that most of its games end by concession.
6. **Rules gaps:** `uv run python tools/gaps.py` lists every rule the engine doesn't implement
   yet. Check it matches what the milestone left for later (`docs/roadmap.md`).

## Optional, with the card data snapshot

With the Scryfall snapshot in `data/` (`docs/howto.md`, "Fetch or update the card data
snapshot"):

- `uv run python tools/card_excerpt.py tools/excerpts/basic_lands.json --check`: the committed
  basic lands still match the snapshot.
- `uv run python tools/coverage.py`: which cards of the target decks in `decks/` are
  implemented.
