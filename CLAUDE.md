# CLAUDE.md — Resolve

Resolve is a Magic: The Gathering **rules engine** written in Python. It runs complete games of
Commander (multiplayer and 1v1) and regular 1v1 Magic, with rules accuracy matching the
Comprehensive Rules. This repo is the **game processor only**. A desktop UI, networking
(friends, peer-to-peer or host-based) and an AI opponent will come later as separate consumers of
the engine's API, so nothing here may depend on them.

## Read first

**Read in full:**

- `docs/design.md`: the architecture. It is authoritative; follow it.
- The current milestone's section of `docs/roadmap.md`: its items and "done" criteria.
- `docs/plans/m2.md`, the approved plan of the current milestone, but only the parts its "How to
  use this plan" names for your step.

**Look up; don't read in full.** These are references, and most of each is irrelevant to any one
task. List a file's headings first (Grep for `^#{2,3} `), then read only the sections your task
touches. Read more when a section points you to another.

- `docs/rules/MagicCompRules-20260925.txt`: the pinned Comprehensive Rules (CR). Look rules up
  by number; do not rely on memory. Use `uv run python tools/rule.py <number>` (`704.5` prints
  the rule with its subrules, `704` a section outline, `--glossary "<term>"` a glossary entry);
  its "See also" line lists the rules the text cross-references, to look up next. Grep is the
  fallback (`^704\.5`). **Never read the whole file:** it is about 250,000 tokens, more than
  your context.
- The rest of `docs/roadmap.md`, including its **rules coverage map** (every numbered CR section,
  keyword ability and keyword action, with a milestone and a tier) and "What's built" (what each
  completed step added, and its modules). Grep for the rule number or keyword.
- `docs/torture-tests.md`: famously difficult cards, the rules each stresses and the milestone
  that must handle it. Read the rows that touch the systems you build or change.
- `docs/howto.md`: step-by-step recipes for recurring tasks. Read the recipe for your task and
  follow it.
- `docs/primitives.md`: the catalog of card-building primitives. Search it before writing a new
  one.
- `docs/decisions.md`: the log of smaller decisions, one dated heading each. Read the entries
  about the systems you touch.
- `docs/verification.md`: how the user verifies a milestone by hand (the `--thorough` runs).

## Current status

**Current milestone: M2 (Spells and the stack), in progress: the plan is approved
(`docs/plans/m2.md`); M2.0 to M2.8 are done (documentation, the rule defaults, mana costs and
characteristics, casting and resolving permanent spells, mana abilities beyond basic lands and
summoning sickness, the agent-side auto-payer, targets with last known information and the first
effects, modes and X, evergreen keywords and countering with Cryptic Command). M0 (Skeleton) and M1 (Turn structure) are complete.** What each completed
step built, and where, is in `docs/roadmap.md`, "What's built".

- **Known violations of rule 12:** none. Every default of `docs/plans/m2.md` §5.1 comes from a
  function in `resolve.rules.defaults` (how to add or change one: `docs/howto.md`).
- **Next:** M2.9 (cost reductions), then M2.10 onward.

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
12. **No hard-coded rule defaults.** Any value or procedure that a card or effect could change is
    never written as a fixed literal or assumption in engine code. That includes:
    - counts and limits (land plays, hand size, cards drawn, starting life, damage thresholds)
    - the turn's structure (which turns, phases and steps happen, and in what order)
    - who makes a decision and what each player can see
    - which zones a player may play or cast cards from
    - the default timing permissions

    Each one comes from a single function that reads the game state, cites its CR rule and is
    the one place effects plug into, even if no effect can modify it yet. When adding one, check
    the rules coverage map for the cards and rules that change it. A reviewer who finds a rule
    default hard-coded elsewhere treats it as a bug.
13. **Torture tests.** `docs/torture-tests.md` lists famously difficult cards. Each milestone's
    plan shows how its design handles the torture tests assigned to it and those assigned to
    later milestones that touch its systems. The milestone implements the ones assigned to it,
    each with rules tests.

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

**Rule defaults are tested through their seam**

- Each rule-default function (rule 12) gets a test that it returns the CR's default, and a
  **seam test**: replace the function with `monkeypatch` and check that the engine obeys it
  everywhere it applies (for example, two land plays allowed means a second land is offered).
  That proves the function is the one place effects plug into.
