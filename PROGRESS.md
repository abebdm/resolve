# PROGRESS — M1.3 Lands and mana

Task: M1 per the approved plan (`docs/plans/m1.md`, binding changes at its top). Branch
`claude/m1-3-lands`, built on `claude/m1-2-turns` (PR #13, based on PR #12's branch). Neither is
merged yet; when they are, merge main into this branch.

Environment (cloud): PyPI is blocked; the venv was assembled from the uv cache (ruff 0.16.8).
Run `.venv/bin/python -m pytest`, `.venv/bin/ruff`, `.venv/bin/pyright --pythonpath
.venv/bin/python`.

## Done
- Tests first: tests/rules/test_305_lands.py, test_605_mana_abilities.py,
  tests/cards/test_basic_lands.py (39 tests). 25 confirmed failing before the implementation
  (21 at the 305.6 gap, 3 at the 305.1 gap, 1 "DID NOT RAISE" 302.6). 14 passed before it: the
  negative timing tests (no land outside main / other turn / with a stack / limit reached), the
  empty-pool test, the registry/decklist card tests, and two characteristics tests that were
  written after `characteristics` gained abilities (could not be confirmed failing).
- Implementation: state/mana.py, GameObject.tapped, Player.mana_pool, events/permanents.py
  (LandPlayed, PermanentTapped, PermanentsUntapped), events/mana.py, primitives (base.Ability,
  costs.TapSelfCost, effects.AddMana, abilities.ActivatedManaAbility/intrinsic_mana_ability),
  CardDefinition.abilities, characteristics abilities (305.6), definitions/basic_lands.py,
  ActivateAbilityOption, priority land play / mana activation (engine/mana.py), untap 502.3,
  pool emptying at step end, PriorityPassed.mana_in_pool, views/oracle/text/invariants, scenario
  tap()/mana(), fixtures (basic lands, nonbasic Forest, real Forest definition).
- ALLOWED_GAPS = 601.2, 800.4a. Tests updated for Forest being implemented.

## Next
- Docs: primitives.md entries, howto "add a card"/"add a primitive", decisions, design §4
  (mana pools, tapped), CLAUDE status, roadmap ticks. test-reviewer. PR (base claude/m1-2-turns).
