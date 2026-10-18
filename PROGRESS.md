# PROGRESS — M1.2 Turns, steps and priority

Task: implement M1 PR by PR (M1.1 to M1.5) per the plan the user approved in the session that
opened abebdm/resolve#12 (M1.1). Branch `claude/m1-2-turns`, built on `claude/m1-1-mulligans`
(PR #12, not merged yet). When #12 merges, merge main into this branch.

User changes to the plan (binding):
1. Type-line parsing must not make loading the card database fail. Unparseable type lines are
   recorded as such and raise only when the card is used: in a deck, in new_game, or by the
   coverage tool. Add a test that the database loads with one such card present.
2. Test "a short deck loses at the first upkeep" cites 121.4 and 704.5b as the governing rules;
   727.3 is only supporting evidence.

Approved ★ items: minimal 800.4 leaving the game in M1 (M1.5); concession withdraws the pending
request and the paused task re-asks via run() (fix StartGame.run re-drawing the chooser); replays
= seed + ordered answers and concessions; Commander mulligan rule removed (done in M1.1);
multiplayer always uses attack-multiple-players (802.2, no 507.1 choice); unimplemented legal
actions are offered and raise NotImplementedRule when chosen (601.2 casting; 305.1 land play and
305.6 mana abilities until M1.3).

## Environment note (cloud sessions)
PyPI is blocked here; the venv was assembled from the uv cache (ruff 0.16.8, not the locked
0.17.1). Run tools as `.venv/bin/python -m pytest`, `.venv/bin/ruff`, and
`.venv/bin/pyright --pythonpath .venv/bin/python`.

## Done
- Type lines (205): `resolve.data.types`, `CardFace.types`, unreadable cards refused only when
  used; tests in tests/data/test_type_line.py; coverage tool lists "Unreadable" and exits 1.
- Turn structure implemented (uncommitted → committed as WIP): `state/turn.py` (Phase, Step,
  TURN_SEQUENCE, TurnState), `GameState.turn`, `Player.lost`, `players_in_game`,
  `next_in_turn_order`; events `TurnBegan`, `StepBegan`, `PriorityPassed` (events/turn.py),
  `PlayerLost` (events/game.py), `CardDiscarded` (events/cards.py); options `PassOption`,
  `PlayLandOption`, `CastSpellOption`; `DecisionKind.DISCARD`; `effects/characteristics.py`;
  engine `turns.py` (FirstTurn, TakeTurn, RunStep, DiscardToHandSize), `priority.py`
  (PriorityRound, priority_options), `sba.py` (state_based_actions, CheckStateBasedActions,
  EndCheck); views: `TurnView`, `PlayerSummary.lost`; scenario `at(...)`, `card_of`;
  game_fixtures `Passer`, `pass_until`, `started_game`, `scenario_database/registry` (adds
  Test Shock instant, Test Ponder sorcery, split halves).
- Tests written first: tests/rules/test_500_turn_structure.py, test_117_priority.py,
  test_704_state_based_actions.py, test_514_cleanup.py (58 tests). All 58 confirmed failing
  with the turn tasks stubbed to raise NotImplementedRule("500.1: STUB") (54 raised the stub,
  4 asserted a different gap rule), then passing with the implementation.

- Old tests updated for the first turn (no assertion loosened): mulligan `act` returns the first
  turn instead of the 103.8 gap; 903.6 log-order test compares up to TurnBegan; gaps-tool test
  names 601.2; play_cli tests (empty decks now end in a draw at the first upkeep; a new
  play_game test reaches the 305.1 gap); fuzz tests (ALLOWED_GAPS, endings, new PatientAgent
  long games, oracle negatives for turn/lost).
- Infrastructure tests: tests/state/test_turn_state.py (sequence, invariants),
  tests/events/test_turn_events.py (events, characteristics), scenario at() tests, text agent.
- Full suite, ruff, pyright passing.

## Next
- Docs: decisions.md (priority pointers not events; offering gaps; 514.1 order via
  ORDER_CARDS 404.3; multiplayer attack-multiple-players 802.2; 109.3 multi-face gap;
  characteristics no cache; PatientAgent in fuzz tests), design.md §4 (turn), howto (scenario
  at()), CLAUDE.md status, roadmap (tick "phases and steps"), howto fuzz/play_cli notes.
- test-reviewer, PR (base claude/m1-1-mulligans), then M1.3-M1.5.
