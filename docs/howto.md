# How-to recipes

Step-by-step instructions for tasks that recur, so every session does them the same way. When a
recurring task is done for the first time, or its steps change, the recipe is written or updated
here in the same PR (CLAUDE.md, "Documentation requirements").

Keep each recipe short: the steps, the files involved, and the tests to add. Explain *why* only
where a step would otherwise look arbitrary.

---

## Recipes

### Fetch or update the card data snapshot

The snapshot (Scryfall's Oracle cards and rulings) lives in `data/`, which git ignores. File
layout, the manual-download path and the drift caveat are in [`data/README.md`](../data/README.md).

**First time on a machine:**
1. `uv run python tools/fetch_scryfall.py` (takes about 10 seconds).
2. `git diff docs/rules/README.md`. Scryfall only serves its current files, so on a new machine
   the pinned date usually moves. Revert it with `git checkout docs/rules/README.md` unless you
   mean to move the pin (see "Updating the pinned snapshot").

**Updating the pinned snapshot** (deliberately, together with any CR update, design.md §2):
1. `uv run python tools/fetch_scryfall.py --update`. It refuses to replace a snapshot without
   `--update`, and validates the new files before replacing anything.
2. Run `uv run python tools/coverage.py` and check that no target-deck card became "unknown".
3. For each implemented card, compare its Oracle text and rulings with the previous snapshot,
   and update its definition and tests if they changed.
4. Commit `docs/rules/README.md`; the tool already updated its version row and changelog.

**In a cloud session:** the environment's network settings must allow `api.scryfall.com` and
`data.scryfall.io`. If they can't, the user downloads the files and runs `--import-files`
([`data/README.md`](../data/README.md)).

**If Scryfall's format changes:** the tool fails with `FetchError` and nothing in `data/` is
replaced. Download a real file, check its structure against `parse_card`, then update the parser
and `tests/scryfall_fixtures.py` together (see `docs/decisions.md`, 2026-10-18).

### Check a deck's card coverage

1. Make sure the snapshot is installed (previous recipe).
2. Run `uv run python tools/coverage.py` for every deck in `decks/`, or name decks:
   `uv run python tools/coverage.py decks/byrke_counters.txt`.
3. Read the report. It shows each deck's card counts, then three lists:
   - **Unknown**: the name matches no card, or several (typo, ambiguous name, or a card newer than
     the snapshot). Fix the decklist; never add a fuzzy match.
   - **Missing**: the card is in the card data but some face has no definition. A multi-faced
     card lists the missing faces.
   - **Implemented**: every face has a definition.

Useful flags:
- `--oracle` prints the Oracle text of every missing card. Use it to plan which mechanics a deck
  needs (the roadmap's "Mechanics" list came from it).
- `--include-sideboard` also checks sideboards, which are out of scope by default.
- `--require-complete` exits with 1 if any card is missing, for scripts and CI.

The exit status is 1 if a deck can't be parsed or names an unknown card. Decklist syntax is in
the docstring of `src/resolve/data/decklist.py`.

### Write tests that need card data

Tests never read `data/` or the network; they build card data from `tests/scryfall_fixtures.py`.

1. Pick or write the Scryfall-format records you need:
   - Reuse `fx.LLANOWAR_ELVES`, `fx.FOREST`, `fx.TRANSFORM_CARD` (transforming double-faced) or
     `fx.SPLIT_CARD`.
   - Use `fx.simple_card("Test Name", "oid-...", **fields)` for a one-off card, and
     `fx.token(...)` or `fx.ruling(...)` for tokens and rulings.
   - Invented cards are named "Test …" so they're obviously not real. Rulings in fixtures are
     placeholders: never present one as an official ruling.
   - Use Scryfall's field names and shapes (`card_faces`, `colors`, `cmc`, strings for power and
     toughness). If a test depends on how Scryfall represents something, check a real record
     first.
2. Build the objects in memory:
   ```python
   from resolve.data.cards import CardDatabase, parse_card, parse_oracle_cards, parse_rulings
   from tests import scryfall_fixtures as fx

   card = parse_card(fx.LLANOWAR_ELVES)
   database = CardDatabase(parse_oracle_cards(fx.default_cards()), parse_rulings(fx.default_rulings()))
   ```
3. To exercise loading from disk (the manifest, checksums, the tools), write a complete snapshot
   to a temporary folder and point the code at it:
   ```python
   def test_something(tmp_path: Path) -> None:
       fx.write_snapshot(tmp_path, cards=[fx.FOREST])  # bulk files + matching snapshot.json
       database = load_card_database(tmp_path)
   ```
   `fx.oracle_cards_bytes(...)`, `fx.rulings_bytes(...)` and `fx.jsonl_gz(...)` give raw bulk-file
   bytes, for example to serve from a fake opener in `tests/tooling/test_fetch_scryfall_tool.py`.
4. Put the test in `tests/data/`, `tests/registry/` or `tests/tooling/` (or `tests/cards/` for a
   card), with a file name that is unique across all test folders.

### Write a scenario test

Set up the board with the scenario builder (`tests/scenario.py`) instead of playing turns, and
drive decisions with a script.

1. Build the state:
   ```python
   scenario = Scenario(players=3, config=GameConfig.commander_game(), seed=1, starting_player=0)
   scenario.life(PlayerId(1), 3)
   elves = scenario.battlefield(PlayerId(0), ["Llanowar Elves"])[0]
   top, second = scenario.library(PlayerId(2), ["Forest", "Llanowar Elves"])  # top first
   scenario.commander(PlayerId(1), "Test Daybreaker")  # in the command zone by default
   state = scenario.build(SomeTask())  # runs to the first decision; build() alone runs nothing
   ```
   Cards are named exactly and come from `tests/game_fixtures.py`'s `scenario_database()` and
   `scenario_registry()` (the fixture cards plus an instant, a sorcery and a split card) unless
   you pass your own. Piles (library, graveyard, stack) are listed top first. Use
   `scenario.add(name, owner=..., zone=..., known_to=[...])` for anything else.
2. To test something during a turn, put the game in it with `at`:
   ```python
   scenario.at(Step.UPKEEP, active=PlayerId(1), number=3)  # player 1 about to get priority
   scenario.at(Phase.PRECOMBAT_MAIN, priority=PlayerId(1), passed=[PlayerId(0)], lands_played=1)
   scenario.at(Step.DRAW, begin=True)  # the step from its beginning
   state = scenario.build()  # state-based actions are checked first (117.5), then the request
   ```
   `at(step)` resumes a step with priority as a player is about to receive it; `begin=True`, and
   any untap or cleanup step, runs the step from its beginning with its turn-based actions.
   The turn then continues normally into later turns. `build(*tasks)` still runs tasks first.
   To play from the start of a real game instead, `tests/game_fixtures.py` has
   `started_game(...)` (everyone kept; at the first upkeep), `Passer` (keeps, passes, discards
   the first cards) and `pass_until(state, condition)`.
3. Answer with a script: `run_script(state, choose(PlayerOption(PlayerId(2)), kind=...), Step(Number(3)))`.
   Prefer `choose(...)` (names the options) over `Step(Pick(i))`, and give `player=` and `kind=`
   when the test is about who is asked what. The script must be used up exactly.
4. Check the result: zones with `names(state, zone)`, objects through `state.objects`, the log
   through `state.event_log`. Expect `NotImplementedRule` with `pytest.raises` where the game
   reaches a gap.
5. Put the test in `tests/rules/test_<section>_<topic>.py` (or `tests/cards/`,
   `tests/interactions/`), named and documented with the CR rule it checks.

### Write an engine test with test-only tasks

For the engine loop itself, drive it with small tasks.

1. Build decks with `tests/game_fixtures.py`: `deck(forests, elves, commanders=[...])`,
   `decks(players)`, or `start(players, seed)` for a new game paused at the 103.1 decision.
   `choose_starting_player(state, index)` answers it and returns the `NotImplementedRule` the
   game stopped at, or `None` if it is waiting for the next decision (the mulligans, 103.5,
   or the first turn).
2. For loop behavior, use the tasks in `tests/engine_support.py` (`Mark`, `Parent`, `AskTwice`,
   `EndGame`, ...) or add one there (not in the test file, so states holding it pickle).
   `running(*tasks)` starts a game with them on the task stack (or use
   `Scenario(...).build(*tasks)`); `markers(state)` lists the `Marker` events they logged;
   `holding(state)` says they have all finished.
3. Answer with `submit(state, answer(state, value))`, or `play(state, agent)` from
   `resolve.agents`. `concede(state, player)` (`resolve.engine`) concedes for a player at the
   paused decision; `resolve.agents.replay.replay(new_state, state.event_log)` replays a game's
   answers and concessions into a new game. To show a rejected answer changed nothing, compare
   with a `copy.deepcopy` taken before.
4. Check `state_impurities(state) == []` and `invariant_violations(state) == []`
   (`resolve.state.invariants`) on any new kind of state.
5. Put the test in `tests/engine/`, `tests/state/`, `tests/decisions/`, `tests/events/`,
   `tests/agents/` or, for a rule, `tests/rules/test_<section>_<topic>.py`.

### Run the fuzz harness

`tools/fuzz.py` plays random-agent games and checks each one (`fuzz_run`'s docstring lists the
checks). It has two presets (`QUICK` and `THOROUGH` in `tools/fuzz.py`); explicit options
override either.

| Run | Command (PowerShell and Unix alike) | Games | Decks | Concessions | Full checks | Time |
|---|---|---|---|---|---|---|
| Quick (default): agents and day-to-day work | `uv run python tools/fuzz.py` | 10 | 40 and 10 basic lands | 1 decision in 200 | every 10 answers | about 20 s on 4 cores |
| Thorough: the user's milestone verification | `uv run python tools/fuzz.py --thorough` | 100 | 40 and 20 basic lands | 1 decision in 500 | before every decision | about 1 hour on 8 cores, 2 on 4 |

1. Both presets cycle the player counts 2 to 6, then the formats (standard, then Commander), so
   10 games are one game of each. The decks are basic lands, the same number of each, from
   `tools/excerpts/basic_lands.json` (no snapshot needed), one size per seat in turn. Games play
   turns (lands, mana, priority, cleanup) until players concede or draw from an empty library;
   the smaller decks make some games end by decking even with several players, where
   concessions otherwise come first. Games run in parallel worker processes (`--jobs N`,
   default: the number of CPUs); the results are the same for any `--jobs`.
2. Options: `--games N`, `--seed S` (of the first game), `--players 2 4`, `--format standard`
   or `--format commander` (`--commander`), `--concessions N` (0: never), `--check-every N`
   (1: before every decision), `--jobs N`, and the decks: `--copies 8 4` (basic-land decks of
   that many of each basic land, one per number), `--deck a.txt --deck b.txt` (cycled among the
   seats; they need the snapshot and implemented cards) or `--empty-decks` (every game ends in
   the first upkeep, a draw).
3. The output: first the preset and settings (`Run:`), then, in runs longer than the quick one,
   a line every 10 games, then the summary: answers accepted and rejected; answers and turns per
   game (min, average, max); endings by type (decked, life total, concession, draw, rules gap,
   then any other, named by the rule of the last loss); lands played and mana abilities
   activated; formats; games per second.
4. A failure prints `FAILED:` with the seed and the start of a command that reproduces that one
   game, then `This run's options:`, the rest of it (decks, concessions, check interval).
   Reproduce it, write a failing test (a scenario test, or a `fuzz_game` call in `tests/fuzz/`),
   then fix the engine.
5. Full checks (the state's purity, every player's view, the deepcopy and pickle copies, invalid
   answers) cost time that grows with the game; the bookkeeping invariants run before every
   decision and every game is replayed at the end whatever `--check-every` says. Each full check
   walks only the log entries added since the last one (`CheckedLog`).
6. When a milestone changes which gaps games can reach (after M1: 601.2 for casting), update
   `ALLOWED_GAPS` in `tools/fuzz.py`, the fuzz tests' expectations and the roadmap together.
   Random agents stop at the first offered gap they pick; the fuzz tests' `PatientAgent`
   (`tests/engine_support.py`) mostly passes, so its games reach later turns. When implemented
   cards can make the default decks more varied, change `basic_land_deck` and its tests.
7. When adding a new check to the harness, add a broken test-only task to
   `tests/engine_support.py` and a test in `tests/fuzz/test_fuzz.py` showing the check catches it.

### Write or check a card data excerpt

A tool that must run without the snapshot (CI, a fresh checkout) uses an excerpt: a few cards
copied from the snapshot into a committed JSON file. Never write card records by hand.

1. With the snapshot in `data/`, write the excerpt:
   `uv run python tools/card_excerpt.py tools/excerpts/NAME.json "Card One" "Card Two"`. It keeps
   only the fields the loader reads (`EXCERPT_CARD_FIELDS`), the cards' rulings, and the
   snapshot's manifest (`taken_from`).
2. Load it with `resolve.data.cards.load_card_excerpt(path)`, a `CardDatabase`.
3. After updating the snapshot, check the excerpts still match it:
   `uv run python tools/card_excerpt.py tools/excerpts/basic_lands.json --check`; rewrite one
   that doesn't.
4. Test what uses the excerpt against the cards' printed characteristics (see
   `tests/tooling/test_card_excerpt_tool.py`).

