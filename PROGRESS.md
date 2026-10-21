# PROGRESS: M2.4 (mana abilities beyond basic lands, and summoning sickness)

Task: implement step M2.4 of `docs/plans/m2.md` (user prompt in session
https://claude.ai/code/session_012iD3s6Qtv27EbFpricYv19). Built on the unmerged M2.3 branch
(`claude/eager-lamport-370u58`, PR abebdm/resolve#29), as the user asked.

## Done
- Snapshot excerpt `tools/excerpts/cards.json` now holds the 7 M2.4 cards (+ earlier ones).
- Primitives (data; behaviour stubbed): `ManaPaymentCost` (costs.py), `ManaRestriction` base and
  `ForSpell`/`ForAbility` (state/mana.py), `SpendOnlyOnSubtype` (primitives/restrictions.py),
  `ControlsAtLeast` (primitives/conditions.py), `AddManaOfAnyColor` (effects.py),
  `ActivatedManaAbility.activate_only_if`, `.mana_cost`.
- Definitions: mana_rocks (Arcane Signet, Selesnya Signet), mana_creatures, nonbasic_lands.
- `DecisionKind.CHOOSE_COLOR`, `ColorOption`; text agent describes them.
- `GameObject.entered_turn`, `Player.last_turn_began`; scenario `entered_turn=`, `at(last_turns=)`.
- Tests first, all confirmed failing on the stub gaps (51 tests).

## Status
- Implementation done; targeted tests pass; docs updated (decisions, design, primitives,
  roadmap, torture tests, howto, verification, CLAUDE.md, README, handoff notes).
- Running: full suite + pyright + quick fuzz; test-reviewer.

## Next (original list)
- Implement: can_tap_for_cost, TurnBegan/create_object set the fields, commander identity,
  colors, ControlsAtLeast.met, restriction allows + PayCosts filtering, nested PayCosts in
  ActivateManaAbility with checkpoint and reversal, flattened activations + 733.1 dependency
  check, ManaSpent.redo, CHOOSE_COLOR in ActivateManaAbility, priority clears passes only when an
  activation completes.
- Fuzz, docs, test-reviewer, PR.

## Decisions (not yet in docs)
- PayCosts.activations holds the ActivateManaAbility tasks themselves (shared references), so
  nested activations are visible to the outer reversal.
- 733.1 dependency check: replay kept activations' mana events on the checkpoint's pool; a kept
  ManaSpent whose units aren't there is refused (identical units: lenient).
