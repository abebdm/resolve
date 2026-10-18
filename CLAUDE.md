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

## Current status

The repository structure and docs exist. **No engine code has been written yet.** The next
milestone is M0 (see the roadmap). Do not start a milestone unless the user asks.

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
7. **Every change ships with tests.** `pytest`, `ruff` and `pyright` must all pass.
8. **Unclear rules:** consult the pinned CR. Record the reasoning, with rule numbers, in a comment
   and in the PR description.
9. **Scope:**
   - implement only the cards and mechanics listed for the current milestone;
   - build cards from primitives;
   - a new primitive requires its own tests.
10. **Architecture changes need the user's sign-off** before code is written. If a design.md
    decision seems wrong, stop and raise it; don't work around it.
11. **Forge and XMage code is for reading only.** Never copy or translate it into this repo (licensing).

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
  `tests/cards/`, `tests/interactions/` and `tests/fuzz/`.
- When a design decision changes (with the user's OK), update `docs/design.md` in the same PR.
- Prefer clear, boring code over clever code. This engine will be read far more than written.