### Play a game in the terminal

`uv run python tools/play_cli.py [--players N] [--commander] [--seed S] [--random SEAT ...]
[--deck PATH ...]`. Every seat not in `--random` is a human at the same terminal, shown only its
own view. Type option numbers from 0 (`help` at the prompt lists the syntax; `view`, `log` and
`quit` also work). Without `--deck` the decks are empty, so every player loses at the first
upkeep for having drawn from an empty library and the game is a draw. A game that reaches a
rule the engine doesn't implement exits with status 3.

### Check that a change works on Windows

CI runs every check on Windows and Linux with Python 3.12, 3.13 and 3.14; a PR isn't done until
all six pass. Before pushing:

1. Run the suite with the encoding warning on, as CI does. PowerShell:
   `$env:PYTHONWARNDEFAULTENCODING = "1"; uv run pytest`. Linux or macOS:
   `PYTHONWARNDEFAULTENCODING=1 uv run pytest`.
2. On Linux, `LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=0 uv run pytest` runs with an ASCII
   locale, which fails wherever code relies on the locale encoding, much as cp1252 does on
   Windows.
3. A test of output a Windows user may redirect sets `PYTHONIOENCODING=cp1252` in a subprocess
   (see `tests/tooling/test_tool_output_encoding.py`). A test of a file a Windows user may make
   writes the bytes itself: `\r\n`, a byte order mark, UTF-16 (see `tests/data/test_decklist.py`).