- M5, when effects can change these defaults, replaces the seam tests with tests using real
  effects.

**Invariants and determinism**

- Engine changes keep the fuzz tests passing:
  - random-agent games complete
  - invariants hold
  - the state round-trips through `deepcopy` and `pickle`
  - replaying a recorded game reproduces the identical state

**Run everything before finishing**

- Run `uv run pytest -q`, `uv run ruff check .` and `uv run pyright`, all passing. For an engine
  change, also run the quick fuzz run, `uv run python tools/fuzz.py`.
- While fixing failures, re-run only the failing tests (`uv run pytest -q --tb=short <test ids>`),
  then the full suite once at the end.
- State the results in the final message and the PR description: number of tests, and pass/fail.
  Give counts and the failures, never the whole output.
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

- **"Current status" in this file.** Say which milestone and step are current, any known rule
  violations, and what's next. It must never describe the repo as it used to be. Keep it short:
  this file is sent with every request an agent makes, so detail goes in
  `docs/roadmap.md`, "What's built", where the PR that completes a step adds what it built and
  its modules.
- **The "Status" paragraph in `README.md`.** A short, plain-language summary of the same thing for
  a human reader: which milestones are complete, what a game can do now, which cards are
  implemented, and what's next. Update it in the same PR as "Current status"; the two must never
  disagree.
- **`docs/roadmap.md`:** tick off completed items, and update the rules coverage map's rows
  for what the PR implements (and its torture-test status in `docs/torture-tests.md`).
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

## Keep your context small

Usage limits stop sessions mid-task, and a full context makes later work worse. None of this
skips a check; it changes how you find things, not what you verify.

- Read files by line range when you know where to look; Grep before reading a large file.
- Don't re-read a file you just edited: the edit would have failed if it hadn't applied.
- Keep command output short: quiet flags (`-q`), filtered output, and only the lines you need.
- Don't paste long logs, diffs or tool reports into PR descriptions or messages; summarize them
  and give the numbers.

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

- **Check the rules coverage map against the milestone's systems.** `docs/roadmap.md`'s rules
  coverage map lists every numbered CR section, keyword ability (CR 702) and keyword action
  (CR 701). Skim all of it, including rows this milestone won't implement. For each row that
  touches a system the milestone builds or changes, make sure the design leaves room for it,
  and say so in the plan. For example:
  - targeting must allow hexproof, shroud and protection;
  - combat damage must allow first strike, double strike, trample and deathtouch;
  - priority must allow split second;
  - casting must allow split cards, double-faced cards, adventures and casting from other zones.

  Adding a rule later is cheap; retrofitting a system that wasn't designed for it is not.
- **Follow the map's milestones and tiers.** Each row has the milestone where its rules live and
  a tier:
  - **evergreen/common** rows are implemented in that milestone;
  - **set mechanic** and **exotic** rows are implemented in M9 (rules coverage), unless a target
    deck needs one, in which case it's done in its own milestone;
  - **out of scope** rows (approved by the user, with a reason) aren't implemented.

  Test keywords and rules with fixture or excerpt cards where no target-deck card has them, and
  record each primitive in `docs/primitives.md`. If the plan finds a row in the wrong milestone
  or tier, propose moving it. Add the milestone's rows to its own checklist in the roadmap.
- **Check the torture tests** (`docs/torture-tests.md`, rule 13): show how the design handles
  those assigned to this milestone and those assigned to later milestones that touch its
  systems. Plan the implementation of those assigned to it.
- **Check for hard-coded rule defaults** (rule 12) in the code the milestone touches, and plan
  their removal.
- **Design ahead only provisionally.** A plan may add design-ahead sections to `docs/design.md`
  for later milestones, marked "Provisional: designed in Mx's plan, built in My". The later
  milestone's plan may revise them, with the user's sign-off.
- **Save the approved plan** to `docs/plans/<milestone>.md`, with the user's approval notes,
  before writing code, so later agents can resume it; delete it in the milestone's last PR.
  Keep it cheap to read: point to content that lives elsewhere (the coverage map, the torture
  tests) rather than copying it.

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
