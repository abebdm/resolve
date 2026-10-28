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

## In progress

- Stubs and tests first.

## Next

- Implement; checks; fuzz; test-reviewer; docs; PR.

## Open questions

- none
