# Decision log

Smaller decisions made during implementation that aren't obvious from the code: interpretations of
ambiguous rules, representation choices, deliberate limitations. Large architectural decisions live
in `docs/design.md` and need the user's sign-off; this log is for everything below that level.

Newest entries go at the top. Entries are never deleted. If a decision is reversed, add a new entry
that says so and mark the old one **Superseded by YYYY-MM-DD**.

## Entry format

```markdown
### YYYY-MM-DD: Short title
- **Decision:** what was decided.
- **Why:** the reasoning, including the alternatives considered.
- **Rules:** relevant CR numbers or rulings, if any.
- **Where:** the modules or files affected.
```

---

### 2026-10-18: Lands, mana abilities and mana pools
- **Decision:** playing a land is a `PlayLandOption` at priority (305.1-305.3, 116.2a) and one
  `LandPlayed` event: the land becomes a new, untapped permanent under its player's control
  (400.7, 110.5b) and `TurnState.lands_played` counts it (305.2a). The limit is one land per
  turn; no effect can add land plays yet.
- **Decision:** mana abilities are activated at priority with `ActivateAbilityOption(object,
  ability)`, where `ability` indexes the object's *computed* abilities (`characteristics`), so
  intrinsic abilities (305.6) are activatable like printed ones. Activation pays the costs as
  one `ApplyEvents`, then applies the effect as another (602.2b, 601.2h, 605.3b); nothing goes
  on the stack. Like a land play, it is an action: the same player receives priority again and
  `passed` starts over (117.3c, 117.4). Mana abilities during casting or payment (605.3a's other
  cases) come with casting in M2.
- **Decision:** a basic land type's mana ability isn't in any definition: `characteristics` adds
  "{T}: Add [mana symbol]" for each basic land type of a land, after its printed abilities, in
  type-line order (305.6). Basic land definitions therefore have no abilities: their Oracle text
  is reminder text.
- **Decision:** mana pools hold `Mana` units (type and source, 106.3), so 106.6 restrictions
  can attach to units later. As each step and main phase ends, every non-empty pool empties
  (`ManaPoolEmptied`, 500.5, 703.4q), in turn order. A player who passes announces their pool
  (`PriorityPassed.mana_in_pool`, 117.3d, 106.4b). Pools and tapped status are public in views.
- **Decision:** the untap step untaps every tapped permanent the active player controls as one
  `PermanentsUntapped` event (502.3); with nothing tapped, nothing is logged.
- **Decision:** `TapSelfCost` on a creature raises `NotImplementedRule("302.6")`: whether a
  creature has been controlled since its controller's most recent turn began isn't tracked
  yet. No M1 card has such an ability.
- **Decision:** primitives' base classes live in `resolve.cards.primitives.base`, which imports
  nothing from the engine, so `CardDefinition` (imported by `resolve.state.game`) can name
  `Ability` without an import cycle. `TapSelfCost` imports `characteristics` inside its method
  for the same reason.
- **Rules:** 106.3, 106.4, 106.4b, 107.5, 110.5b, 110.5d, 116.2a, 117.3c, 117.4, 118.3, 302.6,
  305.1-305.3, 305.6, 305.8, 500.5, 502.3, 602.2, 605.3a, 605.3b, 701.26, 703.4q.
- **Where:** `resolve.cards.primitives`, `resolve.cards.definitions.basic_lands`,
  `resolve.engine.priority`, `resolve.engine.mana`, `resolve.events.permanents`,
  `resolve.events.mana`, `resolve.state.mana`.

### 2026-10-18: Turns, steps and priority
- **Decision:** `TakeTurn` runs `TURN_SEQUENCE` (`resolve.state.turn`): every step, with a main
  phase as a segment whose step is `None` (505.2). Each segment is a `RunStep`: `StepBegan`
  (logged; "at the beginning of" triggers will match it, 500.6), turn-based actions, a
  `PriorityRound` except in untap and cleanup (117.3a, 502.4, 514.3), then the end of the step.
  Skipped steps don't begin at all (500.11): the starting player's first draw step in a game
  with exactly two seats (103.8a; a game that began with more players never skips, 103.8c,
  even after players leave), and declare blockers and combat damage whenever no attackers were
  declared (508.8), which is always until M3 because declaring attackers raises
  `NotImplementedRule("508.1")` whenever the active player controls a creature. The turn after
  cleanup belongs to the next player in turn order still in the game.
- **Decision:** the priority holder (`TurnState.priority`) and the players who passed in
  succession (`TurnState.passed`) are procedural pointers kept by `PriorityRound`, not events.
  `PriorityPassed` is logged as the record of each pass but changes nothing. They live in the
  state, not in the task, so views, invariants and the scenario builder can read and set them.
- **Decision:** each time a player would receive priority, `CheckStateBasedActions` runs first
  (117.5, 704.3), also before the next player after a pass. The step ends when every player
  still in the game has passed in succession with an empty stack; with an object on the stack
  the game stops at `NotImplementedRule("608.1")` (M2).
- **Decision:** legal actions the engine can't take yet are offered and raise
  `NotImplementedRule` when chosen (plan ★7): playing a land (305.1) until M1.3 (now done) and
  casting a spell (601.2) until M2. Hiding them would silently shrink the set of legal actions an AI
  searches. A player who controls a land with a basic land type would have its intrinsic mana
  ability (305.6, 117.1d) as an option, so building that player's options raises
  `NotImplementedRule("305.6")` until M1.3. Options are listed pass first, then hand cards in
  hand order, then commanders in the command zone (903.8).
- **Decision:** cast timing (117.1a): an instant whenever the player has priority; any other
  spell type of 205.2a that is cast (artifact, battle, creature, enchantment, planeswalker,
  sorcery; kindred through its other type, 308.1) only in the player's own main phase with an
  empty stack. A land is never cast (305.9). Flash can't exist yet (no definition has
  abilities). Whether the spell's cost could be paid is part of 601.2 and isn't checked.
- **Decision:** every multiplayer game uses the attack multiple players option (plan ★6), so the
  beginning of combat has no 507.1 choice: all the active player's opponents are defending
  players (802.2). It is Commander's default multiplayer setup (903.2), and a Free-for-All game
  must use one of the attack options (806.2b). It is a deliberate non-parameter, like the
  mulligan rule.
