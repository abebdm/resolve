# PROGRESS — M1.4 Creatures and damage

Branch `claude/m1-4-creatures`, built on `claude/m1-3-lands` (PR #14; #13 and #12 below it,
none merged). Plan: docs/plans/m1.md. Env: PyPI blocked; use `.venv/bin/...` tools.

## Done
- Tests first (704.5f/g, 404.3 SBA ordering, 208.2, 514.2, 514.3a with a creature, vanilla
  creature cards): 11 confirmed failing for the right reason (no creature SBAs / no damage
  removal); the negative ones and card characteristics tests passed before (characteristics P/T
  was written first).
- Implementation: damage, P/T, PutIntoGraveyard / PermanentDestroyed / DamageRemoved,
  CheckStateBasedActions with ORDER_CARDS, RemoveDamage, views/oracle/invariants/text, docs.

## Next
- test-reviewer, PR (base claude/m1-3-lands), then M1.5.
