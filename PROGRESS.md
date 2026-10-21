# Progress: M2.1 (coverage-map test and rule defaults)

Task: implement M2.1 of docs/plans/m2.md. Branch claude/vibrant-bardeen-num3yx.

## Done
- coverage-map module + tests; rule-default functions (engine/defaults.py), legality skeleton,
  turn frame/segments/extra turns, deciding_player/for_player, knows_identity, tests (full suite
  passes, fuzz summary identical to main).

## In progress
- extra tests (ManaLost event, invariants, view), docs (howto, primitives?, decisions,
  roadmap map rows, torture, CLAUDE.md status, README, plan handoff), test-reviewer, PR.

## Decisions not yet in docs
- ManaLost event for partial pool emptying (ManaPoolEmptied keeps its whole-pool guard).
- land-play limit (305.2b) modelled as a prohibition in legality; land_play_options includes timing.
- decider who left the game -> player decides for themselves (800.4a).
- cut_rest_of_turn is a function the ending effect calls (M9 wires it).
- TurnBegan carries segments (existing test updated to name them).
