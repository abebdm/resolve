# Resolve — Design

This document records the architecture of the Resolve rules engine and the reasons behind it.
It is authoritative. Changes require the project owner's sign-off and must be made in the same PR
as the code that depends on them.

---

## 1. Goals and non-goals

**Goals**

- Run complete games of Magic with rules accuracy matching the pinned Comprehensive Rules (CR).
- Formats, in priority order:
  1. Commander multiplayer
  2. 1v1 Commander
  3. Regular 1v1
- Make every intermediate state inspectable, so a UI can show the stack, pending triggers and
  choices at every point.
- Run on ordinary Windows PCs first and foremost: the players use Windows 10/11 with a current
  Python. Linux and macOS should also work, but Windows is the platform that must never break.
- Be a foundation for three future consumers, without engine changes:
  - a desktop UI
  - networked play between friends (no paid servers)
  - an AI player

**Non-goals (for now)**

- UI, networking and AI. They are built later, against the public API.
- Implementing every card. Coverage grows toward the target decks in `decks/`.
- Raw performance. Correctness first; performance is kept *possible* (see §15).

---

## 2. Authority and versioning

- **Rules:** the pinned CR text in `docs/rules/` (currently effective 2026-09-25).
- **Card data:** a pinned Scryfall bulk-data snapshot (Oracle cards and rulings), fetched by
  `tools/fetch_scryfall.py` into `data/` (gitignored). The snapshot date is recorded next to the CR
  version in `docs/rules/README.md`.
- The rules and the card data are updated **together and deliberately**, with a changelog entry, so
  a test never silently changes meaning.
- **Authority order:** CR, then official rulings, then everything else. Forge and XMage are useful
  references but have bugs of their own.

---

## 3. Public API

The engine exposes a small, stable surface (`resolve.engine`):

```python
state = new_game(config: GameConfig, decks: Sequence[Deck], seed: int) -> GameState

request = pending_decision(state) -> DecisionRequest | None   # None => game over
view    = view_for(state, player_id) -> PlayerView            # hidden info removed
submit(state, answer: DecisionAnswer) -> None                 # validates, then runs until the
                                                              # next decision or game end
```

A driver loop looks like:

```python
while (request := pending_decision(state)) is not None:
    agent = agents[request.player]
    answer = agent.decide(view_for(state, request.player), request)
    submit(state, answer)
```

Humans (via a UI), AIs, network peers and scripted test agents are all just `decide`
implementations.

**Inputs.** A `Deck` holds each card's Oracle data and card definitions, resolved from a decklist
by `build_deck(decklist, database, registry)`, which refuses unknown or unimplemented cards. Deck
`i` belongs to player `i`. `seed` is an integer in `[0, 2**64)`.

**Errors and the state** (`resolve.errors`):

- `InvalidAnswer`: the answer was rejected and **nothing changed**. The same decision is still
  pending.
- `NotImplementedRule`: the game reached a rule the engine doesn't implement. The state is left as
  it was at that point and must not be played further (`pending_decision` then raises
  `EngineError`). There is no rollback, which keeps `submit` cheap for AI search.
- `EngineError`: an engine bug or API misuse; the state must not be played further.
- `DeckError`: `new_game` or `build_deck` refused a deck.

**Concession** (104.3a) can happen at any time, not only by the player being asked something, so
it has its own entry point, `concede(state, player)`. The engine is always paused at a decision
(or the game is over), so a concession withdraws the pending request (its id goes stale), logs a
public `Conceded` record, makes the player lose and leave the game (800.4a), and runs the game
on: the task that was asking runs again and asks anew with a new id, or passes the decision to
whoever the rules name now (800.4h, 800.4j). `concede` raises `InvalidAnswer`, changing nothing,
if the game is over or the player already left.

---

## 4. Game state

`GameState` (`resolve.state.game`) is **pure data**. It contains:

