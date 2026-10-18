# PROGRESS — M1.1 Opening hands and mulligans (103.5)

Task: implement M1 PR by PR (M1.1 to M1.5) per the approved plan (session prompt; plan in the
PR descriptions). This branch: M1.1, `claude/m1-1-mulligans`, from main 5e9d319.

User changes to the plan: type-line parsing must not fail database loading (M1.2); test 33 cites
121.4 and 704.5b (M1.2).

## Done
- Tests first: `tests/rules/test_103_5_mulligans.py`, `tests/rules/test_121_drawing.py`.
  All 35 confirmed failing before implementation: 29 at `NotImplementedRule("103.5")` (the M0
  gap), 6 at the `NotImplementedRule("121.1")` stub of `DrawCards`.
- Stubs: `NamedOption`, `PUT_ON_BOTTOM`/`ORDER_CARDS`, `events/cards.py`, `MulliganDeclared`,
  `LogEntry.redacted`, `Player.drew_from_empty_library`, `engine/drawing.py`, `engine/mulligans.py`.

## Next
- Implement: `Event.apply` returns the applied event; pipeline logs `redacted`; views show the
  redacted form; `move_object(bottom=True)`; DrawCards; OpeningHands; 103.8 gap.
- Update M0 tests that relied on the 103.5 gap; fuzz ALLOWED_GAPS; play_cli/text agent.
- Docs, test-reviewer, PR.
