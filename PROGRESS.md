# PROGRESS: M3.1 (Foundations: the spaces, summoning sickness, the combat state)

Task: implement step M3.1 of `docs/plans/m3.md` (user prompt in session; branch
`claude/festive-gates-9pz4rm`).

## Done

- Read the plan's M3.1, sections 3.1, 3.2, 3.6, 3.8, 3.11, 5, design.md §6, §17.8, §17.18.
- M3.0 is merged into `main` (PR #41).

- Tests first, each confirmed failing for the right reason against stubs (2026-10-31):
  - `tests/decisions/test_answer_spaces.py`: the ChooseAssignment and DistributeEach tests
    (stub `validate` raised `NotImplementedRule`; no `ValueError` from the constructors);
  - `tests/agents/test_random_agent.py`: inside-the-space, uniformity, both-spaces tests
    (`RandomAgent can't answer`); `tests/agents/test_text_agent.py`: hints, parsing, rendering,
    the round trip and the combat line (`can't be typed yet`, no combat shown);
  - `tests/fuzz/test_fuzz.py::test_every_probe_answer_is_invalid` for the new spaces;
  - `tests/rules/test_302_6_summoning_sickness.py`: the haste tests (still sick);
  - `tests/rules/test_rule_defaults.py`: citations and the five new defaults (stubs raised
    `NotImplementedRule`), `summoning_sick` for both purposes (haste ignored);
  - `tests/state/test_combat_state.py`: the invariants (none reported), the view (no combat);
  - `tests/engine/test_scenario_builder.py::test_an_illegal_combat_is_refused_when_built`.
  - Renamed, not loosened: the M2 `can_tap_for_cost` tests (`summoning_sick`, `patch_sickness`).

## In progress

- Implemented; docs updated; running the full suite and fuzz, then the test-reviewer.

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
