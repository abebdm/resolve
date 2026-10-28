# PROGRESS: M2.10 (casting during resolution, without paying the mana cost)

Task: implement step M2.10 of `docs/plans/m2.md` (prompt in its "Prompts" section).

## Done

- Checked M2.9 is merged (`main` at ff7825d).
- Read the plan, design.md §17.3/§17.6/§17.12, CR 608.2g, 118.9, 118.6a, 107.3b, 733.2 and
  Rishkar's Expertise's rulings (snapshot 2026-10-27).

## Design (within the plan; to record in docs/decisions.md)

- `CastPermission` gains `alternative_cost` (`WITHOUT_PAYING_MANA_COST`, 118.9) and
  `mana_value_at_most` (checked in `legality._cast_permissions` on the variant's characteristics,
  601.3e).
- A permission an effect grants is a `CastGrant(player, permission)` in
  `GameState.cast_grants`; `defaults.cast_permissions` reads it (the one place zones are allowed).
- `MayCastFromHand` (effect) -> task `CastDuringResolution` (engine/casting.py): adds the grant,
  asks `CAST_DURING_RESOLUTION` (decline first, then `cast_options` with that permission), runs
  `CastSpell`, asks again after a reversal (733.2), removes the grant.
- `CastSpell._x`: 107.3b, X announced 0 without asking; no hybrid announcement when the mana cost
  isn't paid. `_total`: base {0} (118.9, 118.6a), modifiers still apply (118.9d).
- `GreatestPower(EachCreature(controlled_by=You()))` value.

## Done since

- Tests first (35 confirmed failing for the right reason, commit "tests first"), implementation,
  docs (roadmap, coverage map, torture tests, primitives, howto, decisions, design §17.3,
  CLAUDE.md, README, plan handoff notes).
- Quick fuzz: 10 games pass. One-off prepared-board run: 300 games, invariants and pickle OK.

## In progress

- test-reviewer running.

## Open questions

- RESOLVED (user: pin the decks; done, decisions.md 2026-10-28). Was: the fuzz summary test asserts some of the first
  five default-run games reaches turn 10; with Rishkar's Expertise in the decks the max is 9
  (main: 11; 20 games now: 14). Changing it is the user's call (never loosen a test).
