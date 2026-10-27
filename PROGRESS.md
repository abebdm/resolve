# PROGRESS: M2.9 (cost reductions)

Task: implement step M2.9 of docs/plans/m2.md (prompt in its "Prompts" section).

## Done
- Tests first (confirmed failing for the right reason before the implementation):
  - tests/rules/test_601_2f_cost_modifiers.py (11 of 12 fail; the 601.8 "already on the stack"
    test is a must-not test that passes before);
  - tests/cards/test_emerald_medallion_and_kinjallis_caller.py (2 fail: the reductions; the
    others are definition and must-not tests);
  - tests/cards/test_cost_modifier_primitives.py (ReduceGeneric, SpellCostReduction.modifier
    stubs raise NotImplementedRule);
  - tests/data/test_mana_cost.py (`ManaCost.generic`, `with_generic` stubs).
- Fixtures: Emerald Medallion, Kinjalli's Caller (excerpt + scryfall fixtures), Test Thorn
  (test-only `SpellCostIncrease`/`IncreaseGeneric` in tests/game_fixtures.py), Test Growth
  registered.
- Stubs: `resolve.cards.primitives.cost_modifiers`, `definitions/cost_reducers.py`,
  `Quality.adjective`.

## Next
- Implement ManaCost.generic/with_generic, ReduceGeneric, SpellCostReduction.modifier,
  resolve.rules.costs (gathering + pipeline), wire into CastSpell._total.
- Autopay test, fuzz recipes, docs, test-reviewer, PR.
