# PROGRESS — M2.6 (targets, last known information, values and the first effects)

Task: implement step M2.6 of `docs/plans/m2.md` (user prompt in the session; branch
`claude/tender-franklin-ln27dl`).

## Done
- Checked M2.5 is merged into `main`.
- Data and primitives (no engine wiring yet): `CastChoices.targets` (`TargetObject`,
  `TargetPlayer`), `LastKnown` (`resolve.state.last_known`, recorded by `move_object`),
  `resolve.cards.primitives.refs` / `values` / `targets` / `spells`, effects `DealDamage`,
  `Destroy`, `Exile`, `GainLife`, `DrawCards`, `resolve.effects.evaluation`, events
  `DamageDealt`, `LifeGained`, `ObjectExiled`, `BecameTargets`, `SpellDidNotResolve`,
  `SpellResolved`; `legality.TargetAction`/`DestroyAction`/`Targeter` (permissions stubbed),
  `resolve.rules.targeting` (stubs); definitions Swords, Chandra's Ignition, Decimate
  (`definitions/removal.py`), fixtures (Test Shock, Ponder, Shatter, Wall, Totem, Artifact Land
  Creature); `Scenario.targets`; excerpt updated (14 cards).

## In progress
- Tests first (plan's list), then confirm they fail.

## Next
- Wire: `CastSpell` targets stage, `cast_options` 601.2c filter, `ResolveTopOfStack` +
  `ResolveSpell`, `target_problem` permissions, last_known clearing in `PriorityRound`, view/text
  targets, fuzz stats (damage, didn't resolve), docs, test review, PR.

## Decisions not yet in the docs
- The spell ability is `CardDefinition.spell`, read through `Characteristics.spell_ability`.
- A spell with no legal targets isn't offered (filter in `cast_options`).
- `SpellDidNotResolve` goes to the owner's graveyard directly (608.2b), not via
  `resolved_spell_destination` (608.2n only).
- No last known information for card-less objects yet (no characteristics to compute).

## Open questions
- none
