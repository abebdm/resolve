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

## Done (uncommitted work is committed as WIP)
- `src/resolve/data/types.py`: `TypeLine`, `CardType`, `Supertype`, `parse_type_line`,
  `try_parse_type_line` (205; "Time Lord" two-word subtype; plane subtype = whole phrase).
- `CardFace.types` is derived in `__post_init__` (None when unparseable),
  `CardFace.type_line_problem`, `CardData.type_line_problems`.
- `DeckCard.__post_init__` refuses unreadable type lines (DeckError); coverage has
  `CoverageStatus.UNREADABLE` and `DeckCoverage.unreadable`; `build_deck` lists them.
- NOT done yet for this part: tests (tests/data/test_type_line.py: parsing cases, unknown word,
  empty, dash with nothing; database loads with an unparseable fixture card; DeckCard/new_game
  refuse it; coverage reports UNREADABLE) and `tools/coverage.py` report section for unreadable
  cards (it currently shows only Unknown/Missing/Implemented; exit status should treat
  unreadable like unknown).

## Next (design, from the approved plan)
- state/turn.py: `Phase`, `Step` enums; `TurnState(number, active_player, phase, step,
  priority, passed: list, lands_played)`; `GameState.turn`; `Player.lost`.
- Events: `TurnBegan`, `StepBegan` (500.6), `PriorityPassed` (117.3d), `PlayerLost`
  (704.5a/b), `CardDiscarded` (701.9a; several at once → owner orders them, 404.3, via
  ORDER_CARDS listed top to bottom), DecisionKind `DISCARD` (514.1).
- Tasks: `TakeTurn(player, position, started)` over the STEPS constant; `RunStep` (begin event,
  turn-based actions, PriorityRound, end); skip draw step on turn 1 in 2-player games (103.8a);
  508.8 skip blockers/damage; 508.1 gap if AP controls a creature; cleanup 514.1 discard to 7
  (402.2), 514.3a SBA → priority + another cleanup; `PriorityRound` (SBA check → ask →
  pass/act; all players in game passed → step ends, or 608.1 gap with non-empty stack);
  `StateBasedActions` (704.5a/b as one event, clears drew flags; losses → 2p game ends
  104.2a/104.4a draw; multiplayer survivors ≥2 → NotImplementedRule("800.4a")).
- Priority holder is set directly by tasks (procedural pointer, not an event); record in
  decisions.md.
- Priority options: PassOption, PlayLandOption (gap 305.1 until M1.3), CastSpellOption
  (117.1a/302.1/304.1/307.1 timing; commanders in command zone 903.8; gap 601.2);
  multi-faced cards: transform/modal_dfc use front face (712.8a), others raise a gap; a land
  with a basic land type on the battlefield → NotImplementedRule("305.6") until M1.3.
- `resolve.effects.characteristics.characteristics(state, obj)` skeleton (no layers).
- Views: turn info, `lost`; fuzz oracle checks them; ALLOWED_GAPS for M1.2.
- Scenario builder: `at(step, active=..., number=..., priority=..., passed=..., lands_played=...)`
  and `build()` pushes `TakeTurn` resuming at that step.
- Tests first (plan tests 20-40) in tests/rules/test_500_turn_structure.py,
  test_117_priority.py, test_704_state_based_actions.py, test_514_cleanup.py; full 2p decking
  game with 10-card decks ends on turn 8, P1 loses, each graveyard 3 cards.
- Docs, test-reviewer, PR; then M1.3-M1.5.
