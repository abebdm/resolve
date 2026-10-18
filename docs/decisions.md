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
- **Decision:** `uv.lock` is committed and CI runs `uv sync --locked`, so a stale lockfile fails
  CI. Pyright is installed as `pyright[nodejs]`, which ships Node as a wheel. CI runs
  `ruff check`, `ruff format --check`, `pyright` (strict) and `pytest` on Python 3.12 (the
  minimum) and 3.13. The engine has no runtime dependencies; the fetch tool uses only the
  standard library (`urllib`).
- **Why:** plain `pyright` downloads Node at run time when none is installed, which can fail
  on restricted networks. Testing the minimum and a current version catches version-specific breakage.
- **Where:** `pyproject.toml`, `uv.lock`, `.github/workflows/ci.yml`.
