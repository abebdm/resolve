# Progress: meaningful default fuzz run

Task (user prompt): make `uv run python tools/fuzz.py` default to basic-land decks (no snapshot
needed), keep empty decks as an option, report answers/turns/endings, add tests, document in
howto.md with PowerShell commands, open a PR.

## Done
- `tools/excerpts/basic_lands.json`: the five basic lands copied from the Scryfall snapshot of
  2026-10-18 by the new `tools/card_excerpt.py` (write / `--check`), loaded with
  `resolve.data.cards.load_card_excerpt`.

## In progress
- `tools/fuzz.py`: default decks of 40 basics (8 of each), `--empty-decks`, summary, and a
  check schedule (`check_every`) so long games stay affordable.

## Next
- Tests (card_excerpt tool, load_card_excerpt, fuzz defaults and summary), docs (howto,
  decisions, primitives n/a, CLAUDE.md status), test-reviewer, PR.

## Decisions not yet in docs
- Excerpt rather than hand-written records or importing tests' fixtures (tools can't import
  tests/; tools never invent cards).
- Full per-decision checks are quadratic in game length (log walks, copies, pickles); 40-card
  games need a sparse schedule in the CLI.
