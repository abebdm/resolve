# PROGRESS: M2.5, the agent-side auto-payer

Task: implement step M2.5 of `docs/plans/m2.md` (the user's prompt in the session; PR to come).

## Decisions (recorded in docs/decisions.md, 2026-10-22)

- Payments under way and permanents' abilities in the view (approved by the user).
- New "done when": payable casts reversed per kind of seat; the planner cross-checked against a
  brute-force search (approved by the user).

## Done

- View, auto-payer, fuzz seats and `PayableCasts`, `play_cli --autopay`, renderer, fuzz view
  oracle, brute-force test with `--thorough` (`tests/conftest.py`). Docs: decisions, plan (M2.5
  and handoff), howto, verification, design §9/§17.7, roadmap, torture tests, CLAUDE.md, README.

## In progress

- The `--thorough` brute-force run (20 000 boards) failed once; finding the boards it reports.

## Next

- Fix what it finds (regression tests first), full suite, quick fuzz, test-reviewer, PR.
