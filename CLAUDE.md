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

## Current status

M0 is in progress. The data and tooling part is done: `resolve.data` (card data loader and
decklist parser), the card registry (`resolve.cards.registry`), `tools/fetch_scryfall.py`,
`tools/coverage.py` and CI. **The engine core has not been started.** Do not start a milestone
(or the rest of M0) unless the user asks.

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

- Run `uv run pytest`, `uv run ruff check .` and `uv run pyright`, all passing.
- State the results in the final message and the PR description: number of tests, and pass/fail.
- Never claim tests pass without having run them.

**Never weaken tests to get green**

- Don't delete, skip, `xfail`, or loosen an existing test to make a change pass.
- If a test seems wrong, stop and explain why with CR citations, and let the user decide.
- An unimplemented rule is tested as raising `NotImplementedRule`, not skipped silently.

**Use the shared helpers**

- Set up board states with the scenario builder (`tests/scenario.py`) rather than playing out turns
  to reach them.
- Drive choices with the scripted agent.
- Keep tests deterministic: fixed seeds, no reliance on timing.

## Documentation requirements

Future sessions start with no memory of this one. The repo's docs are how they get up to speed, so
keeping them accurate is part of the deliverable, like tests. A task is not done until the docs
below match the code.

**Every PR updates whichever of these it affects:**

- **"Current status" in this file.** Say which milestone is current, what's done, and what's next.
  It must never describe the repo as it used to be.
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

## Working style

- Work in small, milestone-scoped branches and PRs. Tick items off in `docs/roadmap.md` as they land.
- Tests live under `tests/rules/` (named by CR section, for example `test_117_priority.py`),
  `tests/cards/`, `tests/interactions/` and `tests/fuzz/`. Infrastructure has its own folders:
  `tests/data/` (card data and decklists), `tests/registry/` and `tests/tooling/` (the `tools/`
  scripts). Tests never need the real Scryfall snapshot; they use `tests/scryfall_fixtures.py`.
- When a design decision changes (with the user's OK), update `docs/design.md` in the same PR.
- Prefer clear, boring code over clever code. This engine will be read far more than written.