- `config`: the `GameConfig` (format parameters; see §10), and the game's `seed`
- `players`: a list in **seating (clockwise) order**, with `players[i].id == i`. Each player has
  life, a mana pool (a list of `Mana` units, each with its type and source, 106.4) and their
  own library, hand and graveyard; counters, designations (monarch, etc.) and
  commander-damage tallies are added in later milestones. Turn order begins with
  `starting_player` and proceeds clockwise (103.1).
- `cards`: `dict[CardId, Card]`, one entry per physical card: its owner, its Oracle data
  (`CardData`, without rulings) and its card definitions, one per face
- `objects`: `dict[ObjectId, GameObject]` for every object in every zone
- zones: per-player library, hand, graveyard (on `Player`); shared `battlefield`, `stack`,
  `exile`, `command`. Zones are lists of ObjectIds; in every pile the **last element is the top**.
- `turn`: the turn in progress (`resolve.state.turn.TurnState`), or `None` before the first
  turn: its number, the active player, the phase and step (a main phase has no step, 505.2),
  the priority holder and the players who have passed in succession since the last action
  (117.4), and per-turn records (lands played; later spells cast, etc.). The turn's phases and
  steps are one sequence, `TURN_SEQUENCE` (500.1), that `TakeTurn` walks.
- `tasks`: the task stack (§5)
- `pending`: the current `DecisionRequest`, if any; `result`: the `GameResult` once the game is
  over
- `continuous_effects`, `replacement_effects` (from resolved spells and abilities; static abilities
  are derived from objects), added in M5-M6
- `pending_triggers`, `delayed_triggers`, added in M4
- `rng`: the engine's own PRNG (`resolve.state.rng.Rng`, §12), seeded at game creation
- `next_object_id`, `next_timestamp`, `next_request_id`
- `event_log`: the ordered record of everything that happened, with CR citations (§7)

**Identifiers** (`resolve.state.ids`) are `NewType` ints: `PlayerId` is the seat index;
`ObjectId`s are allocated from 1 and never reused, and a zone change gives a new one (400.7);
`CardId` names a physical card and is stable across zones (§8).

**Mutable state, immutable values.** `GameState`, `Player`, `GameObject` and tasks are mutable
`slots` dataclasses: tasks change the state in place, and AI search clones it with `deepcopy`.
Values that never change once created derive from `resolve.values.Immutable`: card data and
definitions, `Card`, `Zone`, `GameConfig`, events, log entries, decision requests, answer spaces
and answers, player views. They are frozen dataclasses holding only scalars, enums, tuples and
other `Immutable` values, and `copy`/`deepcopy` return them unchanged, so copies of a state share
them instead of copying every card's text. Agents only ever receive immutable values.

**Constraints**

- No lambdas, closures, generators, file handles, sets or other non-data values.
- **Card behavior is stored as data.** The registry is consulted once, when decks are built; the
  state then holds each card's `CardDefinition`s (declarative, immutable data). Behavior code
  lives in classes that definitions refer to by instance, never as functions. The state is
  therefore self-contained: `submit` needs no registry, and copies and pickles carry the
  definitions they were played with.
- Tasks and events refer to objects and players by ID, never by reference.
- The entire state must survive `copy.deepcopy` and `pickle` at any moment.
- All collections that are iterated use deterministic order (lists, or dicts with insertion order).
- `resolve.state.invariants` checks all of this at run time (`check_pure_data`,
  `check_immutable`, `check_invariants`); tests and the fuzz harness call it.

---

## 5. Engine loop and tasks

The engine is an explicit **task queue** (a stack of pending tasks stored in the state). This was
chosen over blocking callbacks and over Python generators because generators can't be copied or
pickled, which would make AI search and save/restore impossible.

- A **task** (`resolve.tasks.Task`) is a small dataclass with `run(state) -> TaskResult`. A result
  is one of:
  - `Done()`: pop the task.
  - `Push(tasks)`: pop the task and replace it with `tasks`, which run in order (`tasks[0]`
    first). A task that must continue after its sub-tasks puts itself last, as in
    `Push((child, self))`, having recorded its progress in its own fields.
  - `NeedDecision(player, kind, space, prompt, rules, source)`: the engine pauses. The task stays
    on top; the engine assigns the request id and stores the `DecisionRequest` in `pending`.