- **Why:** a step is a value (phase and step) rather than a task per step so that later extra
  steps and phases (500.7-500.10) can be inserted into one sequence; the scenario builder can
  then resume a turn at any segment.
- **Rules:** 103.8, 500-514, 117.1-117.5, 802.2, 806.2b, 903.2, 903.8.
- **Where:** `resolve.state.turn`, `resolve.engine.turns`, `resolve.engine.priority`,
  `resolve.events.turn`.

### 2026-10-18: State-based actions 704.5a and 704.5b, and losing
- **Decision:** `state_based_actions(state)` checks every condition before anything happens,
  and `CheckStateBasedActions` applies all the results as one `ApplyEvents` (704.3), repeating
  until a check finds nothing. A loss is `PlayerLost`, which sets `Player.lost` and clears the
  player's empty-draw record. `drew_from_empty_library` is cleared only by the loss: a player
  with the flag set always loses at the next check, so "since the last time state-based actions
  were checked" (704.5b) needs no separate clearing. A player who lost has left the game
  (104.5): `players_in_game` and `next_in_turn_order` skip them.
- **Decision:** after a loss `EndCheck` ends the game when at most one player is left: that
  player wins (104.2a), and if none is left the game is a draw (104.4a). A loss that leaves two
  or more players in the game raises `NotImplementedRule("800.4a")` until M1.5 implements
  leaving the game. Because the check runs after the whole simultaneous event, two players of
  three losing together leaves one winner, not a gap.
- **Rules:** 104.2a, 104.4a, 104.5, 117.5, 121.4, 704.3, 704.5a, 704.5b, 800.4a.
- **Where:** `resolve.engine.sba`, `resolve.events.game.PlayerLost`.

### 2026-10-18: Cleanup: discarding to hand size
- **Decision:** 514.1 asks the active player `DISCARD` (a `ChooseSubset` of exactly the excess)
  when their hand holds more than seven cards. The maximum hand size is seven (402.2) whatever
  the starting hand size. When two or more cards are discarded, their owner then orders them in
  the graveyard (404.3) with `ORDER_CARDS`, listed top to bottom; a single card asks no order.
  The cards are discarded together (one `ApplyEvents` of `CardDiscarded` events, bottom card
  first). Discards are public. 514.2 has nothing to remove until damage exists (M1.4). 514.3a is
  implemented: if state-based actions would be performed in cleanup, the active player receives
  priority and another cleanup step follows. Until M1.4 the only possible state-based actions
  end the game (tested: a player at 0 life loses in that cleanup step, after the discard); the
  path where priority and a second cleanup follow is tested in M1.4.
- **Rules:** 402.2, 404.3, 514.1-514.3a, 701.9a, 701.9b.
- **Where:** `resolve.engine.turns.DiscardToHandSize`, `RunStep`.

### 2026-10-18: Characteristics without layers, and type lines
- **Decision:** `resolve.effects.characteristics.characteristics(state, obj)` is the one place
  the engine reads an object's name and types. It starts from the printed face and applies no
  continuous effects (none can exist until M5). It isn't cached: design.md §8 allows a cache,
  but invalidation bugs would be correctness bugs and nothing is slow yet. Transforming and
  modal double-faced cards use their front face (712.8a, 712.8c, 712.8d); any other multi-faced
  layout raises `NotImplementedRule("109.3")` when its characteristics are needed (split 709.4,
  flip 710.1, adventurer 715.4, meld 712.4 all have their own rules).
- **Decision:** type lines are parsed when card data is built (`CardFace.types`). An unreadable
  type line (Un-set joke types) doesn't stop the database from loading (binding change 1): the
  face's `types` is `None`, `CardData.type_line_problems` explains why, and the card is refused
  where it would be used: `DeckCard` (so `build_deck`, `new_game` and the scenario builder) and
  the coverage report (`UNREADABLE`, listed in its own section; the tool exits with 1).
  "Time Lord" is the only two-word creature type (205.3m); a plane's subtype is the whole phrase
  after the dash (205.3b). Supertypes must come before card types (205.4a).
- **Rules:** 109.3, 205, 709.4, 712.8.
- **Where:** `resolve.effects.characteristics`, `resolve.data.types`, `resolve.data.cards`,
  `resolve.cards.coverage`, `tools/coverage.py`.

### 2026-10-18: Tests for long random games
- **Decision:** the fuzz tests add `PatientAgent` (`tests/engine_support.py`): a random agent
  that passes priority 31 times in 32, so random games reach later turns (draws, discards,
  decking) instead of stopping at the first offered gap. Only some long games run the copy and
  invalid-answer checks, which are slow on long logs. The broad fuzz test
  (`test_random_agent_games_complete_with_every_check_passing`) uses decks of 7 to 11 cards,
  each with an elf, and one empty deck in some games: with 6 or fewer cards every player drew
  from an empty library during 103.5 and every game ended at the first state-based-action
  check, before any priority. When every deck has 8 or more cards it asserts that priority
  was asked, and it counts every object a player owns, in every zone. `ALLOWED_GAPS` was
  305.1, 601.2 and 800.4a in M1.2; M1.3 removed 305.1.
- **Rules:** none.
- **Where:** `tests/fuzz/test_fuzz.py`, `tools/fuzz.py`.

### 2026-10-18: Opening hands and mulligans
- **Decision:** `OpeningHands` follows 103.5 literally. Opening hands are drawn one card at a time,
  the starting player first, then the others in turn order (121.2c, 101.4e). The starting player
  declares first, then each other player in turn order (`MULLIGAN`, options `keep` and
  `mulligan`); declarations are public events (101.4b). Once all have declared, every player who
  chose to mulligan shuffles their hand into their library (one `HandShuffledIntoLibrary` event
  each, together), draws a new hand (121.2c order), and then, in APNAP order (101.4), chooses
  which cards to put on the bottom (`PUT_ON_BOTTOM`) and their order (`ORDER_CARDS`, listed
  **top to bottom**); the cards then go to the bottom together. A game "begins with more than two
  players" (100.1b, 103.5c) when it has more than two seats; seats are never removed. "A player
  can take mulligans until their opening hand would be zero cards, after which they may not take
  further mulligans" is read literally, by cards: another mulligan is allowed while the player's
  hand holds at least one card. The mulligan that leaves zero cards is allowed, and the player
  then keeps without being asked. With seven-card hands that is seven mulligans (eight with
  103.5c); a short library reaches zero cards sooner, and a player whose library was empty is
  never asked. A player who must put every card of their hand on the bottom is asked only for
  the order. Cards put on
  the bottom stay known to their owner (`known_to`) until the next shuffle. After the mulligans,
  103.6 has nothing to do (no definition can have such an ability), and the game stops at
  `NotImplementedRule("103.8: ...")` until the turn structure exists.
