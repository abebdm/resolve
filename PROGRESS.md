# PROGRESS: M3.2, declaring attackers and unblocked damage

Task: implement step M3.2 of `docs/plans/m3.md` (user prompt in the session; branch
`claude/friendly-einstein-8ea1q0`).

## Done

- Checked: M3.1 is merged into `main` (PR abebdm/resolve#42); the branch starts from `main`.
- Card data checked against the snapshot of 2026-10-30: Raging Goblin ({R}, 1/1, Haste), Alaborn
  Grenadier ({W}{W}, 2/2, Vigilance), Wall of Stone ({1}{R}{R}, 0/8, Defender); no rulings.

- Tests first written and confirmed failing (commit "M3.2: tests first"): the 508.1 gap
  (`NotImplementedRule("508.1")` from `engine/turns.py`), stubs raising `NotImplementedRule`
  (`legality.AttackAction`, `resolve.events.combat`), the three cards registered without
  abilities. `test_the_abilities_text` passes on the keyword stubs (they are the values).

## In progress

- Implementing.

## Next

- Implement; run every check and the quick fuzz; test-reviewer; docs; PR.

## Decisions not yet in the docs

- Combat state: `CombatBegan` (506.2) as the first step of the combat phase begins, `CombatEnded`
  (511.3) as the end of combat step ends: events in `resolve.events.combat`.
- The scenario builder's `at(...)` creates the (empty) combat state in the combat phase, except
  at the beginning of combat step started from its beginning (the engine creates it then).
- 508.1f taps with `PermanentTapped` events in one set (no new `PermanentsTapped`).
- `Passer` declares no attackers.

## Open questions