- Examples: `TakeTurn`, `RunStep`, `PriorityRound`, `CheckStateBasedActions`, `ApplyEvents`;
  later `CastSpell` (the 601.2 sequence), `ResolveTopOfStack`, `PutTriggersOnStack`,
  `DeclareAttackers`.
- **Resuming.** `submit()` validates the answer (§6), including the paused task's
  `check_answer(state, request, answer)`, which must change nothing. Only then does it log the
  answer, clear `pending` and call the same task's `resume(state, request, answer)`, whose result
  is handled like `run`'s. The loop then continues until a task returns `NeedDecision` or the game
  ends.
- A task keeps **all** of its progress in its fields, never in Python locals across calls, so a
  state copied or pickled mid-task resumes exactly as the original would.
- **Asking again.** A task's `run` must be safe to call again after it returned `NeedDecision`
  (a concession withdraws the request and runs the loop): it asks the same question again, or,
  if the player it asked has left the game, asks whoever must decide now. It never re-draws
  randomness it already drew. Tasks never touch
  `state.tasks` themselves; the loop checks this.
- The loop has a runaway budget (`MAX_TASKS_PER_RUN`) that raises `EngineError`. It catches engine
  bugs only; game loops are §13.

**Notes**

- **Mana abilities don't use the stack (605).** Activating one resolves immediately, including in
  the middle of casting a spell or paying a cost.
- **Special actions (116)** use no stack and are offered as priority choices. Examples: playing a
  land, turning a face-down creature face up, and similar.
- **Priority:** before a player receives priority, the engine performs state-based actions as a
  single event, repeating until none apply. It then puts waiting triggered abilities on the stack,
  APNAP-ordered with each controller choosing order among their own, and repeats both steps until
  stable (117.5, 704.3). Cleanup-step behavior follows 514.

---

## 6. Decisions

A `DecisionRequest` contains:

- the deciding player
- a `kind` (choose action at priority, choose targets, choose modes, choose X, pay costs,
  declare attackers, declare blockers, assign combat damage, order triggers, order
  replacement effects, choose a card name, mulligan, yes/no for "may", etc.)
- **options**, given in one of two forms:
  - an **enumerated list** where the set is finite and reasonably small
  - a **constrained space** where it isn't (an integer range for X, any card name, damage
    divisions, subsets with size bounds)
- enough context for a UI to explain the decision (the source object, the CR reference)

The kinds are `resolve.decisions.DecisionKind`. The answer spaces (`resolve.decisions.spaces`) are
independent of the kind:

| Space | Answer value | Valid when |
|---|---|---|
| `ChooseOne(options)` (enumerated) | `Pick(index)` | `0 <= index < len(options)` |
| `ChooseSubset(options, minimum, maximum)` | `PickMany(indices)` | strictly increasing indices, count within bounds |
| `ChooseOrder(options)` | `Order(permutation)` | a permutation of the option indices |
| `ChooseNumber(minimum, maximum or None)` | `Number(value)` | within bounds |
| `Distribute(recipients, total, minimum_each)` | `Amounts(amounts)` | one per recipient, each at least the minimum, adding up to the total (601.2d) |

Every outcome has exactly one valid answer (canonical forms), which helps AI search. Options are
typed (`PlayerOption`, `ObjectOption`, `NamedOption`, and the priority actions `PassOption`,
`PlayLandOption`, `ActivateAbilityOption`, `CastSpellOption`) so a UI can tell them apart. A priority request lists every
legal action, including ones the engine can't take yet, which raise `NotImplementedRule` when
chosen. A request contains only
what its deciding player may know; one decision is pending at a time, which matches the
sequential APNAP choices of 101.4.

**Rules**

