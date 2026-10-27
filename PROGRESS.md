# PROGRESS: M2.8 (evergreen keywords, counter, Cryptic Command)

Task: implement step M2.8 of `docs/plans/m2.md` (prompt in the plan's "Prompts"). Branch
`claude/m2-8-implementation-m0l5ip`.

## Done

- Read the plan, design.md §17.2/§17.11/§17.12, the code. M2.7 is merged (PR #34).
- Keyword module (`cards/keywords/evergreen.py`, `qualities.py`), `primitives/statics.py`
  (`CantBeCountered`), effect stubs `CounterSpell`/`ReturnToHand`/`TapAll` (tasks raise),
  `EachCreature.controlled_by`, `legality.CounterAction` and `SpellCountered` stubs (raise),
  definitions `keyword_examples.py`, `counterspells.py`, fixtures, excerpt (24 cards),
  `Scenario.stack(variant=)`, `casting_support.target_choices`.
- Tests first written and run: 60 tests, 33 fail for the right reason. 27 pass before the
  implementation (the 14 keyword-card text/characteristics tests, Cryptic's text, and "must
  still happen" tests: list in scratchpad, to copy into the PR).

## In progress

- Implementing.

## Next

- Confirm the tests fail for the right reason; implement prohibitions (target, destroy,
  counter), flash in `may_cast_now`, `CounterSpell`, `CantBeCountered`, `SpellCountered`,
  `ReturnToHand`, `TapAll`, the 702.16e gap; fuzz decks; docs; test-reviewer; PR.

## Decisions not yet in the docs

- **Approved by the user (2026-10-27):** a countered spell goes to its owner's graveyard
  directly (701.6a), through the event pipeline as an ordinary zone change (new object, 400.7)
  so M6's replacement effects can modify it; *not* `resolved_spell_destination` (which is only
  "as it resolves": 715.3d, 720.3d, 702.27a). Tests: a countered permanent spell, a countered
  instant, and a countered Adventure goes to the graveyard, not exile. Update design.md §17.12,
  the defaults docstring, decisions.md and the M2.6 handoff note wording.

## Open questions

- none
