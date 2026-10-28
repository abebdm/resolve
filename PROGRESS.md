# PROGRESS — M2.11 (wrap-up)

Task: implement step M2.11 of `docs/plans/m2.md` (prompt in the plan's "Prompts").

## Decisions so far (the user's, 2026-10-28)

- The thorough fuzz run on main missed the plan §8 expectations (21 of 26 cards cast; 0 didn't
  resolve, 0 countered, 0 damage; no decked or life-total endings).
- **User's answer:** add a "caster" fuzz seat (a random agent that, given priority, casts an
  offered spell, paid by the auto-payer); keep a mix of seats (random, auto-pay, caster) so
  illegal actions are still explored. In verification.md list each expectation the thorough run
  can't meet yet, with its reason and the milestone that makes it reachable (decking,
  life-total endings and damage after M3 removes 508.1; Decimate needs an enchantment in the
  fuzz cards). Add an M3 roadmap item to restore them; note the prepared-board check as a
  possible later tooling item.

## Done

## In progress

## Next

- CasterAgent (`resolve.agents.caster`) + tests; seat kinds in tools/fuzz.py.
- gaps-vs-map test; coverage-map ticks; docs; delete the plan.
