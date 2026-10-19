# CLAUDE.md — Resolve

Resolve is a Magic: The Gathering **rules engine** written in Python. It runs complete games of
Commander (multiplayer and 1v1) and regular 1v1 Magic, with rules accuracy matching the
Comprehensive Rules. This repo is the **game processor only**. A desktop UI, networking
(friends, peer-to-peer or host-based) and an AI opponent will come later as separate consumers of
the engine's API, so nothing here may depend on them.

## Read first

- `docs/design.md`: the architecture. It is authoritative; follow it.
- `docs/roadmap.md`: milestones, "done" criteria, and which milestone is current.
- `docs/rules/MagicCompRules-20260925.txt`: the pinned Comprehensive Rules (CR). Look rules up here
  by number; do not rely on memory.
- `docs/howto.md`: step-by-step recipes for recurring tasks. Follow them.
- `docs/primitives.md`: the catalog of card-building primitives. Check it before writing a new
  one.
- `docs/decisions.md`: the log of smaller decisions made during implementation.
- `docs/verification.md`: how the user verifies a milestone by hand (the `--thorough` runs).

## Current status

**Current milestone: M2 (Spells and the stack), not started. M0 (Skeleton) and M1 (Turn
structure) are complete.**

- **Done (M0):**
  - Data and tooling: `resolve.data` (card data loader and decklist parser), the card registry
    and deck coverage (`resolve.cards.registry`, `resolve.cards.coverage`),
    `tools/fetch_scryfall.py`, `tools/coverage.py`, `tools/gaps.py` (lists every
    `NotImplementedRule`), CI, and the coverage audit (the Scryfall snapshot of 2026-10-17 is
    pinned).
  - The engine core: state types (`resolve.state`: `GameState`, `Player`, `GameObject`, zones,
    IDs, `GameConfig`, the engine's own PRNG, invariant and purity checks), the task loop and
    public API (`resolve.tasks`, `resolve.engine`: `new_game`, `pending_decision`, `view_for`,
    `submit`, `build_deck`), decision kinds, answer spaces and validation (`resolve.decisions`),
    events, the event pipeline (with stubbed replacement and trigger stages) and the event log
    (`resolve.events`), `NotImplementedRule` (`resolve.errors`), and zone moves (`move_object`,
    400.7).
  - Agents and test tooling: `resolve.agents` (the `Agent` protocol, the `play` driver,
    `RandomAgent`, `ScriptedAgent` with replays from the log, and the text renderer and
    `TextAgent` in `resolve.agents.text`); the scenario builder `tests/scenario.py`;
    `tools/play_cli.py`; and the fuzz harness `tools/fuzz.py` with `tests/fuzz/`.
- **Done (M1.1):** drawing (`resolve.engine.drawing.DrawCards`, `CardDrawn`, 121), opening hands
  and mulligans (`resolve.engine.mulligans.OpeningHands`, 103.5 and 103.5c), events logged as
  applied, and redacted log entries for other players (design.md §7, §9).
- **Done (M1.2):** turns, phases and steps (`resolve.state.turn`, `resolve.engine.turns`:
  `TakeTurn`, `RunStep`, 500-514, the 103.8a draw skip, 508.8), priority
  (`resolve.engine.priority.PriorityRound`, 117; casting is offered and raises
  `NotImplementedRule("601.2")` when chosen), the state-based actions 704.5a and 704.5b and the end
  of two-player games (`resolve.engine.sba`, 104.2a, 104.4a), discarding to hand size in cleanup
  (514.1) and 514.3a, type-line parsing (`resolve.data.types`, 205), the characteristics entry point
  without layers (`resolve.effects.characteristics`), turn info in views, and the scenario builder's
  `at(...)`. Two-player games with any decks play to a decking loss when every player passes.
- **Done (M1.3):** the five basic lands (`resolve.cards.definitions.basic_lands`), playing
  lands (305), the first primitives (`TapSelfCost`, `AddMana`, `ActivatedManaAbility`; 305.6
  intrinsic mana abilities added by `characteristics`), tapped status, the untap step (502.3),
  mana pools emptying as steps end (500.5), and mana abilities at priority (605.3a). Random
  agents finish two-player land-only games.
- **Done (M1.4):** vanilla creatures (`resolve.cards.definitions.vanilla_creatures`), power and
  toughness in `characteristics`, damage marked on permanents, the state-based actions 704.5f
  and 704.5g (with the owner ordering cards that reach a graveyard together, 404.3), and damage
  removal in cleanup (514.2).
- **Done (M1.5):** concession (`resolve.engine.concede`, 104.3a), leaving the game
  (`LeaveGame`, 800.4a, 800.4h, 800.4j, 800.4k), multiplayer endings (104.2a, 104.4a), re-entrant
  asking tasks, and replays of answers and concessions (`resolve.agents.replay`). The fuzz
  harness concedes at random and random agents finish 2- to 4-player land-only games.
- **Done (tooling, after M1):** `tools/fuzz.py` plays basic-land decks by default (from the
  committed excerpt `tools/excerpts/basic_lands.json`, written by `tools/card_excerpt.py`; no
  snapshot needed), with a quick default run (about 20 seconds) and a `--thorough` preset for
  the user's milestone verification (`docs/verification.md`), games in parallel (`--jobs`), and
  a summary of answers, turns, endings, lands and mana.
- **Next:** M2 (spells and the stack), starting with the casting process (601.2), which is the
  `NotImplementedRule("601.2")` gap every game with a nonland card can reach.

Do not start a milestone unless the user asks.

## Non-negotiable rules

1. **Accuracy over convenience. Never silently simplify a rule.** If something isn't implemented,
   raise `NotImplementedRule("<CR number>: <what>")` so the gap is loud.
2. **Cite CR numbers** in code comments, docstrings and event-log entries (for example `# 704.5g`).
3. **Authority order:** pinned CR, then official card rulings (Scryfall), then everything else.
   Forge and XMage are references, not ground truth.
4. **The engine is pure.** `src/resolve` never imports UI, networking or agent code (except
   `resolve.agents`, which depends on the engine, never the reverse). Agents see only per-player
   views.
5. **Game state is pure data.** No lambdas, closures, open files or generators stored in state. The
   whole state must survive `copy.deepcopy` and `pickle` at any moment, including mid-resolution.
6. **Determinism:**
   - all randomness uses the RNG stored in the state;
   - never iterate over a `set` of game objects (use dicts or sorted IDs);
   - never read the clock;
   - never depend on `id()` or hash ordering.
7. **Every change ships with tests, and the tests must be run.** A task is not done until the
   new tests exist and the full suite, `ruff` and `pyright` all pass. See "Testing requirements"
   below.
8. **Unclear rules:** consult the pinned CR. Record the reasoning, with rule numbers, in a comment
   and in the PR description.
9. **Scope:**
   - implement only the cards and mechanics listed for the current milestone;
   - build cards from primitives;
   - a new primitive requires its own tests.
10. **Architecture changes need the user's sign-off** before code is written. If a design.md
    decision seems wrong, stop and raise it; don't work around it.
11. **Reference engines:**
    - **XMage (MIT license).** Read it freely: to check how cards behave, and to inform the design
      of primitives (its ability and effect taxonomy is a useful guide). Don't mechanically
      translate its code; its architecture differs from ours (design.md §11). If a substantial
      piece of logic is ever adapted from XMage, add XMage's MIT copyright notice to
      `THIRD_PARTY_NOTICES.md` and say so in the PR.
    - **Forge (GPL license).** Read for ideas only. Never copy or translate its code or card
      scripts into this repo.

## Architecture in brief (details in docs/design.md)

- **Task-queue engine.** `GameState` holds a stack of pending tasks. The engine runs tasks until one
  needs a player decision, then stops and exposes a `DecisionRequest`. Answers come back through
  `submit()` and are validated.
- **Public API:** `new_game(config, decks, seed)`, `pending_decision(state)`,
  `view_for(state, player)`, `submit(state, answer)`.
- **Event pipeline.** Each event is proposed, then modified by replacement and prevention effects
  (616 ordering), then applied, logged, and checked for triggers. Before any player receives
  priority, the engine runs state-based actions and puts triggers on the stack (117.5 / 704.3).
- **Object identity.** An object that changes zones is a new object with a new ID (400.7). A stable
  card identity is tracked separately.
- **Characteristics are computed through the layer system (613), never stored as mutated values.**
- **Hidden information.** Each object records which players know its identity. Views are built from
  that.
- **Multiplayer from day one.** Players are a list in turn order, and nothing assumes two players.

## Cards

- Card data (Oracle text, types, costs, rulings) comes from a locally downloaded Scryfall bulk
  snapshot in `data/`. That snapshot is gitignored and never committed.
- Card behavior is a Python definition, registered by exact card name, in
  `src/resolve/cards/definitions/`. It is built from primitives in `cards/primitives/` and
  `cards/keywords/`. Truly unusual cards may register a custom effect or task class.
- Decks containing unimplemented cards are refused, never approximated.
- **Per-card workflow:**
  1. Read the Oracle text and rulings.
  2. Write the definition from existing primitives.
  3. Write tests derived from the rulings.
  4. Check Forge or XMage behavior for missed corner cases.
- The target decks are in `decks/`.

## Testing requirements

Tests are how this project proves rules accuracy. Treat them as part of the deliverable, not an
afterthought.

**Every change includes tests**

- Every new function, task, primitive, keyword, card or tool gets tests in the same PR. Write them
  alongside the code, or before it.
- **Bug fixes start with a failing test** that reproduces the bug, then the fix makes it pass.

**Derive expected behavior from the rules, not from the code**

- Expected outcomes come from the pinned CR text and official rulings, never from "what the code
  currently does".
- Each rules test cites the CR number it checks, in its name or docstring. For example,
  `test_704_5a_player_with_zero_life_loses`.
- When the CR or a ruling is ambiguous, write down the interpretation in the test's docstring.
- Never compute an expected value by calling the code under test. Write expected values out,
  worked from the rules.

**Tests first for rules and cards**

For any change that implements or alters game behavior (rules, primitives, keywords, cards):

1. Write the tests from the CR and the rulings before writing the implementation.
2. Run them and confirm each one **fails for the right reason**. "The player didn't lose" is the
   right reason. An import error or a missing function is not; add a stub that raises
   `NotImplementedRule` so the test reaches its assertion.
3. Then write the implementation and make the tests pass.
4. The PR description lists which tests were confirmed failing before the implementation, and
   names any test that couldn't be (with the reason).

Pure infrastructure (tooling, data loading, internal plumbing) may write tests alongside the code.

**Test what must happen and what must not**

- **Illegal actions are rejected:** casting at the wrong time, illegal targets, invalid decision
  answers.
- **Effects don't fire when they shouldn't:** a trigger whose condition isn't met, a replacement
  effect that doesn't apply.
- **Edge cases:**
  - zero, empty, and maximum values
  - objects changing zones mid-resolution (400.7)
  - simultaneous events
  - more than two players, wherever multiplayer could matter

**Card tests**

- Every implemented card gets tests in `tests/cards/`, including one for each relevant official
  ruling.

**Invariants and determinism**

- Engine changes keep the fuzz tests passing:
  - random-agent games complete
  - invariants hold
  - the state round-trips through `deepcopy` and `pickle`
  - replaying a recorded game reproduces the identical state

**Run everything before finishing**

- Run `uv run pytest`, `uv run ruff check .` and `uv run pyright`, all passing. For an engine
  change, also run the quick fuzz run, `uv run python tools/fuzz.py`.
- State the results in the final message and the PR description: number of tests, and pass/fail.
- Never claim tests pass without having run them.

**Quick runs for agents, thorough runs for the user's milestone checks**

- Any run whose length is a trade-off (how many games, seeds or iterations; how often an
  expensive check runs; how large the inputs are) gets two settings:
  - **a quick default**, for agents and day-to-day work: short (about a minute at most) but
    still meaningful, exercising what the current milestone implements, never a run that ends
    before doing anything;
  - **a `--thorough` preset**, for the user's manual verification at the end of each milestone:
    err on the side of coverage over speed (tens of minutes to a couple of hours is fine), with
    every check on wherever that is affordable.
- Agents run the quick default and run `--thorough` only when asked. Explicit options override
  either preset.
- Document both settings in `docs/howto.md`, and list every `--thorough` run, with what to look
  for in its output, in `docs/verification.md`. Tests check both presets' values and that the
  default run exercises the code (see `tests/fuzz/test_fuzz_summary.py`).

**Never weaken tests to get green**

- Don't delete, skip, `xfail`, or loosen an existing test to make a change pass.
- If a test seems wrong, stop and explain why with CR citations, and let the user decide.
- An unimplemented rule is tested as raising `NotImplementedRule`, not skipped silently.

**Independent test review before every PR that changes game behavior**

- Before opening the PR, run the `test-reviewer` subagent (`.claude/agents/test-reviewer.md`) on
  the branch. It starts with fresh context and checks the tests against the CR and rulings, not
  against the implementation.
- Address every finding: add the missing tests, or fix the wrong ones. Where you disagree with a
  finding, explain why with CR citations.
- Put the reviewer's verdict and how each finding was handled in the PR description.
- The user may also run a review in a separate session; the recipe is in `docs/howto.md`.

**Use the shared helpers**

- Set up board states with the scenario builder (`tests/scenario.py`) rather than playing out turns
  to reach them.
- Drive choices with the scripted agent (`run_script` in `tests/scenario.py`, or
  `resolve.agents.ScriptedAgent`).
- Keep tests deterministic: fixed seeds, no reliance on timing.

## Documentation requirements

Future sessions start with no memory of this one. The repo's docs are how they get up to speed, so
keeping them accurate is part of the deliverable, like tests. A task is not done until the docs
below match the code.

**Every PR updates whichever of these it affects:**

- **"Current status" in this file.** Say which milestone is current, what's done, and what's next.
  It must never describe the repo as it used to be.
- **The "Status" paragraph in `README.md`.** A short, plain-language summary of the same thing for
  a human reader: which milestones are complete, what a game can do now, which cards are
  implemented, and what's next. Update it in the same PR as "Current status"; the two must never
  disagree.
- **`docs/roadmap.md`:** tick off completed items.
- **`docs/primitives.md`:** every new or changed primitive, keyword or target filter gets an
  entry. An entry has:
  - its name and module
  - one line on what it does
  - the CR rules it implements
  - an example card that uses it

  Before writing a new primitive, search this catalog. Extend or reuse an existing one rather than
  creating a near-duplicate under a different name.
- **`docs/howto.md`:** when a recurring task is done for the first time, or its steps change, record
  the steps. Examples: adding a card, a primitive, a keyword, an event type or a decision kind;
  writing a scenario test.
- **`docs/decisions.md`:** add a dated entry for any judgment call that isn't obvious from the code.
  Examples: an interpretation of an ambiguous rule, a representation choice, a deliberate
  limitation. Each entry gives the decision, why it was made, and the CR rules involved. Large
  architectural changes still go in `docs/design.md`, with the user's sign-off.
- **`docs/design.md`:** whenever an approved design decision changes.
- **Docstrings:** public classes and functions get docstrings that cite the CR rules they implement.

**Keep docs lean and true**

- Document what a future session needs in order to work correctly. Don't narrate how the work went;
  that belongs in the PR description.
- Prefer generating over hand-writing. Anything that can be derived from the code (coverage,
  the list of `NotImplementedRule` gaps) should come from a tool, not a hand-maintained list.
- If a doc is wrong, fix it in the same PR. A stale doc is a bug.

## Commands

```bash
uv sync                    # create/refresh the environment
uv run pytest              # tests
uv run ruff check .        # lint
uv run ruff format .       # format
uv run pyright             # type check
```

## Work in checkpoints

A session can stop at any time: a usage limit, a closed app, a lost connection. Work must survive
that, and a fresh session must be able to resume it.

- **Commit and push to the working branch after each meaningful step,** not just at the end.
  Examples: a passing group of tests, a finished module, a doc update. Work-in-progress commits
  are fine on a branch. Never push to `main`.
- **Keep a progress note in `PROGRESS.md` at the repo root** while a task is under way. Update it
  with each checkpoint commit. It holds:
  - the task, and a link to the PR or prompt it came from
  - what's done
  - what's in progress, including any half-finished change and how far it got
  - what's next
  - decisions made so far that aren't yet in the docs
  - open questions for the user
- **Resuming:** if `PROGRESS.md` exists on the branch you're asked to work on, read it first and
  continue from it rather than starting over.
- **Before opening the PR,** move anything lasting from `PROGRESS.md` into the proper docs
  (decisions.md, howto.md, and so on), then delete `PROGRESS.md`. It must never reach `main`.

## Platform: Windows first

The players run Windows 10/11 with a current Python (3.14 at the time of writing). Everything
must work there first. CI runs the full suite on Windows and Linux with Python 3.12, 3.13 and
3.14, and a PR isn't done until every combination passes.

- Use `pathlib` for paths. Never build paths with `/` string concatenation, and never assume
  separators.
- Open text files with an explicit `encoding="utf-8"`. When reading, don't assume `\n` line
  endings: git on Windows may check files out with `\r\n`. When writing data that must be
  byte-identical, open in binary mode, or pass `newline="\n"`. Two checks enforce the encoding
  rule: `tests/tooling/test_portability_lint.py` (on every run), and in CI
  `PYTHONWARNDEFAULTENCODING=1`, which makes any use of the locale encoding fail a test. To run
  the second locally in PowerShell: `$env:PYTHONWARNDEFAULTENCODING = "1"; uv run pytest`.
- Files people make on Windows arrive with a byte order mark or as UTF-16 (Notepad, PowerShell
  5.1). Readers of user files accept those, as `load_decklist` does, and refuse other encodings
  loudly.
- A tool's output may be redirected, and redirected output on Windows is cp1252. Every tool's
  `if __name__ == "__main__":` block reconfigures `sys.stdout` to UTF-8 first (copy an existing
  tool); `tests/tooling/test_tool_output_encoding.py` checks each tool.
- No POSIX-only features: `fcntl`, `os.fork`, Unix signals, `/tmp`, shell pipelines,
  executable bits or shebang-only scripts. Run subprocesses with `sys.executable` and a list
  of arguments, never a shell string.
- File names must be valid on Windows and must not differ only in case. Windows file systems
  are case-insensitive, and names can't contain characters such as `: * ? " < > |`.
- **Commands in docs and PR descriptions must work in Windows PowerShell.** If a command
  differs, give the PowerShell form; Unix tools like `tail`, `grep` and `cat` don't exist there.
- **A test may never be skipped or loosened on Windows to get green.** That is weakening a test
  (see "Never weaken tests"). Fix the code instead.

## Planning a milestone

Every milestone starts with a plan the user approves (design, tests first, PR-sized steps).
When writing one:

- **Check the keywords against the milestone's systems.** Skim every keyword ability (CR 702)
  and keyword action (CR 701), including ones this milestone won't implement. For each that
  touches a system the milestone builds or changes, make sure the design leaves room for it,
  and say so in the plan. For example: targeting must allow hexproof, shroud and protection;
  combat damage must allow first strike, double strike, trample and deathtouch; priority must
  allow split second. Adding a keyword later is cheap; retrofitting a system that wasn't designed
  for it is not.
- **Follow the roadmap's keyword table.** `docs/roadmap.md` assigns every keyword to the
  milestone where its rules live. Implement the ones assigned to the current milestone, test
  them with fixture or excerpt cards where no target-deck card has them, and record each in
  `docs/primitives.md`. If the plan finds a keyword assigned to the wrong milestone, propose
  moving it.
- **Save the approved plan** to `docs/plans/<milestone>.md`, with the user's approval notes,
  before writing code, so later agents can resume it; delete it in the milestone's last PR.

## Working style

- Work in small, milestone-scoped branches and PRs. Tick items off in `docs/roadmap.md` as they land.
- Tests live under `tests/rules/` (named by CR section, for example `test_117_priority.py`),
  `tests/cards/`, `tests/interactions/` and `tests/fuzz/`. Infrastructure has its own folders:
  `tests/data/` (card data and decklists), `tests/registry/`, `tests/tooling/` (the `tools/`
  scripts), `tests/agents/`, and for the engine core `tests/state/`, `tests/engine/`,
  `tests/decisions/` and `tests/events/`. Tests never need the real Scryfall snapshot; they use
  `tests/scryfall_fixtures.py`, plus `tests/game_fixtures.py` (decks and games) and
  `tests/engine_support.py` (test-only tasks and events).
- When a design decision changes (with the user's OK), update `docs/design.md` in the same PR.
- Prefer clear, boring code over clever code. This engine will be read far more than written.
