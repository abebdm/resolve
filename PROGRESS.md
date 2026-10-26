# PROGRESS: M2.7 (modes and X)

Task: implement step M2.7 of `docs/plans/m2.md` (user prompt, session
https://claude.ai/code/session_019NjyT5tmWx2kXf97h4y35b). Branch `claude/eloquent-wright-vwpk4r`.

## Done

- Checked M2.6 is merged into `main` (PR #33).
- Downloaded the Scryfall snapshot (2026-10-26) for Fiery Confluence's Oracle text and rulings.

- Tests first (confirmed failing on the 700.2/601.2b gaps, the `with_x` stub and X's text).
- Implementation: `CastSpell` stages `MODES`, `X`, `TARGETS`; `targeting.legal_modes`,
  `mode_choices`; modal resolution (`Instruction`); `X` value; `ManaCost.with_x`/`has_x`;
  mana value with X on the stack; Fiery Confluence; text agent's `ModesOption`.
- Fuzz-summary test widened to five games (the first four no longer had a payable cast reversed
  by a random seat); brute-force auto-pay search includes Test Blaze.

## Next

- Full suite, pyright, quick fuzz, gaps tool; test-reviewer; docs; PR.

## Decisions so far (not yet in docs)

- A mode choice is a multiset of mode indices, listed in printed order (700.2d: "as if that mode
  appeared that many times in sequence"); the relative order of a repeated mode's instances
  (the ruling's "you choose their relative order") is the order its targets are chosen.
- The total cost (601.2f) replaces each {X} with a generic symbol of the announced value
  (107.3a), so `PayCosts` and `PaymentView.cost` see what is actually paid.

## Open questions

- none
