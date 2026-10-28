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
- **"Not yet reachable"** (below the checklist) lists the expectations the thorough run can't
  meet yet, each with its reason and the milestone that makes it reachable; a run missing only
  those still passes. A milestone that makes one reachable moves it back into the checklist.
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
   an 8-core machine (about TIME_4 on 4 cores). It prints its settings first, a line every 10
   games, and the summary at the end. The seats cycle three kinds of player: random (exploring
   illegal actions), caster (plays a land, then casts every spell it may, paid by the
   auto-payer) and auto-pay (random, paid by the auto-payer). Check that:
   - the first line starts `Run: thorough preset;`, the summary says `100 games passed`, and
     nothing says `FAILED:`;
   - `Endings:` shows `concession` games and many `rules gap` games, with `draw x0`
     (`decked` and `life total` may be 0: see "Not yet reachable" below);
   - `Spells:` shows casts, resolutions and reversals above zero; `didn't resolve` and
     `countered` are only one or two each in 100 games (a spell whose target was removed in
     response; a Cancel or Cryptic Command cast by a caster seat with mana left open), so a 0
     in one of them, after an engine change, is worth a note rather than a failure: the rules
     and card tests cover both;
   - `Damage:` above zero (Fiery Confluence, Chandra's Ignition);
   - `Casts per card:` lists every card of `tools/excerpts/cards.json` but the lands (played,
     not cast), Repentant Blacksmith (kept out of the fuzz decks until M6, 702.16e) and the
     cards under "Not yet reachable"; a rarely cast card (Cryptic Command, with three blue
     symbols) may be missing in one run and is then worth a note, not a failure;
   - `Gaps:` lists only `508.1` and `903.8`;
   - `Turns per game:` reaches a maximum of several tens of turns, and `Played:` shows
     hundreds of lands and mana abilities, and some reversed mana ability activations
     (Selesnya Signet activated with nothing to pay its {1});
   - `Reversed casts:` shows, for the auto-pay seats (the casters and the auto-pay seats, which
     pay with the auto-payer), `0 of N payable` with N above zero (the auto-payer never
     reverses a cast it could pay), and for the random seats some payable casts reversed;
     most attempts of both kinds are reversed, because the agents try what they can't pay;
   - the last line gives the time; note it if it is much longer than the estimate above.
   The exact numbers depend on the engine and change from milestone to milestone; a run with the
   same code always prints the same numbers, except the timing. At the end of M2 the run
   printed: RESULT_LINES
5. **The quick run** (what agents run): `uv run python tools/fuzz.py`. Under a minute: 10 games,
   with the full checks every 10 answers. The same things to check as in step 4, for 10 games,
   except that most cards, `didn't resolve`, `countered` and damage may be missing from so few
   games.
6. **The auto-payer against brute force:**
   `uv run pytest tests/agents/test_autopay_brute_force.py --thorough`. It builds 20 000 random
   small boards and costs and, on each, searches every answer through the engine for a way to
   pay; the auto-payer's planner must find a plan whenever the search finds a payment, and its
   plan must complete the action. About 5 minutes. Check that both tests pass (`2 passed`); a failure
   lists each board it got wrong (the spell, the permanents, the pool and the commander).
7. **Rules gaps:** `uv run python tools/gaps.py` lists every rule the engine doesn't implement
   yet. Check it matches what the milestone left for later (`docs/roadmap.md`).

## Not yet reachable

The milestone check expects everything above. These expectations of the M2 plan the thorough
run can't meet yet; each says why and when it becomes reachable (docs/decisions.md,
2026-10-28, "M2.11"):

- **Endings by decking and by life total** (`decked`, `life total` may be 0), and much damage:
  most games stop at the 508.1 gap (declaring attackers) soon after a creature resolves, long
  before a library runs out or a life total reaches 0 from spells alone. **M3** implements
  attacking and removes 508.1 from the allowed gaps; its roadmap item restores these
  expectations.
- **Chandra's Ignition cast:** it needs a creature its caster controls as its target and five
  mana in a main phase, and a game with a creature on the battlefield stops at its
  controller's next combat (508.1). Reachable in **M3**, with the endings above.
- **Decimate cast:** it needs a target artifact, creature, enchantment and land, and no card in
  the fuzz decks is an enchantment. Reachable when the first enchantment card is implemented
  and joins the fuzz excerpt (the card and rules tests cover Decimate meanwhile).

## Optional, with the card data snapshot

With the Scryfall snapshot in `data/` (`docs/howto.md`, "Fetch or update the card data
snapshot"):

- `uv run python tools/card_excerpt.py tools/excerpts/basic_lands.json --check` and the same
  for `tools/excerpts/cards.json`: the committed excerpts still match the snapshot.
- `uv run python tools/coverage.py`: which cards of the target decks in `decks/` are
  implemented.
