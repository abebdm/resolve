# Progress: M0 engine core

Working note (CLAUDE.md, "Work in checkpoints"). Deleted before the PR is opened.

## Task

The M0 engine core, from the user's request in the Claude Code session (no PR yet): core state
types, the task loop and public API, decision request/answer types with validation, the event
skeleton and log, `NotImplementedRule`. The design proposal (A–G) and two additions (sharing
`Immutable` values on deepcopy plus a deep-immutability test; a test that every cited CR number
exists) were approved. The scenario builder, agents, CLI and fuzz harness are out of scope.
Branch: `claude/elegant-wozniak-l9r1o6`.

## Done

- Engine core implemented: `resolve.state`, `resolve.tasks`, `resolve.engine`,
  `resolve.decisions`, `resolve.events`, `resolve.errors`, `resolve.values`, `resolve.citations`,
  `tools/gaps.py`.
- 455 tests passing; ruff and pyright clean.
- Docs: design.md (A–G), decisions.md entries, howto recipes, roadmap ticks plus 103.5 added to
  M1, CLAUDE.md Current status and test folders.
- Merged `origin/main` twice (PR #7 tests-first and test review; PR #8 checkpoints).
- Ran the independent test review (general-purpose agent given `.claude/agents/test-reviewer.md`,
  which wasn't loaded in this session). Verdict: **Adequate with gaps.**

## Done since the review

All review findings are addressed (test-first where behavior changed). The suite has 469 tests,
and ruff and pyright are clean.
1. Commander placement moved after 103.1: `PutCommandersIntoCommandZone` and
   `CommanderPutIntoCommandZone`, built on the new `move_object` (400.7).
   - Tests confirmed failing first, on their assertions:
     - `test_103_2c_commanders_stay_in_their_decks_until_the_starting_player_is_chosen`
     - both `test_903_6_*` tests
     - both `test_613_7m_*` tests
   - Two tests were corrected for the new ordering:
     - `test_view_shows_public_zones_to_everyone` now looks after the choice
     - the old 903.6 test was replaced
2. The missing-coverage tests were added. These passed at once, because they cover behavior that
   was already right:
   - every library is shuffled
   - no shuffle before the choice
   - life comes from the config
   - views in the real 103.1 flow
   - a shuffle touches only the named library
3. 109.4c: `create_object` and `move_object` raise `NotImplementedRule` for a controlled object
   in the command zone. Confirmed failing first (it was an `EngineError`).
4. 400.7 `move_object` tests: confirmed failing against a `NotImplementedRule` stub first.
5. `DecisionKind` is `@unique`, and its test now checks `__members__`. The test couldn't have
   failed before, since the kinds were already unique.
6. The hook-placeholder test is kept as is; the PR explains why.

## Done: second review (verdict Adequate with gaps), all findings addressed

- Wrong: 400.3 is a redirect ("it goes to its owner's corresponding zone"), not an error. Plan:
  `create_object` and `move_object` redirect a per-player zone to the owner's, and the two 400.3
  tests assert the redirect. Fix the Two-Headed Giant docstring (103.4a/810.4: shared team life).
- Missing (tests first): a failed move leaves the state unchanged; 109.4c through `move_object`;
  `known_to` set before a move is dropped; controller dropped off the stack and required onto the
  battlefield; a Commander game in the purity/invariant states; the 903.3 designation (`CardId`)
  survives the move; command to command is a new object (400.10); commander log entries are
  public; life still set after the procedure; a Commander deck without a commander (deferred to
  M7, documented by a test).
- Recorded in decisions.md ("Moving objects between zones"), including the policy that events
  which move a card players saw set `known_to` themselves (M1).
- Test-first: the two 400.3 redirect tests failed on `EngineError` first. The other new tests
  passed at once (coverage of behavior that was already right). 479 tests; ruff and pyright
  clean. No third review round: the code change was the small 400.3 redirect, and the rest was
  tests.

## Next

- Re-run the reviewer: done (second round above).
- Move anything lasting from here into the docs, delete PROGRESS.md, open the PR. The PR
  description includes the reviewer's verdict, how each finding was handled, and which parts were
  test-first. None of M0 was strictly test-first: it began before the rule. The review fixes
  above are written test-first.

## Decisions not yet in the docs

- None: commander placement and `move_object` are in decisions.md.

## Open questions for the user

- None.
