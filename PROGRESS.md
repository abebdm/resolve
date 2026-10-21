# PROGRESS: M2.1 (coverage-map test and rule defaults)

Task: step M2.1 of `docs/plans/m2.md`. Branch `claude/great-dirac-kuse4l`.

## Design (this session)
- `resolve.rules.defaults`: every 5.1 function; engine code calls them as `defaults.<name>(...)`
  (module attribute, so a `monkeypatch` seam works everywhere).
- `resolve.rules.legality`: `Action`, `PlayLand`, `Verdict`, `permissions`, `prohibitions`, `allowed`.
- `TurnState.segments` (remaining segments), `GameState.extra_turns`, `GameState.turn_direction`,
  `DecisionRequest.for_player`, `knows_identity` replaces `view.is_known_to`.

## Done
- Map test `tests/tooling/test_coverage_map.py` (passes on the real map; fails on every broken map).
- Tests first written (rules/test_rule_defaults.py, test_rule_default_seams.py, test_101_2_legality.py,
  test_723_controlling_a_player.py) and confirmed failing against stubs (52 failed, assertions on the
  engine ignoring the seams; defaults/legality stubs raise NotImplementedRule).
- Data fields added: TurnState.segments, GameState.extra_turns/turn_direction, DecisionRequest.for_player,
  WaitingFor.for_player, concede(by=) (ignored yet).

## In progress
- Implementing defaults/legality/engine wiring.

## Next
- Implement; docs; test-reviewer; PR.
