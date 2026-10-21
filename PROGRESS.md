# PROGRESS: M2.3 (casting and resolving permanent spells)

Task: implement step M2.3 of `docs/plans/m2.md` (user prompt in the session; no PR yet).

## Done
- `resolve.state.spell`: cast variants, `CastPermission` (`FROM_HAND`, `COMMANDER`), `CastChoices`;
  `GameObject.spell` / `cast_record`.
- Options `CastSpellOption(object, variant, permission)`, `ManaOption`, `ManaActivationOption`;
  decision kinds `ACTIVATE_MANA_ABILITIES`, `REVERSE_MANA_ABILITIES`.
- `variant_characteristics` (601.3e); characteristics on the stack read the spell's variant.
- defaults: `cast_permissions`, `cast_options` (per permission and layout variant),
  `has_sorcery_timing(..., ignoring=)` (601.2e), `may_cast_now(..., variant, permission)`,
  `resolved_spell_destination` (608.2n). `legality.CastAction`.
- Written, untested: `resolve.state.checkpoint` (take/restore, 733.1 library check, leavers stay
  gone), `resolve.events.spells` (SpellProposed, SpellCast, ActionReversed,
  PermanentSpellResolved), `ManaSpent`, `Event.library_action`, Sol Ring definition
  (`definitions/mana_rocks.py`), purity walker allows a checkpoint's copies.

## In progress / next
- Stubs: `engine/casting.py` (CastSpell), `engine/resolution.py` (ResolveTopOfStack),
  `engine/payment.py` (only `PAY`).
- Next: write the plan's "Tests first" list (test_601_casting, test_608_resolving,
  test_733_illegal_actions, tests/cards/test_sol_ring.py), confirm failing; implement CastSpell
  stages, PayCosts as an embedded procedure (not a task on the stack: the cast needs its
  activations for 733.1), reversal, ResolveTopOfStack, priority fixes (117.3b, 117.3c, 733.2:
  CastSpell clears `passed` at 601.2i), views (`ObjectView.spell`), text agent, invariants,
  `Scenario.stack` building spells; fuzz recipes and allowed gaps (508.1, 903.8); excerpt Sol Ring;
  replace the 601.2/608.1 gap tests (test_117_priority, test_gaps_tool, test_play_cli).

## Decisions not yet in the docs
- A split card in hand still raises 109.3 in `characteristics` (709.4 is M5); `cast_options`
  offers its halves (checked on the half's characteristics), which raise 709.3 when cast.
- PayCosts is a procedure object embedded in the casting task, not a separate task.
- `CastPermission` leaves out alternative cost and destination fields until M2.10/M4.