- **Why:** 103.5 puts the bottoming inside "to take a mulligan", so it happens each time, not when
  keeping. "After which they may not take further mulligans" places the limit after the zero-card
  hand. The first version counted mulligans against the starting hand size instead; the test
  review pointed out that the text speaks of the hand's cards, which differs for short libraries. **Questions with a single possible answer are not asked** (a forced keep, which cards go
  to the bottom when all must); priority is the exception and is always asked, because passing
  automatically is an agent's convenience (design.md §6). Commander has no mulligan rule of its
  own (the user approved removing "Commander mulligan rules" from design.md §10 and roadmap M7).
- **Rules:** 100.1a, 100.1b, 101.4, 101.4b, 101.4e, 103.5, 103.5c, 121.2c, 400.2, 400.7, 701.24a.
- **Where:** `src/resolve/engine/mulligans.py`, `src/resolve/events/cards.py`,
  `src/resolve/engine/start.py`, `tests/rules/test_103_5_mulligans.py`.

### 2026-10-18: Drawing, events logged as applied, and redacted log entries
- **Decision:** `DrawCards(player, count, rules)` makes one `CardDrawn` event per card (121.2,
  so replacement effects will apply per draw, 121.6b). An event is proposed without its outcome
  and `Event.apply` may return a copy recording it (the drawn library object, the new hand
  object); the pipeline logs that applied form. Drawing from an empty library draws nothing,
  sets `Player.drew_from_empty_library` (cleared by the state-based action check, 704.5b;
  **superseded by 2026-10-18 "State-based actions 704.5a and 704.5b, and losing"**: only the
  loss clears it) and
  adds 121.4 to the event's rules. A `LogEntry` hidden from some players may carry a `redacted`
  form (`Event.redacted()`), which `view_for` shows to the others with `visible_to=None`
  (`LogEntry.shown_to`). A draw is fully visible only to the drawer; others see the new hand
  object's ID but not the library object's. `CardsPutOnBottom` shows others only the count.
  `HandShuffledIntoLibrary` is public: it names hand objects, whose IDs everyone already sees.
  `move_object(..., bottom=True)` puts the new object at the bottom of a pile.
- **Why:** design.md §9 required log redaction to be designed with drawing: library object IDs
  survive shuffles, so revealing one tells where a card went. One entry per event with two forms
  was chosen over two separate entries so that each event keeps one index and one trigger
  check. Hand placeholder IDs are already public in views (design.md §9), so showing the new hand
  object reveals nothing more. Returning the applied event keeps events immutable values while
  letting the log say which objects were involved, which the UI and the redaction need.
- **Rules:** 121.1, 121.2, 121.4, 121.6b, 400.7, 401.2, 402.3, 704.5b; design.md §7, §9.
- **Where:** `src/resolve/events/base.py`, `src/resolve/events/pipeline.py`,
  `src/resolve/events/cards.py`, `src/resolve/engine/drawing.py`, `src/resolve/engine/view.py`,
  `src/resolve/state/game.py`, `tools/fuzz.py` (the view oracle shows redacted forms and fails if
  a redacted draw or bottoming still names cards).

