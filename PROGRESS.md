# PROGRESS — M1.5 Concession and leaving the game

Branch `claude/m1-5-concession`, built on `claude/m1-4-creatures` (PR #15 → #14 → #13 → #12,
none merged). Plan docs/plans/m1.md (delete it in this PR). Env: PyPI blocked; `.venv/bin/...`.

## Done
- Tests first: tests/engine/test_concede.py, tests/rules/test_800_4_leaving_the_game.py (23
  tests): all 23 confirmed failing (19 at the `104.3a` concede stub, 3 at the old `800.4a`
  gap, 1 asserting another gap rule).
- Implementation: Player.left_game; PlayerLeftGame, Conceded events; LeaveGame, EndCheck
  continuing games; concede(); re-entrant StartGame/OpeningHands/PriorityRound/
  DiscardToHandSize/CheckStateBasedActions; TakeTurn 800.4k; draw skip for a departed AP;
  resolve.agents.replay (inputs = answers + concessions); fuzz concessions + replay; views.
- Fuzz caught a bug (holder leaves after everyone else passed → step must end, 117.4); fixed
  with a regression test (mutation-checked).

## Next
- Docs: design §3/§5/§12, decisions, howto, CLAUDE status (M1 done → M2), roadmap M1 ticks,
  delete docs/plans/m1.md. test-reviewer. PR.
