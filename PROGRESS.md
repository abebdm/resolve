# PROGRESS: M2.2 (mana costs, spell characteristics, typed words, ChooseCounts)

Task: implement step M2.2 of `docs/plans/m2.md`; open a PR when done (delete this file first).

## Done
- Tests first written (`tests/data/test_mana_cost.py`, `tests/rules/test_202_mana_cost_and_color.py`,
  `tests/rules/test_612_typed_words.py`, additions to the answer-space, random-agent, text-agent,
  fuzz and vanilla-creature tests); stubs raise `NotImplementedRule`.
- `tools/excerpts/cards.json` written from the 2026-10-21 snapshot (the snapshot is local only).

## In progress
- Implementation: `data/mana_cost.py`, `CardFace.cost`, `Characteristics` fields, `words.py`,
  `ChooseCounts` and its agent support, fuzz probes.

## Next
- Checks, quick fuzz, test-reviewer, docs (roadmap map rows, primitives, howto, decisions, status,
  README, plan handoff notes), PR.

## Notes
- The 2 two-face (`prepare`/`omen`) 109.3 test cases already pass before the change; only the
  one-face data cases fail for the right reason.