- The engine validates every answer and rejects illegal ones. It never trusts the agent.
  Validation has two stages, neither of which changes anything: the answer must echo the pending
  request's id and player and lie in its space (`validate_answer`), then the asking task's
  `check_answer` applies the rules a space can't express.
- Enumerated options are what the future AI will search over, so prefer enumeration wherever
  practical.
- **Convenience lives outside the engine.** Mana auto-payment, auto-passing priority and "stops"
  belong in agent-side helpers. The engine always asks the full question; helpers may answer
  automatically.

---

## 7. Events and the effect pipeline

Every atomic change to the game is an **event** (`resolve.events.Event`): a frozen value naming
objects and players by ID and citing its CR rules. Examples: damage dealt, life changed, zone
change, counters added or removed, tap or untap, card drawn, player loses. Events are applied only
by the `ApplyEvents` task, which takes a set of simultaneous events through the pipeline below;
it is a task because ordering replacement effects needs decisions (616.1).

The pipeline for each event (or set of simultaneous events):

1. **Propose** the event.
2. **Apply replacement and prevention effects** (614–616). The affected player, or the controller of
   the affected object, chooses the order when several apply (616.1). Each effect applies at most
   once per event, with the documented exceptions (for example 903.9b).
3. **Apply** the modified event to the state.
4. **Log** it with CR citations, *as applied*: an event is proposed before its outcome is known
   ("player 1 draws a card"), and `apply` may return a copy recording what happened (which
   library object was drawn and the new hand object's ID). Each `LogEntry` holds an event or an
   `AnswerRecord` (an answered decision, from which replays are rebuilt), who may see it
   (`None` = everyone) and, for an entry hidden from some players, the `redacted` form they see
   instead (§9). Answers are visible only to their player; their public consequences are logged
   as events.
5. **Detect triggers.** Check triggered abilities against the event and add matches to
   `pending_triggers`. "Leaves the battlefield" and similar triggers "look back in time" using the
   pre-event state (603.10).

Effects that change how a permanent enters the battlefield are handled as part of the zone-change
event (614.1c–d, 614.12). Examples: entering tapped, entering with counters, and "as this enters,
choose…".

---

## 8. Object identity and characteristics

**Identity**

- An object that moves between zones becomes a **new object** with a new `ObjectId` and no memory
  of its previous existence (400.7, with its listed exceptions).
- A stable `CardId` tracks the physical card across zones. This is used for commander identity and
  commander damage (903.10a), and for "the card" references allowed by 400.7's exceptions.

**Characteristics**

- Characteristics are **computed, never stored as mutated values.** `characteristics(state, obj)`:
  1. starts from the card definition (or token, or copy, definition)
  2. applies all applicable continuous effects through the **layer system** (613): layers 1–7 with
     the 7a–7d sublayers
  3. orders effects within a layer by timestamp (613.7) and by the dependency system (613.8)
- Counters, status (tapped, flipped, face-down, phased) and attachments live on the object.
  Their effects on characteristics are applied in the appropriate layer.
- Results may be cached, with the cache invalidated on any state change. Correctness comes
  first: the cache is an optimization only, added when the benchmark asks for it. There is none
  yet (`resolve.effects.characteristics`, docs/decisions.md).

---

## 9. Hidden information and knowledge

- Each object records **which players know its identity**. Examples:
  - a card in hand: its owner
  - a scried card placed on top of the library: its owner
  - a revealed card: all players
  - a face-down permanent: its controller
- `view_for(state, player)` builds a `PlayerView` that includes only what that player may know.
  Hidden objects in hands appear as opaque placeholders with stable IDs.
- **Libraries appear only as a count** (later: plus the cards the viewer knows, at known
  positions). Library objects keep their IDs through shuffles (a shuffle isn't a zone change,
  400.7), so showing them would reveal where a once-seen card went, and the initial IDs follow
  decklist order. For the same reason, a log entry that would reveal a library object's ID to
  another player carries a redacted form for them (`Event.redacted`, `LogEntry.redacted`): a
  draw shows other players the new hand object but not the library object it came from, and
  cards put on the bottom of a library show only how many there were. An event that is public
  anyway may count library objects instead of naming them: a player leaving the game
  (`PlayerLeftGame`) names the objects that left from the other zones and counts the library.
- The library order is hidden from everyone, except where knowledge was gained (for example by scry).
- The event log is filtered per viewer by each entry's visibility.
- Agents (including the AI) only ever see `PlayerView`s. This is required for fair networked play and
  for AI with imperfect information.

---

## 10. Formats, multiplayer and Commander

**GameConfig parameters** (`resolve.state.config`):

- starting life (103.4; 40 in Commander, 103.4c)
- starting hand size (103.5)
- whether the commander rules apply, and the commander damage threshold (903.10a)

Deliberately **not** parameters:

- the player count: it is the number of decks (100.1)
- a mulligan rule: the CR has one procedure (103.5), and 103.5c applies to multiplayer games by
  rule
- deck-construction rules (size, singleton, color identity): added in M7 together with their
  enforcement, `validate_deck`; until then `new_game` doesn't check deck legality
- the range-of-influence option (801): Commander doesn't use it; added only if ever needed

This gives Commander multiplayer, 1v1 Commander and regular 1v1 from one engine.

**Multiplayer from day one:**

- Players are an ordered list; nothing assumes two players.
- APNAP order is used for simultaneous triggers and choices (101.4).
- **Leaving the game (800.4).** When a player leaves, the objects they own leave, effects giving
  them control of objects end, and the related consequences follow. This is designed in from the
  start; it is not retrofitted. Since M1: `LeaveGame` removes the objects a player owns (800.4a),
  priority passes on, turns continue without an active player (800.4j), players who left begin
  no turns (800.4k), and choices pass to the next player (800.4h). Objects whose controller
  isn't their owner raise `NotImplementedRule("800.4a")` until control-changing effects exist.
- **Conceding (104.3a)** is possible at any time, not only at priority.

**Commander (903):**

- the command zone
- casting the commander with commander tax
- color identity
- 21 combat damage from a single commander causes a loss (903.10a)
- the commander's zone-change options:
  - graveyard or exile → a state-based choice (903.9a)
  - hand or library → a replacement effect (903.9b)

Commander has no mulligan rule of its own: 103.5 applies, with 103.5c's free first mulligan in a
game that begins with more than two players (903.12g is for Brawl only).

---

## 11. Cards

**Data**

- Scryfall bulk Oracle data is loaded at startup from the local pinned snapshot. It provides name,
  mana cost, type line, Oracle text, power/toughness/loyalty, keywords, color identity and faces.
- Rulings are also loaded, and used to write tests.

**Behavior**

- A **card definition** is Python code registered under the exact card name (for multi-face cards,
  per face). It is assembled from **primitives**:
  - **effects:** damage, draw, destroy, exile, zone moves, create tokens, counters, life,
    sequences, choices
  - **targets and filters**
  - **triggers:** event matchers, intervening-if conditions (603.4), delayed triggers
  - **conditions:** predicates on the state
  - **costs, durations, static abilities, replacement effects**
  - a **keyword library** (flying, trample, ward, equip, ...). The goal is every keyword ability
    (CR 702) and keyword action (CR 701), not only those the target decks use. The roadmap's
    keyword table gives each one a milestone and a tier: evergreen and common keywords are built
    in the milestone where their rules live, the rest in M9 (keyword coverage). Every system is
    designed to leave room for all of them.
- Truly unusual cards may register a **custom** effect or task class under their name. The state
  still holds only data plus registry references.
- Definitions are declarative wherever possible, so the engine (and later the AI) can inspect them.

**Coverage**

- The registry knows which cards are implemented. `new_game` **refuses** decks containing
  unimplemented cards; nothing is approximated.
- `tools/coverage.py` reports, for any decklist, which cards are implemented and which are missing.

**Workflow for each card**

1. Read the Oracle text and rulings.
2. Write the definition from existing primitives, adding new primitives only when needed.
3. Write tests derived from the rulings.
4. Check Forge's script or XMage's class for corner cases.

New primitives are engine code and get careful review.

**Reference engines and licensing**

- **XMage (MIT).** It may be read freely:
  - to check card behavior
  - to guide the design of our primitive vocabulary (its ability and effect taxonomy reflects
    years of discovering which building blocks Magic needs)

  It is **not** mechanically translated. XMage cards call into a large framework that mutates game
  objects directly, which doesn't fit our pure-data state, event pipeline and object-identity
  model. If a substantial piece of logic is ever adapted from XMage, its MIT copyright notice goes
  in `THIRD_PARTY_NOTICES.md`.
- **Forge (GPL).** It is read for ideas only. Its code and card scripts are never copied or
  translated into this repo; doing so would likely make the project a GPL derivative.

---

## 12. Determinism, replays and saves

- The game is a pure function of (config, decks, seed, ordered list of inputs): the decision
  answers and the concessions, in the order they happened. Both are in the event log
  (`AnswerRecord`, `Conceded`); `resolve.agents.replay.replay` applies them to a new game, and
  raises `ReplayDiverged` when the new game asks something else, ends sooner, or has a
  conceding player already out of it.
- The **replay / save format** is exactly that, plus the engine version, CR version and card-data
  snapshot date. One format serves save files, bug reports and (later) the network lockstep
  protocol.
- Any randomness goes through `state.rng`. Nothing reads the clock. No iteration over sets.
- `state.rng` is the engine's own PRNG: xoshiro256**, seeded with splitmix64, with rejection
  sampling for bounded integers and Fisher-Yates shuffles. Python only guarantees that
  `random.Random.random()` stays the same across versions (`shuffle` and `randrange` may change),
  and replays, lockstep peers on other Python versions and a later port must reproduce every
  shuffle. Tests pin its outputs to the reference implementation.
- Fuzz tests verify that replaying a recorded game reproduces an identical state.

---

## 13. Loops

- Mandatory infinite loops end the game in a draw (104.4b).
- Optional loops involve the shortcut rules (732).
- At minimum the engine includes a **loop guard** (an action and iteration budget per priority
  pass), so it can never hang. Full shortcut negotiation comes later.

---

## 14. Testing strategy

**Scenario builder** (`tests/scenario.py`)

- Constructs exact board states (zones, life, turn, step, priority holder) without playing a game
  to reach them.
- Drives the game with scripted answers.

**Rule tests** (`tests/rules/`)

- Organized by CR section (`test_117_priority.py`, `test_613_layers.py`, …).

**Card tests** (`tests/cards/`)

- One module per card or card group, derived from official rulings.

**Interaction tests** (`tests/interactions/`)

- Notorious combinations and cross-card edge cases. Examples: layer dependencies, multiple
  replacement effects, commander zone changes.

**Fuzz tests** (`tests/fuzz/`)

- A random agent plays many full games, asserting:
  - no crashes
  - invariants hold (zone consistency, no object in two zones, life and damage bookkeeping, etc.)
  - replay determinism

**Other**

- A **benchmark**: random-agent games per second, tracked to notice regressions.
- CI runs `pytest`, `ruff` and `pyright` on every PR.

---

## 15. Performance stance

- Python is fine for playing games; it will be slow for large-scale AI simulation.
- The data-oriented, task-queue design keeps a later port of the hot paths (for example to Rust via
  PyO3) contained rather than a rewrite.
- Don't optimize prematurely. Do keep the benchmark, and avoid designs that make cloning
  pathologically expensive.

---

## 16. Open questions

- Exact representation of continuous effects that depend on changing information (e.g. "for as long
  as", characteristic-defining abilities). This is decided in M5.
- How much of 732 (shortcuts) is worth implementing before networked play exists.
- Undo/takeback support for casual play. It's cheap to do via snapshots, but it's a UI/agent
  concern; the engine needs no changes.
