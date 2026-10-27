# Resolve — Design

This document records the architecture of the Resolve rules engine and the reasons behind it.
It is authoritative. Changes require the project owner's sign-off and must be made in the same PR
as the code that depends on them. The one exception is §17: designs a milestone plan approved
ahead of their code, each marked provisional.

---

## 1. Goals and non-goals

**Goals**

- Run complete games of Magic with rules accuracy matching the pinned Comprehensive Rules (CR).
- Eventually handle every card that has ever been tournament-legal, with no shortcuts. A card
  is in scope if Scryfall lists it as legal, restricted or banned in at least one paper format.
  It is out only if it was never tournament-legal (acorn-stamped, silver-bordered, playtest
  cards, memorabilia, a casual variant's cards; docs/decisions.md, "Card scope: tournament
  legality"). The roadmap's rules coverage map gives every numbered CR section and keyword a
  milestone, and `docs/torture-tests.md` lists the hardest cards each milestone must handle.
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
- Implementing every card now. Card coverage grows toward the target decks in `decks/` first (M8),
  then toward every rule in the coverage map (M9).
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
if the game is over or the player already left; `concede(state, player, by=other)` is refused,
because the controller of a player can't make them concede (723.6).

---

## 4. Game state

*Designed ahead (provisional): stack objects and their choices (§17.5), counters and
designations (§17.15), choices stored on permanents (§17.13).*

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
  steps are data: a turn starts with the segments `defaults.turn_structure` gives it
  (`TURN_SEQUENCE`, 500.1) in `TurnState.segments`, and `TakeTurn` begins them one at a time, so
  effects can insert and remove phases and steps (500.8-500.10)
- `tasks`: the task stack (§5)
- `pending`: the current `DecisionRequest`, if any; `result`: the `GameResult` once the game is
  over
- `continuous_effects`, `replacement_effects` (from resolved spells and abilities; static abilities
  are derived from objects), added in M5-M6
- `pending_triggers`, `delayed_triggers`, added in M4
- `rng`: the engine's own PRNG (`resolve.state.rng.Rng`, §12), seeded at game creation
- `extra_turns` (the players who take extra turns next, the next one last, 500.7) and
  `turn_direction` (1: clockwise, 103.1)
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
- Examples: `TakeTurn`, `RunStep`, `PriorityRound`, `CheckStateBasedActions`, `ApplyEvents`,
  `CastSpell` (the 601.2 sequence), `ResolveTopOfStack`; later `PutTriggersOnStack`,
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
- **The turn frame (724).** `TakeTurn` stays on the task stack for the whole turn, so everything
  above it belongs to the turn in progress (`turn_frame_index`). Ending the turn removes those
  tasks and the remaining `TurnState.segments` and goes to the cleanup step; the effect itself is
  built in M9.

**Reversing illegal actions (733)**

When an action begins (casting a spell, activating a mana ability with a mana cost; from M4,
activating any ability or taking a special action), its task stores a **checkpoint** (`resolve.state.checkpoint`): a copy of every
restorable `GameState` field. It leaves out an explicit list (`NOT_RESTORED`):

- the event log;
- the task stack;
- `pending`;
- the ID, timestamp and request counters, which only ever grow;
- the RNG, which is never rewound, so a reversal can't be used to look at randomness.

If the action can't be completed (601.2e, 601.6, 601.2h, 118.3), the reversal goes as follows:

1. The player chooses which of the mana abilities they activated during the action to reverse
   (733.1; `REVERSE_MANA_ABILITIES`, not asked when none were): those activated while paying
   for one of them included (Selesnya Signet's {1}), in the order they began, and not those
   already reversed. The kept ones must include every ability whose mana paid for a kept one
   (checked by replaying the kept ones' mana on the pool at the checkpoint,
   `resolve.engine.reversal`).
2. The checkpoint is restored. A player who left the game meanwhile stays gone (800.4a).
3. The kept mana abilities aren't undone (733.1): their results stand exactly as they happened.
   The events each logged during its activation are made again as recorded (`Event.redo`), in
   order, without activating the ability again or logging the events twice; so an ability whose
   effect depended on the moment (Lion's Eye Diamond's "discard your hand", while the spell was on
   the stack) keeps that result. An event a mana ability can't cause yet raises
   `NotImplementedRule("733.1")` in `redo`. From M4, the triggers of kept abilities stand too
   (the redo re-establishes them); the undone action's don't. (Changed during M2.3, with the
   user's sign-off: the plan first replayed the kept abilities.)
4. Knowledge gained during the attempt is recorded (the card was seen on the stack), and a
   public `ActionReversed` is logged.

The player keeps priority, and the passes made before the attempt still count (733.2): the
priority task doesn't clear them when a cast or an activation begins; the cast clears them as it
completes (601.2i), and so does a completed mana ability activation. 733.1 forbids reversing library actions; 601.2h pays such costs last, and mana
abilities can't do them (605.1a), so finding one since the checkpoint is an `EngineError`.

The action's task holds its payment (`PayCosts`, §17.7) in a field rather than as a separate
task, because the reversal needs the mana abilities activated while paying. A mana ability with a
mana cost is such an action too: `ActivateManaAbility` takes its own checkpoint, embeds a
`PayCosts`, and is reversed the same way if its cost can't be paid, inside or outside a cast.

**Rule defaults (rule 12)**

Every value or procedure a card or effect could change comes from one function in
`resolve.rules.defaults` that reads the state, cites its rule and is the single place effects
plug in. The engine calls them through the module (`defaults.maximum_hand_size(state, player)`),
so a replacement is obeyed everywhere. They are listed, with their rules and defaults, in the
module's docstring; the recipe is in `docs/howto.md` ("Add or change a rule default"). Among them:

- `deciding_player(state, player)` (723.5): the loop maps the player a task asks through it, and
  the `DecisionRequest` carries both who answers and whose decision it is (§6);
- `knows_identity(state, obj, viewer)` (400.2, 402.3, 723.4): the one visibility check (§9);
- `turn_structure`, `is_skipped`, `next_turn` (500.1, 500.7, 500.11, 103.1, 800.4k), with
  `TurnState.segments` and `GameState.extra_turns` as data;
- `land_plays_allowed`, `land_play_options`, `cast_permissions`, `cast_options`,
  `has_sorcery_timing`, `may_cast_now` (305.2, 305.1, 601.3, 903.8, 117.1a), with legality
  questions asked through `resolve.rules.legality.allowed` (§17.2);
- `resolved_spell_destination` (608.2n).

---

## 6. Decisions

*Designed ahead (provisional): paying costs and `ChooseCounts` (§17.7); the rule for constrained
answer spaces (§17.8).*

A `DecisionRequest` contains:

- the deciding player (`player`, who answers) and `for_player`, whose decision it is by the rules.
  The task names the player the rules ask; the loop maps them through `deciding_player` (723.5),
  so they differ only while another player controls them
- a `kind` (choose action at priority, choose targets, choose modes, choose X, pay costs,
  choose a color, reverse mana abilities, declare attackers, declare blockers, assign combat damage, order triggers, order
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
| `ChooseCounts(options, maxima, total)` | `Amounts(amounts)` | one per option, each from 0 to its maximum, adding up to the total (601.2h; built in M2.2, §17.7) |

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

*Designed ahead (provisional): last known information and values (§17.9).*

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

- `defaults.knows_identity(state, obj, viewer)` is the one visibility check (400.2, 402.3); a
  player's controller also knows what they know (723.4), and sees the log entries they see.
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
- **Public game information an agent needs to act** is in the view, computed by the engine:
  each permanent's abilities (`ObjectView.abilities`: index, text, the mana part of the cost
  and the mana a mana ability adds now, 400.2), and the payments under way
  (`PlayerView.payments`, outermost first: payer, cost, purpose and the mana restrictions that
  allow spending on it, 601.2a, 601.2f-h, 106.6). Tasks report what they are paying through
  `Task.payment_under_way()`. The auto-payer (§6, "Convenience lives outside the engine") plans
  from these alone (M2.5; docs/decisions.md, 2026-10-22).
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

*Designed ahead (provisional): legality (§17.2), cast variants and permissions (§17.3), the cost
model (§17.6), typed words (§17.10), keywords and targeting (§17.11), resolution destinations
(§17.12), durations (§17.14), searching (§17.16), subgames and restarting (§17.17).*

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
    rules coverage map gives each one, and every numbered CR section, a milestone and a tier:
    evergreen and common rows are built in the milestone where their rules live, the rest in M9
    (rules coverage). Every system is designed to leave room for all of them (§17).
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

---

## 17. Designs approved ahead of their code

The M2 plan (`docs/plans/m2.md`, approved 2026-10-19) designed the systems below before
writing the code that needs them. That way every rule and keyword in the roadmap's rules coverage
map, and every torture test in `docs/torture-tests.md`, has a place to plug in.

**Every subsection here is provisional.** Each one names the milestone that builds it. That
milestone's plan may revise it, with the user's sign-off. When it's built, the text moves into
the section above it belongs to, and its provisional marker is removed. This is the one
exception to "the same PR as the code" at the top of this document (docs/decisions.md,
2026-10-19).

### 17.1 Rule defaults (rule 12)

Built in M2.1, and moved to §5 ("Rule defaults"), §6 and §9.

### 17.2 Legality: permissions and prohibitions (101.2)

*Provisional: designed in M2's plan; built in M2 (M2.1 to M2.8), extended in M3 to M5 and M9.
Each milestone's plan may revise it, with the user's sign-off. M2.1 built the skeleton
(`resolve.rules.legality`: `allowed`, `permissions`, `prohibitions`, and `PlayLand`, whose limit
305.2b is a prohibition); M2.3 casting (`CastAction`); M2.6 `TargetAction` and `DestroyAction`;
M2.8 `CounterAction` and the keyword prohibitions (shroud, hexproof, protection,
indestructible, "can't be countered").*

Every legality question is an `Action` value: casting, playing a land, activating, targeting,
countering, destroying; from M3 attacking and blocking; from M4 searching and special actions.
`allowed(state, action) -> Verdict` works in four steps:

1. It collects **permissions**: the rules' own (117.1a, 305.1, 601.3, 903.8) and those granted
   by effects.
2. It requires at least one.
3. It collects **prohibitions**:
   - hexproof, shroud and protection, as "can't be the target";
   - "can't be countered";
   - indestructible, as "can't be destroyed";
   - from M5, static abilities ("can't cast spells during your turn");
   - from M9, split second.
4. **Any applicable prohibition wins (101.2).** Adding or removing abilities is not a
   prohibition (101.2a).

601.3a-b's "consider choices made later" is a flag on the check. Event-level prohibitions
("can't gain life", "your life total can't change") are checked as events are proposed (M4).
Their order with replacement effects is settled in M6 (614).

### 17.3 Casting: cast variants and permissions (601.2)

*Provisional: designed in M2's plan; built in M2 (M2.3 onward). That milestone's plan may revise
it, with the user's sign-off. M2.3 built the variants, the permissions `FROM_HAND` and
`COMMANDER`, `cast_options`, `variant_characteristics` and `CastSpell` (601.2a, 601.2e-i);
variants other than normal raise their rules' gaps. M2.6 built the targets stage (601.2c: one
`CHOOSE_TARGETS` per instance of "target", `BecameTargets`); M2.7 the modes (601.2b, 700.2:
`CHOOSE_MODES`, a `ChooseOne` of `ModesOption` multisets) and X (`CHOOSE_X`, a `ChooseNumber`;
the total cost has its value). Division and hybrid arrive in M4 and M9.*

Every way of casting that changes a spell's characteristics is chosen **before** the card moves
to the stack, and castability is checked on the chosen characteristics only (601.3e):

- split cards and Rooms (709.3);
- modal double-faced cards (712.11b-c);
- casting transformed or converted (712.11a, d);
- adventures (715.3);
- omens (720.3);
- prototype (718.3);
- face down (708.4);
- fuse (702.102).

So a priority option is `CastSpellOption(card, variant, permission)`:

- **`CastVariant`**: normal, a half, fused, back face, an alternative (adventure, omen,
  prototype), or face down.
- **`CastPermission`**: the zone, the timing (sorcery, instant, "as though it had flash",
  "during this resolution", 608.2g), any alternative cost it requires (flashback, "without
  paying its mana cost", 118.9b), and where the spell goes as it leaves the stack.

On the stack, `characteristics` reads the spell's variant (709.3b, 712.8c, 712.8f, 715.3b,
720.3b, 718.3b). A permanent spell's choices pass to the permanent it becomes as
`GameObject.cast_record` (400.7d, 107.3m, 712.13, 718.3b, 709.5d).

`CastSpell` runs 601.2a-i as stages:

1. propose;
2. alternative and additional costs;
3. modes;
4. X;
5. hybrid and Phyrexian announcements;
6. targets;
7. division;
8. the 601.2e check;
9. total cost;
10. pay;
11. cast.

It never gives priority; its caller does (601.2i, 608.2g).

### 17.4 Reversing illegal actions (733)

Built in M2.3, and moved to §5 ("Reversing illegal actions").

### 17.5 Spells and abilities on the stack

*Provisional: designed in M2's plan; built in M2.3 (spells), M4 (abilities), M5 (copies). Each
milestone's plan may revise it, with the user's sign-off. M2.3 built `GameObject.spell` and
`CastChoices` (variant, permission, the zone cast from, total cost, mana spent) and
`ObjectView.spell`; M2.6 added the targets (`CastChoices.targets`, per instance of "target");
M2.7 added the modes (`CastChoices.modes`; the targets list each chosen mode's instances in
turn) and X (`CastChoices.x`).*

A spell is its card's object on the stack, with `GameObject.spell: CastChoices`. That record is
Immutable and replaced as each choice is made. It holds every decision 707.10 copies:

- the variant and permission;
- the zone the spell was cast from;
- the modes, each with its targets per instance of "target";
- X;
- divisions;
- alternative and additional costs;
- hybrid and Phyrexian announcements;
- the locked-in total cost and the mana spent.

Room is kept for three more kinds of stack object:

- A copy of a spell (707.10, 112.1a) is a card-less object with an equal record. Nothing may
  assume a stack object has a card.
- An ability on the stack (M4) is a card-less object with its source, ability and choices.
- A face-down spell is visible only to its controller (708.5).

### 17.6 The cost model (118, 601.2f-h)

*Provisional: designed in M2's plan; built in M2 (mana), M4 (other costs), M9 (hybrid,
Phyrexian, snow, payment alternatives). Each milestone's plan may revise it, with the user's
sign-off.*

- `ManaCost` holds every symbol of 107.4: colored, {C}, generic, {X}, hybrid, monocolored
  hybrid, Phyrexian and snow.
- A `Mana` unit records its type, its source, its restriction (106.6) and, for {S}, whether its
  source was snow.
- A total cost is a mana part plus **cost components**: tapping, sacrificing, discarding,
  exiling, paying life, removing counters, revealing and so on. Each component knows whether
  it can be paid, the choices it needs, its payment events and its 601.2h ordering class.
- 601.2f is a pipeline of ordered **cost modifiers**:
  1. the mana cost or an alternative cost;
  2. plus additional costs and increases;
  3. minus reductions, in the order the player chooses where it matters (118.7e, 118.7b-d);
  4. then effects that directly affect the total;
  5. then lock-in.
- Payment alternatives (convoke, improvise, delve, waterbend, assist, harmonize) are extra
  options in the 601.2g decision. They produce payment units usable only for that payment.
- "Spend mana as though it were any type" (118.14) modifies the payment check.

### 17.7 Paying costs and the `ChooseCounts` space

*Provisional: designed in M2's plan; built in M2.2 to M2.4. That milestone's plan may revise it,
with the user's sign-off. M2.3 built `PayCosts` (`resolve.engine.payment`) for generic, colored
and {C} mana; the action being paid for holds it in a field (§5, "Reversing illegal actions").
M2.4 added mana abilities' mana costs and restricted mana (106.6). M2.5 shows the payments
under way in the view (`PlayerView.payments`, §9), for the agent-side auto-payer
(`resolve.agents.autopay`).*

`PayCosts(payer, cost, purpose)` pays the costs of spells (`ForSpell`), of abilities
(`ForAbility`) and later of effects. Its decisions go through `deciding_player`, and it uses only
the payer's resources (723.5a).

- **601.2g:** an `ACTIVATE_MANA_ABILITIES` decision offers "pay" and every mana ability the
  payer can activate (605.3a), but not those being activated (605.3c: the ability whose cost is
  being paid, and those it is paying for).
- **601.2h:** a `PAY_COSTS` decision in the space `ChooseCounts(options, maxima, total)`,
  answered with `Amounts`: how many units of each class of identical mana to spend. A class of
  restricted mana that may not be spent on `purpose` (106.6) has a maximum of 0. It is not
  asked when only one answer pays. When none pays, the action is reversed (§5).
- A mana ability with a mana cost (Selesnya Signet) pays it with its own embedded `PayCosts`,
  which may activate other mana abilities in turn; `PayCosts.activations` holds the activation
  tasks, each with its own payment, so a reversal reaches them all.

Per-unit options would give two answers for one outcome, breaking §6's canonical answers. That
is why the space is new.

### 17.8 Constrained answer spaces

*Provisional: designed in M2's plan; `ChooseCounts` built in M2, `ChooseAssignment` in M3,
`ChooseCardName` in M4. Each milestone's plan may revise it, with the user's sign-off.*

**Rule.** A decision whose enumeration can grow without bound, or combinatorially, uses a
constrained space, never an enumerated list.

| Decision | Space |
|---|---|
| X, life to pay | `ChooseNumber` |
| targets, searches, proliferate | `ChooseSubset` |
| division | `Distribute` |
| orders | `ChooseOrder` |
| mana payment | `ChooseCounts` |
| attack and block declarations (each item mapped to one of its choices, with constraints) | `ChooseAssignment` |
| any card name, validated against the card data (201.4) | `ChooseCardName` |

Mode combinations stay enumerated, because the worst real cases are small.

### 17.9 Last known information and values

*Provisional: designed in M2's plan; built in M2.6, extended in M4 (look-back) and M5
(continuous values). Each milestone's plan may revise it, with the user's sign-off. M2.6 built
`LastKnown` (`resolve.state.last_known`; card-less objects record none until they exist),
`resolve.effects.evaluation` (`Context`, `information`, `evaluate`) for resolution, and the
values `Fixed` and `PowerOf`.*

**Last known information.** `move_object` records a `LastKnown` value for an object leaving the
battlefield or the stack, in `GameState.last_known`. The value holds the object's
characteristics, controller, owner, zone, status and damage. Entries are cleared when a player
is about to receive priority with an empty stack.

**Values.** Values are Immutable expressions: fixed numbers, X, power, toughness, counts, the
greatest power, arithmetic, and halving with rounding (107.1a). They are evaluated through one
function, whose context says when:

- on announcement (601.2b, 113.7a);
- on resolution, once per effect (608.2h, 611.2d);
- continuously, for static abilities (M5).

An object reference resolves to current information if the object is still where it was
expected, else to its last known information (608.2h). Negative amounts count as 0 (107.1b).

**Look-back.** From M4, effects that look back in time (603.10, 608.2i: "dealt damage this
turn", "spells cast this turn") read a history derived from the event log.

### 17.10 Definitions: "this object" and typed words (612)

*Provisional: designed in M2's plan; typed words built in M2.2, rewriting by text-changing
effects in M5. Each milestone's plan may revise it, with the user's sign-off.*

**Self-reference.** A definition refers to its own object with `ThisObject()`, never by name
(201.5).

**Typed words.** Every color word, land type and creature or other subtype in a definition is a
typed word: `ColorWord`, `LandTypeWord` or `SubtypeWord`. Card names are a separate `NameRef`
that no text change can rewrite (612.2).

**Rewriting.** A text-changing effect (layer 3, M5) applies a mapping of words through a generic
walk of the definition's Immutable fields (`rewrite_words`). Abilities granted by other effects
aren't rewritten (612.3).

### 17.11 Keywords, qualities and targeting

*Provisional: designed in M2's plan; built in M2.6 and M2.8; abilities' targets in M4 and 115.7
in M5. Each milestone's plan may revise it, with the user's sign-off. M2.6 built targeting
(`resolve.rules.targeting`, `legality.TargetAction`, `Targeter`); 115.5 is the rules' own
prohibition there. M2.8 built the keywords (`resolve.cards.keywords`: `Flash`, `Hexproof`,
`Shroud`, `Indestructible`, `Protection`, `has_keyword`) and the qualities but a player
(702.16k); their prohibitions are in `legality` (docs/decisions.md, 2026-10-27). A spell on the
stack keeps none of them (113.6).*

**Keywords and qualities.**

- Keyword abilities are `Ability` values in `resolve.cards.keywords`, read only through an
  object's computed characteristics, so granted keywords (M5) need no change.
- Protection and "hexproof from" take a **quality**: a color, multicolored, monocolored, a card
  type (702.16a), a subtype, everything (702.16j) or a player (702.16k).
- "From each color" and "from A and from B" become separate abilities (702.16g-h,
  702.11f-g).

**Targeting.** `target_problem(state, targeter, spec, candidate)` is the single legality check
for targets. It is built on `allowed` and used at 601.2c, at 608.2b, by 115.7 and by abilities.
In order, it checks:

1. the kind and zone (115.2, 115.4; for a player, that they are still in the game);
2. the target's filter;
3. that a spell doesn't target itself (115.5);
4. the prohibitions:
   - shroud;
   - hexproof, against opponents;
   - hexproof from a quality;
   - protection, from any controller.

The targeter is a spell or an ability, with its controller and the characteristics its
qualities are judged by: the spell's own, or the ability source's last known information
(113.7a).

### 17.12 Resolution and where a spell goes

*Provisional: designed in M2's plan; built in M2.3 and M2.6. That milestone's plan may revise it,
with the user's sign-off. M2.3 built `resolved_spell_destination` and the resolution of
permanent spells (608.3a); M2.6 the resolution of instants and sorceries (`ResolveSpell`; a spell
whose targets are all illegal goes to its owner's graveyard, 608.2b, without the destination
function) and the 120.3 table (`DamageDealt.apply`); M2.8 countering (`SpellCountered`) and
protection's damage gap (702.16e). Revised in M2.8 with the user's sign-off (docs/decisions.md,
2026-10-27): a countered spell doesn't use the destination function.*

**Where it goes.** `resolved_spell_destination(state, spell)` decides where an instant or sorcery
goes as it resolves (608.2n). The default is its owner's graveyard. It is where the destinations
that apply "as it resolves" plug in:

- adventures (exile with permission, 715.3d);
- omens (shuffled into the library, 720.3d);
- buyback (to the hand, 702.27a).

A countered spell (701.6a) and a spell that doesn't resolve (608.2b) always go to their owner's
graveyard, as ordinary zone changes through the event pipeline (`SpellCountered`,
`SpellDidNotResolve`: new objects, 400.7); a countered Adventure goes to the graveyard, not
exile. Replacement effects (Rest in Peace, flashback-style exile: M6) change those events, and
the resolution's, in the replacement stage.

**Damage.** One 120.3 results table reads the source's characteristics, using last known
information if the source is gone. Deathtouch, lifelink, infect, wither, toxic and protection's
prevention plug in there (until M6, damage protection would prevent raises the 702.16e gap at
the top of `DamageDealt.apply`).

### 17.13 Choices stored on permanents

*Provisional: designed in M2's plan; built in M2.3 (`cast_record`, built), M4 (links), M6
(entry choices). Each milestone's plan may revise it, with the user's sign-off.*

A permanent can carry three kinds of stored choice:

- `cast_record`: how its spell was cast (400.7d). Kicked, X (107.3m), the mana spent, prototyped,
  the face up, a Room half unlocked.
- `choices`: "as this enters, choose" (614.12, 607.2a). A color, a creature type, a player, a
  card name.
- links: the objects its linked abilities refer to (607: "exiled with this").

Which of these are copiable values is decided in M5 (707.2, 707.9).

### 17.14 Durations (611.2)

*Provisional: designed in M2's plan; built in M5. That milestone's plan may revise it, with the
user's sign-off.*

A continuous effect from a resolving spell or ability has a `Duration` value. Events in the
pipeline end it:

- the cleanup step (514.2);
- a player's next turn beginning;
- an object leaving a zone;
- the end of combat;
- a condition becoming false ("for as long as", 611.2b).

Durations are never checked ad hoc.

### 17.15 Counters and designations

*Provisional: designed in M2's plan; built in M4 (counters, object designations) and M7 (player
and game designations). Each milestone's plan may revise it, with the user's sign-off.*

**Counters.** `GameObject.counters` and `Player.counters` are `dict[CounterKind, int]` (122):
+1/+1, -1/-1, loyalty, poison, energy, experience, rad, ticket and the rest.

**Designations.** A typed dictionary on objects, players and the game holds every designation:

- the monarch, the initiative, the city's blessing;
- speed, day and night, the Ring-bearer, an enduring story;
- monstrous, renowned, saddled, suspected, harnessed, solved, prepared;
- goaded, recording who goaded and for how long;
- unlocked Room halves;
- phased out.

### 17.16 Searching hidden zones (701.23)

*Provisional: designed in M2's plan; built in M4. That milestone's plan may revise it, with the
user's sign-off.*

A `SEARCH` decision shows the searcher the whole zone in their private request. It is a
`ChooseSubset` whose bounds follow the instruction:

| Instruction | Bounds | Rule |
|---|---|---|
| names a quality ("a basic land card") | the searcher may find none | 701.23b |
| an undefined quality | nothing can be found | 701.23c |
| a plain quantity ("a card", "three cards") | exactly that many, or as many as there are | 701.23d |

Searches at the same time decide in APNAP order (701.23i). Which cards may be searched comes
from a rule-default function (701.23f, Aven Mindcensor). What the searcher learns about library
positions is recorded as knowledge (§9).

### 17.17 Subgames and restarting the game

*Provisional: designed in M2's plan; built in M9. That milestone's plan may revise it, with the
user's sign-off.*

**Subgames (729).** A subgame is a nested `GameState` held by a task of the main game. Its
decisions surface as the main game's pending decision.

**Restarting (727).** Restarting builds a new initial state from the cards, keeping those the
effect names.

Both fit the pure-data state. Nothing in the coverage map was found that the architecture can't
accommodate.
