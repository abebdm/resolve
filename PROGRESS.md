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

## In progress: addressing the review findings

1. **Wrong tests: commanders are put into the command zone before 103.1.** The reviewer is right:
   103.2 says the 103.2c step (commanders into the command zone) happens *after* the starting
   player is determined, and 101.4e plus 613.7m order their timestamps APNAP from the starting
   player. Plan:
   - `initial_state` puts commanders in the library with the rest of the deck, which stands for
     the deck before 103.3.
   - `StartGame` then applies a simultaneous `CommanderPutIntoCommandZone` event for each player,
     in turn order. It is a zone change, so each commander becomes a new object with a new
     ObjectId and timestamp (400.7, 613.7d, 613.7m).
   - A player with more than one commander raises `NotImplementedRule("613.7m: ...")`, because
     that player chooses the relative order.
   - Fix both tests to check commanders after the choice, and record the change in decisions.md.
2. **Missing tests:**
   - every player's library is shuffled, not only player 0's (103.3)
   - a Commander game played through the choice (903.6)
   - views and log visibility in the real 103.1 flow (402.3, design §9)
   - no shuffle before the choice (103.3)
   - life comes from the config (103.4)
   - 109.4c: emblems are controlled; make `create_object` raise `NotImplementedRule("109.4c")`
     for a controller in the command zone instead of `EngineError`
3. **Hollow test:** `test_decision_kinds_have_distinct_values` can't fail, because Enum aliases
   duplicate values. Use `@enum.unique` and check `__members__`.
4. The replacement and trigger hook test is a placeholder; keep it and explain in the PR.

## Next

- Re-run the reviewer (the changes to commander placement are substantial).
- Move anything lasting from here into the docs, delete PROGRESS.md, open the PR. The PR
  description includes the reviewer's verdict, how each finding was handled, and which parts were
  test-first. None of M0 was strictly test-first: it began before the rule. The review fixes
  above are written test-first.

## Decisions not yet in the docs

- Commander placement moves to after 103.1 (finding 1). Goes into decisions.md once done.

## Open questions for the user

- None.
