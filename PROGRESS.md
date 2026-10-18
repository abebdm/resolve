# PROGRESS — M1.5 Concession and leaving the game

Branch `claude/m1-5-concession`, built on `claude/m1-4-creatures` (PR #15 → #14 → #13 → #12,
none merged). The M1 plan (docs/plans/m1.md) is already deleted on this branch; read it with
`git show origin/claude/m1-4-creatures:docs/plans/m1.md`. Task from the user: verify #12-#15,
finish M1.5, open its PR against `claude/m1-4-creatures`.

## Done
- Tests first: tests/engine/test_concede.py, tests/rules/test_800_4_leaving_the_game.py (23
  tests): all 23 confirmed failing (19 at the `104.3a` concede stub, 3 at the old `800.4a`
  gap, 1 asserting another gap rule).
- Implementation: concede(), LeaveGame/EndCheck, re-entrant asking tasks, 800.4k, replays with
  concessions, fuzz concessions. Fuzz found the "holder leaves after all others passed" bug
  (fixed with a regression test).
- Docs (commit 6b88a90): design §3/§5/§10/§12, decisions, howto, roadmap, status, plan deleted.
- Session 2 verification of #12-#15 (all CI green, PROGRESS absent, descriptions complete).
  Fixes pushed to the earlier branches and merged forward:
  - #13: the broad fuzz test was hollow (decks ≤6 cards, every game a draw at 103.5's draws);
    decks now 7-11 cards, priority asserted, every owned object counted. Superseded mark on the
    M1.1 flag-clearing decision.
  - #14: CLAUDE.md M1.2 line (land plays no longer a gap), design §6 ActivateAbilityOption,
    play_cli docstring.
  - #15: decisions: pools empty in APNAP order; vanilla creatures checked against the
    2026-10-18 snapshot.
  - Here: two elves per fuzz deck (keeps the suite at ~140 s).
- test-reviewer on origin/main...this branch: Adequate with gaps, no wrong tests.

## In progress
- Addressing the review's findings, tests first (see "Findings" below).

## Findings to address (test-reviewer, session 2)
1. Concession during SBA graveyard ORDER_CARDS (`_still_apply`), 4 players.
2. Concession during cleanup DISCARD (AP concedes) and during its ORDER_CARDS (NAP concedes).
3. 800.4j: no discard and no land play for others in a departed AP's turn.
4. 117.4 with a non-holder leaving: (a) one who passed, (b) one who didn't.
5. Starting player concedes during 3p mulligans: P1 takes turn 1 and draws.
6. 800.4a leaves other players' objects (tapped Forest, damaged Bears) alone.
7. 800.4a in Commander (commander leaves the command zone).
8. Concession during PUT_ON_BOTTOM and during its ORDER_CARDS.
9. Non-chooser concedes during 103.1.
10. New request ids for MULLIGAN and DISCARD after a concession.
11. An answer from a player who left is rejected.
12. Replay of a concession that no longer applies raises ReplayDiverged.
13. PlayerLeftGame's public form shows library IDs (design §9): redact.
Hollow: 800.4j test claims; `any(Conceded) or players == 2`; card conservation in the
concession fuzz test.

## Next
- Then: re-run test-reviewer, delete PROGRESS.md, end-of-M1 verification (fuzz with basic-land
  decks needs a snapshot: `tools/fetch_scryfall.py --data-dir <scratch>`), play_cli decking
  game, open the PR against claude/m1-4-creatures, update #13-#15 descriptions.

## Open questions
- None.
