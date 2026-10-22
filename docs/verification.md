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
4. **The thorough fuzz run:** `uv run python tools/fuzz.py --thorough`. It plays 100 games with
   every check before every decision, several at once (one per CPU), and takes about an hour on
   an 8-core machine (about two on 4 cores). It prints its settings first, a line every 10
   games, and the summary at the end. Check that:
   - the first line starts `Run: thorough preset;`, the summary says `100 games passed`, and
     nothing says `FAILED:`;
   - `Endings:` shows `concession` games and many `rules gap` games, with `life total x0` and
     `draw x0` (nothing in M2.3's decks can change a life total); `decked` may be 0, since most
     games stop at the 508.1 gap once a creature resolves (M2.11 settles the final
     expectations);
   - `Spells:` shows casts, resolutions and reversals above zero; `Casts per card:` lists the
     excerpt's cards (Sol Ring, the Signets, the mana creatures and the vanilla creatures; the
     lands are played, not cast); `Gaps:` lists only `508.1` and `903.8`;
   - `Turns per game:` reaches a maximum of several tens of turns, and `Played:` shows
     thousands of lands and mana abilities, and some reversed mana ability activations
     (Selesnya Signet activated with nothing to pay its {1});
   - `Reversed casts:` shows, for the auto-pay seats, `0 of N payable` with N above zero (the
     auto-payer never reverses a cast it could pay), and for the random seats some payable casts
     reversed; most attempts of both kinds are reversed, because the random agents cast what
     they can't pay;
   - the last line gives the time; note it if it is much longer than the estimate above.
   The exact numbers depend on the engine and change from milestone to milestone; a run with the
   same code always prints the same numbers, except the timing.
5. **The quick run** (what agents run): `uv run python tools/fuzz.py`. Under a minute: 10 games,
   with the full checks every 10 answers. The same things to check as in step 4, for 10 games.
6. **The auto-payer against brute force:**
   `uv run pytest tests/agents/test_autopay_brute_force.py --thorough`. It builds 20 000 random
   small boards and costs and, on each, searches every answer through the engine for a way to
   pay; the auto-payer's planner must find a plan whenever the search finds a payment, and its
   plan must cast the spell. A few minutes. Check that both tests pass (`2 passed`); a failure
   lists each board it got wrong (the spell, the permanents, the pool and the commander).
7. **Rules gaps:** `uv run python tools/gaps.py` lists every rule the engine doesn't implement
   yet. Check it matches what the milestone left for later (`docs/roadmap.md`).

## Optional, with the card data snapshot

With the Scryfall snapshot in `data/` (`docs/howto.md`, "Fetch or update the card data
snapshot"):

- `uv run python tools/card_excerpt.py tools/excerpts/basic_lands.json --check` and the same
  for `tools/excerpts/cards.json`: the committed excerpts still match the snapshot.
- `uv run python tools/coverage.py`: which cards of the target decks in `decks/` are
  implemented.