### 2026-10-18: Windows first: the CI matrix and the encoding checks
- **Decision:** CI runs ruff, pyright and pytest on `windows-latest` and `ubuntu-latest` with
  Python 3.12, 3.13 and 3.14 (supersedes the CI part of "Tooling: uv lockfile, pyright from a
  wheel, CI on two Pythons"). Every text file is opened with an explicit encoding, UTF-8 unless
  there is a reason. Two checks enforce it: `tests/tooling/test_portability_lint.py` scans
  `src`, `tools` and `tests` for text I/O without an encoding (also shell-string subprocesses,
  POSIX-only modules and calls, and `/tmp`), and CI sets `PYTHONWARNDEFAULTENCODING=1` while
  `pyproject.toml` turns `EncodingWarning` into a test failure. There is no `.gitattributes`:
  code must read `\r\n` and `\n` alike, and tests feed it `\r\n` explicitly.
- **Why:** Python 3.12 to 3.14 on Windows default to the ANSI code page (cp1252) for files and
  redirected output; UTF-8 becomes the default only in 3.15 (PEP 686). PR #11's Windows jobs
  failed exactly this way: a test wrote the rules README with `write_text()` and no encoding
  (`©` became byte 0xa9) and the tool read it as UTF-8. The scan runs on every platform and
  every local `uv run pytest`; the warning catches calls a scan can't see. Running in UTF-8 mode
  (`PYTHONUTF8=1`) was rejected: it would hide the bug from CI while players, who don't run in
  that mode, still hit it. Ruff's `PLW1514` was rejected: it is preview-only and found none of
  the 15 offending calls (it can't tell that `readme` is a `Path`).
- **Where:** `.github/workflows/ci.yml`, `pyproject.toml`, `tests/tooling/test_portability_lint.py`.

### 2026-10-18: Tools write UTF-8 output and LF files
- **Decision:** each tool's `__main__` block reconfigures `sys.stdout` to UTF-8 before calling
  `main()`. `tools/fetch_scryfall.py` writes the rules README and `snapshot.json` with
  `newline="\n"`. Standard input and standard error are left alone.
- **Why:** output redirected to a file or pipe on Windows is encoded as cp1252, which has no
  `−` (U+2212, the minus sign of planeswalker abilities) and nothing outside Western European
  scripts; `coverage.py --oracle > report.txt` crashed halfway. A console already gets UTF-8
  (PEP 528), so this changes only redirected output, and matches what Python 3.15 will do.
  `errors="replace"` was rejected because it silently changes the text. The README is tracked
  by git, so the tool writes the same bytes on every platform. Standard error already escapes
  what it can't encode (`backslashreplace`), and the terminal player's input is ASCII.
- **Where:** `tools/*.py`, `tests/tooling/test_tool_output_encoding.py` (probes every tool),
  `tests/tooling/test_coverage_tool.py`, `tests/tooling/test_fetch_scryfall_tool.py`.

### 2026-10-18: Decklist and source file encodings
- **Decision:** `load_decklist` reads UTF-8, with or without a byte order mark, and UTF-16 with
  a byte order mark. Anything else is a `DecklistError` naming the file. `tools/gaps.py` parses
  source files from their bytes, so it decodes them as Python does (BOM, PEP 263 declarations).
- **Why:** these are what Windows editors and shells write: Notepad and PowerShell 5.1's
  `Out-File -Encoding utf8` add a UTF-8 byte order mark, and PowerShell 5.1's `>` writes UTF-16.
  Before, a BOM made the first line unreadable and UTF-16 crashed with a `UnicodeDecodeError`.
  A file saved as "ANSI" is refused rather than guessed at: the same bytes are different card
  names in different code pages (non-negotiable rule 1: accuracy over convenience).
- **Where:** `src/resolve/data/decklist.py`, `tools/gaps.py`.

### 2026-10-18: The fuzz harness
- **Decision:** the harness is `tools/fuzz.py` (`fuzz_run`, `fuzz_game`, `state_problems`,
  `invalid_answers`), tested and used by `tests/fuzz/test_fuzz.py` (imported as `tools.fuzz`,
  like `tools.coverage`). Before every answer it checks invariants, purity, and every player's
  view against an oracle written out from the rules, not from the engine's `is_known_to`:
  immutable; the request only in the decider's view; life, library counts (401.2), the objects
  of every hand, graveyard and shared zone in order (402.3, 404.2); card names exactly where
  the viewer may know them (400.2, 402.3, 404.2, 406.3); and exactly the log entries visible to
  the viewer, with answers visible only to their player. It checks that `deepcopy` and `pickle`
  give equal states, and that answers for another request or from another player (carrying the
  agent's own, valid value, so only the id or player is wrong), of the wrong type or outside
  the space are rejected without changing anything. It then submits the random answer to the state, a deep
  copy and a pickled copy, which must end the same way and in equal states. A rejected random
  answer must change nothing, and the agent answers again; 100 rejections in a row
  (`MAX_ATTEMPTS`) or 10,000 accepted answers (`MAX_ANSWERS`) are failures. At the end the game
  is replayed from its start with `ScriptedAgent.from_log` and must reproduce the identical
  state. `NotImplementedRule` ends a game only for a rule in `allowed_gaps` (default `("103.5",)`,
  the end of an M0 game); any other exception is a `FuzzFailure` naming the seed and a command
  that reproduces it. Seat `i` is played by `RandomAgent(seed + i)`. The command line cycles
  player counts 2-6 and both formats, gives seat `i` of game seed `s` deck
  `(s + i) % len(decks)` so a failure reproduces from its seed alone, and prints games per
  second; the number isn't stored anywhere yet. Every check relies on `==` between states, so
  `tests/state/test_state_equality.py` forbids `compare=False` fields, `eq=False`
  dataclasses and hand-written `__eq__` methods in the engine; and a test replays a game in two processes with different
  `PYTHONHASHSEED`s and requires byte-identical pickles (CLAUDE.md rule 6).
- **Why:** design.md §14 and the roadmap. The harness lives in `tools/` because rule 4 keeps
  agent-using code out of the engine and tools can't import `tests/`. Submitting to copies at
  every decision tests the strongest form of design.md §5 (a state copied mid-task resumes
  exactly as the original) at little cost. Each check has a negative test built from a broken
  test-only task (`tests/engine_support.py`), so a check that silently stops working is noticed.
  The CLI defaults to empty decks because no card is implemented and tools never invent cards.
  Widen `ALLOWED_GAPS` deliberately as milestones change where games stop.
- **Rules:** 400.2, 401.2, 402.3, 404.2, 406.3; design.md §5, §6, §7, §9, §12.
- **Where:** `tools/fuzz.py`, `tests/fuzz/test_fuzz.py`, `tests/engine_support.py`.

### 2026-10-18: The text interface and `tools/play_cli.py`
- **Decision:** the renderer (`render_view`, `render_request`, `render_log_entry`), the answer
  parser (`parse_answer`) and the CLI agent (`TextAgent`) are in `resolve.agents.text`;
  `tools/play_cli.py` only parses arguments, builds decks and runs `play`. Options are numbered
  from 0, matching `Pick` indices. The parser checks only the shape of what was typed (out-of-range
  numbers go to the engine, which rejects them, and the driver asks again). Each human seat
  sees its own view, so hot-seat play doesn't leak hands; for the same reason the final view is
  printed only when a single seat is human (player 0's when every seat is random), and hot-seat
  games end with just the result. Without `--deck` every player gets an
  empty deck; with `--deck`, decks come from the snapshot and must be fully implemented. Exit
  statuses: 0 game over, 1 couldn't start, 2 bad arguments, 3 stopped at a `NotImplementedRule`,
  4 quit.
- **Why:** the renderer is useful outside the CLI (debugging, failure messages), and keeping it
  in the agents package keeps it on the agent side of rule 4. Zero-based numbering keeps the CLI
  and the log saying the same thing. Empty decks are the only decks that need no card
  implementation, and decks are never approximated.
- **Where:** `src/resolve/agents/text.py`, `tools/play_cli.py`.

### 2026-10-18: The scenario builder in M0
- **Decision:** `tests/scenario.py`'s `Scenario` starts from `initial_state` with empty decks and
  creates objects immediately, so every call returns real `ObjectId`s and IDs and timestamps
  follow call order. It sets player count, config, seed, starting player (default 0; `None` for
  "not chosen yet"), life (any integer), cards in every zone, `known_to` and commanders (in any
  zone, only with the Commander rules). Piles (library, graveyard, stack) are listed **top
  first**, and a later call puts its cards on top. A card in another player's library, hand or
  graveyard is refused rather than redirected (400.3); a controller is required exactly on the
  battlefield and the stack. A failed `add` leaves the scenario unchanged. `build(*tasks)` checks
  invariants and purity and runs the given tasks to their first decision. Turn, step, phase and
  priority holder are added with the turn structure in M1. Like `new_game`, the builder doesn't
  check whether a card may be a commander (legendary, partner for a second one: 903.3, 903.5,
  702.124a); that is deck validation in M7. The test review suggested refusing such commanders;
  it was kept consistent with `new_game` instead, and a second commander reaches the existing
  613.7m gap when the game starts. `run_script(state, *steps)` plays a
  script and requires every step to be used; `names(state, zone)` lists a zone's card names.
- **Why:** design.md §14. Building through the engine's own `create_object` keeps scenario
  states identical in shape to played ones. Top-first lists read like "the top card is X".
  Refusing an impossible placement catches test mistakes that a redirect would hide. The builder
  can't set what the engine doesn't model yet.
- **Rules:** 103.1, 108.4, 110.2, 119, 400.2, 400.3, 401.2, 405.2, 613.7d, 702.124a, 903.3,
  903.5.
- **Where:** `tests/scenario.py`, `tests/engine/test_scenario_builder.py`.

### 2026-10-18: Agents, the driver and replays
- **Decision:** `resolve.agents` holds the `Agent` protocol (`decide(view, request) ->
  DecisionAnswer`), the driver `play(state, agents, max_answers=None, on_invalid=None)`,
  `RandomAgent` and `ScriptedAgent`. `play` takes one agent for every player or one per seat.
  A rejected answer raises `InvalidAnswer` unless `on_invalid` is given; then the same agent is
  asked again, up to 100 times per decision. `RandomAgent` uses its own `Rng` (the engine's
  generator) and is uniform over each space's answers: over options, over subset sizes and then
  subsets of that size, over permutations, over numbers, and over divisions (stars and bars). An
  unbounded `ChooseNumber` is capped at `minimum + 20` (`unbounded_span`). A script is a list of
  `Step(value)` or `Choose(options)` (resolved against the space, so a test needn't know option
  indices), each optionally naming the expected player and kind; a mismatch or running out raises
  `ScriptError`. A replay is `ScriptedAgent.from_log(state.event_log)`: the recorded answers with
  their players and kinds, played from the same config, decks and seed. The save-file format with
  engine, CR and data versions (design.md §12) is not built yet. The determinism lint scans
  `resolve.agents`.
- **Why:** design.md §3 already defines the driver loop and the `decide` interface. Uniform
  answers explore every kind of answer, including the extremes. Replaying through the same
  agent interface means a replay checks itself: a step whose player or kind no longer matches
  stops the replay at the first divergence. Rejected answers aren't logged, so replays contain
  only accepted ones.
- **Rules:** 101.4; design.md §3, §6, §12.
- **Where:** `src/resolve/agents/`, `tests/agents/`, `tests/state/test_determinism_lint.py`.

### 2026-10-18: Every CR citation in the engine must exist in the pinned rules
- **Decision:** `tests/tooling/test_rule_citations.py` collects every CR number the engine cites
  and checks it against the section, rule and subrule numbers parsed from
  `docs/rules/MagicCompRules-20260925.txt`. It collects them statically (string constants passed
  as `rules=`, every `NotImplementedRule` message via `tools/gaps.py`, and every dotted number such
  as `613.7m` anywhere in the source text of `src/resolve`, comments and docstrings included) and
  at run time (the rules of every log entry and request of a played game). Citations have one
  format, checked when events and requests are built (`resolve.citations`): `"103"`, `"103.1"` or
  `"701.24a"`, one rule per string.
- **Why:** the user asked for it. Citations are how readers check the engine against the CR; a
  mistyped or renumbered rule would otherwise go unnoticed until someone looked it up. Bare
  three-digit section numbers in prose aren't scanned (too many false positives such as "100
  cards"), but structured citations may be sections.
- **Rules:** CLAUDE.md rules 2 and 3.
- **Where:** `src/resolve/citations.py`, `tests/tooling/test_rule_citations.py`.

### 2026-10-18: Immutable values are shared between copies of a state
- **Decision:** value types derive from `resolve.values.Immutable`, whose `__copy__` and
  `__deepcopy__` return the object itself: `CardData`, `CardFace`, `CardDefinition`, `Card`,
  `Zone`, `GameConfig`, events, log entries, requests, answer spaces, options, answers, decks and
  player views. Each must be a frozen dataclass whose fields hold only scalars, enums, tuples and
  other `Immutable` values. `tests/state/test_immutability.py` checks every subclass from its type
  hints (so field annotations must be resolvable at run time, not imported only under
  `TYPE_CHECKING`), and `resolve.state.invariants.mutable_parts` checks actual values. `CardData`
  holds no rulings: they stay in `CardDatabase`, for writing tests.
- **Why:** the user asked for it. Under design.md decision A the state holds every card's data and
  definitions; copying them on every clone would make AI search pay for Oracle text that never
  changes. Sharing is only safe for deeply immutable values, hence the test. Frozen dataclasses
  don't check types at run time, so the value check also exists (a list passed where a tuple is
  annotated would otherwise be shared and mutable).
- **Where:** `src/resolve/values.py`, `src/resolve/data/cards.py`, `src/resolve/cards/registry.py`,
  `src/resolve/state/invariants.py`.

### 2026-10-18: Starting the game in M0
- **Decision:** `initial_state` creates every card's object in its owner's library (commanders
  first, then deck order), which stands for the player's deck before 103.3: hidden and unshuffled.
  It records each player's commanders (`Player.commanders`, 903.3) and sets life from the config
  (103.4). `CardId`s and setup timestamps follow seat order, commanders first, then deck order.
  `StartGame` then:
  1. picks the player who chooses the starting player uniformly with the game's RNG and asks them
     (`CHOOSE_STARTING_PLAYER`; every player is an option, the chooser included) (103.1);
  2. in a Commander game, puts every commander into the command zone with one set of simultaneous
     `CommanderPutIntoCommandZone` events in turn order from the starting player (103.2c, 903.6).
     Each commander becomes a new object (400.7) whose timestamp follows APNAP order (613.7m,
     with the starting player as active player, 101.4e). A player with several commanders
     (partners) raises `NotImplementedRule("613.7m: ...")`, because that player chooses the
     order among their own;
  3. shuffles each library in turn order (103.3);
  4. stops at `NotImplementedRule("103.5: ...")`.

  The opponents' optional extra shuffle or cut (103.3) is left out. Matches aren't modeled:
  `new_game` is one game, so 103.1's "loser of the previous game chooses" belongs to whoever runs a
  match.
- **Why:** 103.2 puts 103.2c after the starting player is determined, so the chooser must not see
  the other players' commanders yet. The test review caught that an earlier version of this branch
  put them in the command zone at setup. 103.1 leaves the method of picking the chooser to the
  players; a uniform random pick is such a method and keeps the game a function of its seed. A
  uniformly random library stays uniformly random after any further shuffle or cut, so offering
  that choice would add a decision with no effect. The setup timestamps aren't ordered by
  613.7m: there is no starting player yet, and nothing can observe the relative timestamps of
  cards in a library before they next change zone. The `CommanderPutIntoCommandZone` log entries
  show the commanders' old library IDs to everyone; that reveals nothing, because the commander
  is leaving and the rest of the library is shuffled next.
- **Rules:** 101.4e, 103.1-103.5, 400.7, 613.7d, 613.7m, 701.24a, 903.3, 903.6, 903.7.
- **Where:** `src/resolve/engine/setup.py`, `src/resolve/engine/start.py`,
  `src/resolve/events/game.py`.

### 2026-10-18: Moving objects between zones
- **Decision:** `resolve.state.game.move_object` implements 400.7:
  - The object is removed, and a new object with a new ID and timestamp is created on top of the
    destination.
  - A move from the command zone into the command zone also makes a new object (400.10).
  - An object sent to another player's library, hand or graveyard goes to its owner's instead
    (400.3); `create_object` applies the same redirect.
  - The destination is checked before anything changes: a controller must be given exactly for
    the battlefield and the stack (109.4, 110.2).
  - A controlled object in the command zone (an emblem, 109.4c) raises `NotImplementedRule`.
  - No knowledge carries over to the new object. An event that moves a card whose identity
    players saw (a revealed card put back on top of a library, 701.20) records that on the new
    object itself; that arrives in M1.
  - Only events call `move_object`. Last-known information and the other 400.7 exceptions arrive
    with the milestones that need them (M1, M4).
- **Why:** 400.3 is a redirect, not a prohibition: "put it into your hand" on a card you don't own
  is legal and sends it to its owner's hand. The test review caught that an earlier version
  raised `EngineError` instead. Keeping knowledge decisions in the event that knows what players
  saw keeps the primitive simple and correct by default (400.7: "no memory of ... its previous
  existence").
- **Rules:** 109.4, 109.4c, 110.2, 400.3, 400.7, 400.10, 613.7d, 701.20.
- **Where:** `src/resolve/state/game.py`.

### 2026-10-18: Identifiers, seating and pile order
- **Decision:** `PlayerId`, `ObjectId` and `CardId` are `NewType` ints. `PlayerId` is the seat
  index and `players` is in seating order (deck `i` is player `i`); turn order is computed from
  `starting_player` (`turn_order`). `ObjectId`s and `CardId`s start at 1 and are never reused. In
  every pile (library, graveyard, stack) the last list element is the top; hand, battlefield,
  exile and command lists keep arrival order. Objects without a controller have
  `controller=None`; 108.4a's "use the owner" is for whoever asks.
- **Why:** ints pickle, compare and hash cheaply and deterministically; `NewType` keeps them
  apart for pyright. Seat indices stay valid when players leave (800.4). One orientation for all
  piles avoids a class of top/bottom bugs.
- **Rules:** 103.1, 108.4, 109.4, 400.5, 400.7, 404.1, 405.2.
- **Where:** `src/resolve/state/ids.py`, `src/resolve/state/game.py`, `src/resolve/state/zones.py`.

### 2026-10-18: Answer validation and canonical answers
- **Decision:** an answer is checked in two stages, neither of which changes the state: the
  request's id and player and its answer space (`validate_answer`), then the asking task's
  `check_answer`. Each outcome has exactly one valid answer: subsets are strictly increasing
  indices, orders are permutations, distributions are one amount per recipient. Booleans are not
  accepted as integers. A space that can't be answered (no options, impossible bounds) raises
  `ValueError` when built, as an engine bug. `DecisionKind` lists the vocabulary of design.md §6;
  only `CHOOSE_STARTING_PLAYER` is asked in M0.
- **Why:** rejecting before changing anything lets an agent (or a network peer) retry, and makes
  "the state is unchanged" testable by comparing with a copy. Canonical answers mean equal
  answers have equal meaning, which AI search and replays rely on.
- **Rules:** 101.4, 601.2d, 107.3a.
- **Where:** `src/resolve/decisions/`, `src/resolve/engine/loop.py`.

### 2026-10-18: The engine loop, errors and the state after an error
- **Decision:** the task base class lives in `resolve.tasks` (top level), not `resolve.engine`,
  because events use it and `resolve.engine` imports the events. The loop raises `EngineError` if
  a task changes `state.tasks` itself, if the stack empties during a game, or after
  `MAX_TASKS_PER_RUN` (one million) tasks without a decision. `submit` isn't transactional: after
  `NotImplementedRule` or `EngineError` the state stays as it was when the error was raised, isn't
  waiting for anything, and must not be played on (`pending_decision` raises `EngineError`).
- **Why:** a rollback would mean copying the state on every `submit`, which AI search can't
  afford. The runaway budget only catches engine bugs; mandatory game loops are 104.4b (M7).
- **Where:** `src/resolve/tasks.py`, `src/resolve/engine/loop.py`, `src/resolve/errors.py`.

### 2026-10-18: The event log records answers and who may see each entry
- **Decision:** a `LogEntry` holds an event or an `AnswerRecord`, its index and its visibility
  (`None` for everyone, or sorted player IDs). Answers are visible only to the player who gave
  them; whatever they make public is logged as events. An event's visibility is judged before it
  is applied. Views include the entries their player may see. Views show printed card names until
  the layer system exists (M5); an object without a card in a view raises
  `NotImplementedRule("111.1: ...")`, since tokens don't exist yet.
- **Why:** replays are rebuilt from the answers (design.md §12), and some answers are secret
  (cards put on the bottom after a mulligan, 103.5). How zone-change entries are redacted for
  other players is decided in M1, when cards are drawn.
- **Rules:** 101.4, 103.5, 111.1.
- **Where:** `src/resolve/events/base.py`, `src/resolve/engine/view.py`.

### 2026-10-18: Deck construction isn't checked until M7
- **Decision:** `new_game` checks only that there are at least two decks (100.1), that every card
  has a definition for each face (`DeckCard`), and that commanders are given only with the
  Commander rules. Deck size, singleton, color identity and "has a commander" (100.2a, 903.3,
  903.5) are left to `validate_deck` in M7.
- **Why:** deck legality is a pre-game check, not a game rule, and the decision to move the
  deck-construction settings out of `GameConfig` until they're enforced was approved with
  design.md §10. Tests and the scenario builder need small, illegal decks anyway.
- **Rules:** 100.1, 100.2a, 903.3, 903.5.
- **Where:** `src/resolve/engine/deck.py`, `src/resolve/engine/setup.py`.

### 2026-10-18: Purity, determinism and gap tooling
- **Decision:** `resolve.state.invariants.state_impurities` accepts scalars, enums, lists, tuples,
  dicts with int/str/enum keys and any dataclass instance whose fields are pure (and that has no
  attributes besides its fields, so test-only tasks qualify); it also rejects a `GameObject` or
  `Player` held outside `state.objects`/`state.players`. `tests/state/test_determinism_lint.py`
  scans the engine packages for imports of `time`, `datetime`, `random`, `uuid`, `secrets`, `os`
  and `threading` and calls to `id()` and `hash()`. `tools/gaps.py` lists every
  `NotImplementedRule` by AST and fails on any whose message isn't a literal starting with a CR
  number.
- **Why:** CLAUDE.md rules 1, 5 and 6, enforced by tools rather than by review. Set iteration
  can't be found by a scan, so sets are kept out of the state instead.
- **Where:** `src/resolve/state/invariants.py`, `tests/state/`, `tools/gaps.py`.

### 2026-10-18: Engine test layout and helpers
- **Decision:** engine infrastructure tests live in `tests/state/`, `tests/engine/`,
  `tests/decisions/` and `tests/events/`; rules tests in `tests/rules/` as before.
  `tests/game_fixtures.py` builds decks from the Scryfall fixtures with test-only definitions and
  starts games. `tests/engine_support.py` holds test-only tasks and a `Marker` event, in an
  importable module so that states holding them can be pickled; `running(*tasks)` starts a game
  with those tasks above a `Hold` task that keeps the game waiting once they finish.
- **Why:** the scenario builder (later in M0) will replace most of the fixtures, but the loop
  needs tasks that exercise every result type before any real turn structure exists.
- **Where:** `tests/`.

### 2026-10-18: Test layout and Scryfall fixtures
- **Decision:** Infrastructure tests live in `tests/data/` (card data, decklists),
  `tests/registry/` (registry, deck coverage) and `tests/tooling/` (the `tools/` scripts). No test
  reads `data/` or the network. Tests that need card data use `tests/scryfall_fixtures.py`:
  hand-written records in Scryfall's bulk format, a few real cards (Llanowar Elves, Forest) plus
  invented cards whose names start with "Test" for edge cases, and placeholder rulings that are
  not real rulings. Fixture bulk files are gzipped with `mtime=0` so their bytes are reproducible.
  `tests/` has no `__init__.py`, so pytest imports test files by basename and basenames must be
  unique across folders (hence `test_coverage_tool.py` vs `test_deck_coverage.py`). pytest's
  `pythonpath = ["."]` makes the repo root importable, so tests import `tests.scryfall_fixtures`
  and the tools as `tools.coverage` (`tools/` is a package).
- **Why:** the real snapshot is large, gitignored and absent in CI, and a test must not change
  meaning when the snapshot changes. Invented names make it obvious which data is real. The
  fixtures once encoded a wrong assumption about Scryfall's format (plain JSON arrays) and the
  tests passed anyway; when the external format matters, check the fixtures against a real
  download.
- **Where:** `tests/`, `tests/scryfall_fixtures.py`, `tools/__init__.py`, `pyproject.toml`.

### 2026-10-18: Card registry: per-face definitions collected from `DEFINITIONS`
- **Decision:** `CardDefinition` holds only `name` for now; behavior fields arrive with the
  primitives. Definitions are registered under the exact Oracle name of each face, so a
  multi-faced card is implemented only when every face has a definition (registering
  `"Front // Back"` doesn't count). Each module in `resolve.cards.definitions` exports a
  `DEFINITIONS` sequence; `default_registry()` imports the modules in sorted name order and
  registers them. Registering a name twice is an error.
- **Why:** design.md §11 registers multi-faced cards per face. Collecting explicit lists instead
  of registering on import keeps the registry free of global state, so tests build their own
  registries, and sorted order keeps it deterministic. The coverage logic lives in the package
  (`resolve.cards.coverage`) rather than only in the tool, so `new_game` can reuse it to refuse
  unimplemented decks.
- **Rules:** 709 (split), 710 (flip), 712 (double-faced), 715 (adventurer), 722 (preparation).
- **Where:** `src/resolve/cards/registry.py`, `src/resolve/cards/coverage.py`.

### 2026-10-18: Card name matching is exact; ambiguous names are refused
- **Decision:** `CardDatabase.get` matches names exactly and case-sensitively. A multi-faced card
  can also be found by its front face's name, but never by a back face's name, and a card's full
  name always wins over another card's front-face alias. Objects that can't be in a deck
  (`NON_DECK_LAYOUTS`: tokens, emblems, art series, Jumpstart `front_card`s, `reversible_card`
  reprints, Planechase, Archenemy and Vanguard cards) are left out of the index. A name still
  shared by several cards raises `AmbiguousCardNameError`; a deck naming it is reported as
  "unknown".
- **Why:** decks are refused rather than approximated (CLAUDE.md), so near-matches are errors.
  Decklists usually name double-faced cards by their front face. Tokens share names with each
  other, and front cards and reversible cards share names with real cards (Savage Lands,
  Inferno). In the 2026-10-17 snapshot, 38 names remain ambiguous, all Un-set or playtest
  variants (for example Red Herring); none are in the target decks. If one is ever needed, prefer
  a deliberate rule (such as ignoring `set_type == "funny"`) over guessing.
- **Rules:** 201.2 (English names). Interchangeable names (201.3) are not treated as equal; that
  only matters for deck construction (903.5b) and belongs to deck validation (M7).
- **Where:** `src/resolve/data/cards.py` (`CardDatabase`, `NON_DECK_LAYOUTS`).

### 2026-10-18: Card data representation
- **Decision:** `CardData.faces` always has at least one `CardFace`; single-faced cards get one
  face built from the card's own fields. Faces without `colors` (split and adventurer cards) take
  the card's colors. Power, toughness, loyalty and defense are strings or `None`. `mana_value`
  is a float. Scryfall's `keywords` list is kept for reports only.
- **Why:** one shape for every card avoids special cases. Values like `*` and `1+*` (208.2)
  aren't numbers, and Scryfall reports fractional mana values for a few Un-cards. Card behavior
  must come from definitions built from primitives, never from Scryfall's keyword tags, which
  also include ability words and keyword actions.
- **Rules:** 109.3, 202.3, 208.2, 903.4.
- **Where:** `src/resolve/data/cards.py`.

### 2026-10-18: Decklist format and parsing rules
- **Decision:** a decklist has `Commander`, `Mainboard` and `Sideboard` sections; headers are
  matched case-insensitively and each may appear once. Card lines are `<count> <exact name>` with
  a positive integer count (`1x Name` is rejected). Every card line must follow a header. `#`
  starts a comment only at the beginning of a line, so `#` inside a name is kept. A card repeated
  within one section has its counts added. Errors give `deck:line`. Names are kept exactly as
  written. The parser does no deck validation.
- **Why:** strict parsing turns typos into errors instead of guesses. Deck legality (100 cards,
  singleton, color identity) belongs to deck validation in M7. The sideboard is out of scope for
  coverage (roadmap) and is only checked with `--include-sideboard`.
- **Rules:** 100.4 (sideboards), 903.3 (commander), 903.5a–c (Commander deck construction, not
  enforced here).
- **Where:** `src/resolve/data/decklist.py`, `decks/`.

### 2026-10-18: Snapshot drift on new machines is accepted
- **Decision:** a fresh checkout fetches Scryfall's current snapshot, not the pinned one. The
  fetch tool then rewrites the pinned date in `docs/rules/README.md` and adds a changelog row;
  the developer commits that to move the pin, or reverts it with
  `git checkout docs/rules/README.md`.
- **Why:** Scryfall serves only its current bulk files, so the pinned files can't be
  re-downloaded. The change shows up in `git diff`, and Oracle text rarely changes between
  snapshots. The user chose this over adding a strict date check or hosting a copy of the files.
- **Where:** `tools/fetch_scryfall.py`, `data/README.md`, `docs/rules/README.md`.

### 2026-10-18: Snapshot manifest and checksum checks
- **Decision:** `data/snapshot.json` records, for each bulk file, its publication time
  (`updated_at`), source, size and SHA-256. `load_card_database` refuses files whose SHA-256
  doesn't match (`verify=False` skips the check). The fetch tool downloads to `*.part` files and
  checks that each parses as the right bulk type before replacing anything; the Oracle-cards file
  must list each Oracle ID once, which tells it apart from Scryfall's other card files. The
  manifest is written last. An existing snapshot is replaced only with `--update`. Files
  downloaded by hand go in with `--import-files`, which reads the publication time from
  Scryfall's file names (`oracle-cards-YYYYMMDDHHMMSS.jsonl.gz`) or from `--updated-at`.
  The snapshot's date is the UTC date of the Oracle-cards file.
- **Why:** design.md §2 pins card data so a test never silently changes meaning; checksums catch
  edited, truncated or swapped files. The manual import exists because cloud sessions may not be
  allowed to reach Scryfall (`api.scryfall.com` and `data.scryfall.io` must be allowed in the
  environment's network settings).
- **Where:** `src/resolve/data/cards.py` (`SnapshotInfo`, `BulkFileInfo`,
  `load_card_database`), `tools/fetch_scryfall.py`.

### 2026-10-18: Scryfall bulk data is stored as gzipped JSON Lines
- **Decision:** the fetch tool downloads each entry's `jsonl_download_uri` and stores the file
  unchanged, as `data/oracle-cards.jsonl.gz` and `data/rulings.jsonl.gz`. The loader reads them
  line by line (`read_jsonl_gz`).
- **Why:** Scryfall's bulk-data index offers only gzip-compressed JSON Lines; the plain-JSON
  `download_uri` is gone. Keeping the file as served keeps it small (about 25 MB instead of over
  100 MB) and makes its SHA-256 the checksum of exactly what Scryfall published.
- **Where:** `src/resolve/data/cards.py`, `tools/fetch_scryfall.py`.

### 2026-10-18: Tooling: uv lockfile, pyright from a wheel, CI on two Pythons
**Superseded by 2026-10-18 (Windows first: the CI matrix and the encoding checks)** for the CI
matrix; the lockfile and pyright parts stand.
- **Decision:** `uv.lock` is committed and CI runs `uv sync --locked`, so a stale lockfile fails
  CI. Pyright is installed as `pyright[nodejs]`, which ships Node as a wheel. CI runs
  `ruff check`, `ruff format --check`, `pyright` (strict) and `pytest` on Python 3.12 (the
  minimum) and 3.13. The engine has no runtime dependencies; the fetch tool uses only the
  standard library (`urllib`).
- **Why:** plain `pyright` downloads Node at run time when none is installed, which can fail
  on restricted networks. Testing the minimum and a current version catches version-specific breakage.
- **Where:** `pyproject.toml`, `uv.lock`, `.github/workflows/ci.yml`.
