# PROGRESS: M3.5 (requirements, restrictions and costs; the Lure torture test)

Task: implement step M3.5 of `docs/plans/m3.md` (user prompt in the session).

## Done
- Tests first written (confirmed failing for the right reasons, see below):
  - tests/decisions/test_assignment_requirements.py (solver: NotAlone, AtMost, requirements,
    costly picks, brute-force check, random_legal, benchmark)
  - tests/rules/test_508_1_requirements_and_restrictions.py
  - tests/rules/test_509_1c_blocking_requirements.py
  - tests/cards/test_combat_rules_cards.py
  - tests/interactions/test_lure_ghostly_prison.py
  - tests/agents/test_autopay.py: test_autopay_pays_an_attack_cost, ..._a_block_cost
- Space vocabulary (NotAlone, AtMost, Requirement, CostlyPick; ChooseAssignment fields and
  validate), solver stubs; primitives (cards/primitives/combat.py), card definitions, fixtures,
  ForAttack/ForBlock purposes; excerpt with the five cards (Snapshot 2026-11-02).

## Next
- Implement the solver (assignment.py), compilers (rules/combat.py), legality prohibitions,
  costs in engine/combat.py (checkpoint, PayCosts, reversal), events' `cost`, ActionReversed
  `declaration`; text agent; fuzz probes, summary, exclusions (Nacatl Savage), decks.
- Docs, test review, PR.

## Decisions not yet in docs
- 802.4b: Mogg Flunkies' "blocks alone" and Silent Arbiter's blocking limit are judged per
  defending player's declaration (other players' blockers ignored).
- "flyer-only restriction" in the torture test: Test Stomper's restriction stands in.
- Silent Arbiter = two `AtMostCreatures(1, blocking=...)` abilities (plan's
  `AtMostCreaturesAttackAndBlock`).

## Tests confirmed passing before the implementation (they test what must not happen)
juggernaut needn't attack when tapped/sick; Warmonger affects only its controller's creatures;
Prison doesn't tax its controller's attacks; malformed answer refused first; Tollkeeper's cost
not required; Unicorn attacking another player; attacking isn't required when it costs; primitive
texts and definitions (data only).
