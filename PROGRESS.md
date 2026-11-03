# PROGRESS: M3.5 (requirements, restrictions and costs; the Lure torture test)

Task: implement step M3.5 of `docs/plans/m3.md` (user prompt in the session).

## Done
- Tests first (confirmed failing for the right reasons), then the implementation: solver,
  compilers, prohibitions, costs with checkpoint and reversal, text agent, fuzz probes, summary,
  exclusions; docs (roadmap, coverage map, torture tests, primitives, howto, decisions,
  verification, plan handoff, CLAUDE.md, README).
- random_legal draws cost-free answers half the time (a combat-deck fuzz found agents stuck
  declaring unpayable attacks: 393 reversals in one game).
- Concession-during-payment tests added.

## In progress
- Full suite, quick fuzz, combat-deck fuzz (`--deck` scratch decklist) running.
- test-reviewer running; handle its findings.

## Next
- PR (delete this file first).

## Tests confirmed passing before the implementation (they test what must not happen)
juggernaut needn't attack when tapped/sick; Warmonger affects only its controller's creatures;
Prison doesn't tax its controller's attacks; malformed answer refused first; Tollkeeper's cost
not required; Unicorn attacking another player; attacking isn't required when it costs; primitive
texts and definitions (data only).