4. A new tool in `tools/` copies the `__main__` block of an existing one (UTF-8 standard output);
   the output-encoding test picks it up automatically.

### Add an event type

1. In `src/resolve/events/`, write a `@dataclass(frozen=True, kw_only=True)` subclass of `Event`.
   Its fields are scalars, enums, tuples and IDs only, never `GameObject`s or `Player`s
   (`tests/state/test_immutability.py` checks every event class).
2. Implement `apply(state)`, the change itself. A zone change goes through
   `resolve.state.game.move_object` (400.7, 400.3). If applying it learns something the proposal
   couldn't say (a new object's ID, which card was on top), return a copy recording it
   (`dataclasses.replace`); otherwise return `None`. Override `visible_to(state)` if some
   players may not see it in the log (it is judged before the event is applied), and
   `redacted()` to give the others a form without the hidden part (never a library object's ID,
   design.md §9).
3. Propose it from a task with `Push((ApplyEvents((event, ...)), ...))`, passing
   `rules=(...)` with the causing rule first. Never call `apply` directly from engine code.
4. Test: the change, what it must not change, rejected inputs, and the log entry with its
   visibility. `tests/tooling/test_rule_citations.py` checks the cited rules exist.

### Add a decision kind or an answer space

1. Add the kind to `DecisionKind` (`src/resolve/decisions/kinds.py`) with its CR rule in a
   comment, if it isn't there yet.
