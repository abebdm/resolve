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
- Tests first written and run: 41 fail for the right reason (no target choice, the 608.2c gap,
  the stubs): tests/rules/test_115_targets.py (all 11), test_608_resolving.py (6 new),
  tests/cards/test_swords_to_plowshares.py (6), test_chandras_ignition.py (7),
  test_decimate.py (5), test_608_2h_last_known_information.py (forgetting), test_101_2_legality
  (3 destroy), test_spell_primitives (Destroy), the destination seam test. Passing at once
  (written with their code): primitive texts/filters/evaluate, the event tests, LKI recording.

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
