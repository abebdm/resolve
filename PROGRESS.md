# PROGRESS: M3.3 (declaring blockers, and dividing damage)

Task: implement step M3.3 of `docs/plans/m3.md` (prompt from the user, 2026-10-31).
Branch: `claude/intelligent-edison-29zwm4`.

## Decisions so far (not yet in the docs)

- **The user's answer (2026-10-31):** protection's blocking part (702.16f, 702.16j) moves from
  M3.4 into M3.3, as a prohibition of `BlockAction`: without it M3.3 would silently allow
  illegal blocks against Nacatl Savage (in the fuzz decks). The plan's M3.3 and M3.4 sections and
  the coverage-map row are to be updated. Checked: no other fuzz-deck creature has a blocking
  restriction (only Nacatl Savage and Repentant Blacksmith, both protection).
- Palace Guard's card data checked against Snapshot 2026-10-31 ({2}{W} Human Soldier 1/4, "This
  creature can block any number of creatures."; no rulings). Excerpt rewritten from it.
- Each defending player's declaration is applied as its own `BlockersDeclared(blocks,
  defending_player=p)`, fixing the blocked status of the attackers attacking p (802.4, 509.1h);
  a final `BlockersDeclared()` fixes any attacker still undecided (attacking a player who left).
- `CombatDamage` keeps each player's answered assignment with its space; re-run after a
  concession it reuses an answer only if the player's space is unchanged (else asks again).

## Done

- Read the plan, design, code. Excerpt has Palace Guard.

## In progress

- Tests first, with stubs.

## Next

- Implement; checks; fuzz; test-reviewer; docs; PR.

## Open questions

- none
