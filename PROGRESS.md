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

- Tests first (confirmed failing: the 509.1 and 510.1c gaps, blocks_allowed 1 for Palace Guard,
  BlockersDeclared ignoring defending_player); implementation; docs (roadmap, map, torture
  tests, primitives, howto, decisions, verification, plan sections and handoff, CLAUDE.md,
  README). Quick fuzz passes (10 games, 57 s, gaps 903.8 x3). Pyright, ruff clean.

## In progress

- Full suite run; test-reviewer.

## Next

- Handle review findings; delete PROGRESS.md; PR.

## Open questions

- none