2. Use an existing answer space if one fits (`ChooseOne`, `ChooseSubset`, `ChooseOrder`,
   `ChooseNumber`, `Distribute`). A new space goes in `spaces.py`: a frozen `AnswerSpace` with a
   `__post_init__` that raises `ValueError` if the space can't be answered, a `validate` that
   raises `InvalidAnswer`, a canonical answer value (one valid answer per outcome), and tests of
   valid, invalid, empty and boundary answers in `tests/decisions/test_answer_spaces.py`.
3. The asking task returns `NeedDecision(...)`, rejects rules-illegal answers in `check_answer`
   (without changing anything), and continues in `resume`.

### List the rules the engine doesn't implement

Run `uv run python tools/gaps.py`. It lists every `NotImplementedRule` in `src/resolve` by CR
number, and exits with 1 if any message isn't a literal `"<CR number>: <what>"`. Don't keep a
hand-written list anywhere.

### Review a PR's tests independently

Every PR that changes game behavior gets an independent test review (CLAUDE.md, "Testing
requirements"). The reviewer is the `test-reviewer` subagent in `.claude/agents/test-reviewer.md`.
It checks tests against the CR and rulings, never against the implementation, and doesn't edit
files.

**As part of implementing** (the normal path):
1. When the tests and implementation are done and the suite passes, run the `test-reviewer`
   subagent on the branch.
2. For each finding, add or fix tests, or explain with CR citations why you disagree.
3. Re-run the reviewer if the changes were substantial.
4. Record the verdict and how each finding was handled in the PR description.

**As a separate check** (the user, in a fresh session, for extra independence):
1. Check out the PR's branch (`git fetch && git checkout <branch>`), or name the PR.
2. Ask: *"Use the test-reviewer agent to review the tests on this branch (PR #N)."*
3. Paste the report into the PR as a comment. Ask the implementing session to address it, or
   address it in this session.

### Add a card

1. Read the card's Oracle text and rulings in the snapshot (`uv run python tools/coverage.py
   --oracle` shows the Oracle text of missing cards).
2. Write the definition in a module of `src/resolve/cards/definitions/` (one module per card
   or card group, such as `basic_lands.py`): a `CardDefinition(name, abilities=(...))` per face,
   built from the primitives in `docs/primitives.md`, and added to the module's `DEFINITIONS`.
   Leave out what rules give the card by themselves (a basic land type's mana ability, 305.6).
3. Add a Scryfall-format record to `tests/scryfall_fixtures.py` if tests need the card, and to
   `scenario_database()` / `scenario_registry()` in `tests/game_fixtures.py` for scenarios.
4. Write `tests/cards/test_<card or group>.py`: the computed characteristics, each ability in
   play, the timing it may be cast or played with, and one test per relevant official ruling.
5. Check that `default_registry()` finds it (a test like
   `test_all_five_are_registered_without_printed_abilities`), and that tests which used the
   card as an example of an *unimplemented* card now use another one.

### Add a primitive

1. Search `docs/primitives.md` first; extend an existing primitive rather than adding a
   near-duplicate.
2. Write it in `src/resolve/cards/primitives/` (`abilities.py`, `costs.py`, `effects.py`, ...):
   a frozen `Immutable` dataclass holding only data, whose methods produce events (never
   change the state directly). Base classes that definitions name go in `base.py`, which imports
   nothing from the engine, so `CardDefinition` can refer to them without import cycles.
3. Raise `NotImplementedRule` for the parts of its rules that aren't supported yet (as
   `TapSelfCost` does for creatures, 302.6).
4. Test it on its own (`tests/cards/test_mana_primitives.py` is an example): what it allows,
   what it refuses, the events it produces, and its `text`.
5. Add its entry to `docs/primitives.md` (name and module, one line, the rules, an example).

---

## Still to write

Expected recipes, written when each task is first done:

- Add a keyword ability
- Fix a rules bug
