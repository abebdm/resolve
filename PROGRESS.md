# PROGRESS: M3.1 (Foundations: the spaces, summoning sickness, the combat state)

Task: implement step M3.1 of `docs/plans/m3.md` (user prompt in session; branch
`claude/festive-gates-9pz4rm`).

## Done

- Read the plan's M3.1, sections 3.1, 3.2, 3.6, 3.8, 3.11, 5, design.md §6, §17.8, §17.18.
- M3.0 is merged into `main` (PR #41).

## In progress

- Writing the "Tests first" list.

## Next

- Confirm failures, implement, checks, fuzz, test-reviewer, docs, PR.

## Decisions not yet in the docs

- `ChooseAssignment` in M3.1 has `items`, `choices`, `maxima` only; `constraints`,
  `requirements` and `costly` join it in M3.4/M3.5 (the step says "without constraints yet").
- `DistributeEach(sources, parts)`: `sources` names the creature each part divides (a UI needs
  it); answer value `AmountsEach(amounts)`, one `Amounts` per part.
- `CombatState` has no `phase` number until M3.8 (numbered segments), and no `first_strike`
  until M3.6.

## Open questions

- none
