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

---

## Still to write

Expected recipes, written when each task is first done:

- Add a card
- Add a primitive
- Add a keyword ability
- Add an event type
- Add a decision kind
- Write a scenario test
- Fix a rules bug
