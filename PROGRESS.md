# PROGRESS: M3.4 (evasion and blocking restrictions)

Task: implement step M3.4 of `docs/plans/m3.md` (the user's prompt in this session).

## Done
- Checked M3.3 is merged (main at e9f3f40). Snapshot 2026-10-31 downloaded (pin in
  `docs/rules/README.md` left unchanged); the seven cards' text matches the plan.
- `tools/excerpts/cards.json` rewritten with the seven new cards.

## In progress
- Stubs, then the "Tests first" list, then the implementation.

## Next
- Implementation, checks, fuzz, test-reviewer, docs, PR.

## Decisions not yet in the docs
- `NoneOrAtLeast(choice, minimum)` lives in `resolve.decisions.spaces` (data); the solver
  (`resolve.decisions.assignment`) checks it and draws `random_legal` answers (random per-item
  subsets, then each broken constraint repaired by filling it up or clearing it).
- The block compiler drops a choice that fewer creatures can block than its `NoneOrAtLeast`
  minimum (no legal declaration has it), so a lone blocker isn't offered a menace attacker.
- 702.16k: `PlayerQuality(player)`; qualities gain `matches_source(characteristics, controller,
  owner)` (default: `matches`), used by targeting, blocking and the 702.16e gap.
- Landwalk's land type is `LandTypeQuality(LandTypeWord)` (612.2 can rewrite it); the defending
  player is the one the attacker attacks (802.2a).

## Open questions
- none
