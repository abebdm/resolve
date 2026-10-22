# PROGRESS: M2.5, the agent-side auto-payer

Task: implement step M2.5 of `docs/plans/m2.md` (the user's prompt in the session; PR to come).

## Decisions so far (move to the docs before the PR)

- **Approved by the user (2026-10-22): payments in the view.** The plan didn't say how a
  view-only agent learns what it is paying. `PlayerView.payments` lists the payments under way
  (outermost first: payer, cost, purpose, and the restrictions that allow spending mana on it,
  106.6, evaluated by the engine); `ObjectView.abilities` gives each permanent's abilities as
  engine-computed `AbilityView`s (text, mana cost, the mana it can make now). Goes into
  design.md §6/§9/§17.7 and decisions.md.

## Done

## In progress

- Tests first: `tests/engine/test_view_abilities_and_payments.py`, `tests/agents/test_autopay.py`.

## Next

- Implement the view, `resolve.agents.autopay`, `play_cli --autopay`, fuzz seats; docs; review.
