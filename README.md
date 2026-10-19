# Resolve

A Magic: The Gathering rules engine in Python, aimed at running Commander (multiplayer and 1v1)
and regular 1v1 games with Comprehensive-Rules accuracy, and at making every step of the game
(the stack, triggers, choices) inspectable.

This repository is the game processor only. A desktop UI, networked play and an AI player will
be built later on top of its API.

- Architecture: [`docs/design.md`](docs/design.md)
- Milestones and the rules coverage map: [`docs/roadmap.md`](docs/roadmap.md)
- Torture tests: [`docs/torture-tests.md`](docs/torture-tests.md)
- How-to recipes: [`docs/howto.md`](docs/howto.md)
- Primitives catalog: [`docs/primitives.md`](docs/primitives.md)
- Decision log: [`docs/decisions.md`](docs/decisions.md)
- Pinned rules: [`docs/rules/`](docs/rules/)
- Target decks: [`decks/`](decks/)
- Guide for Claude Code: [`CLAUDE.md`](CLAUDE.md)

**Status:** M0 (skeleton) and M1 (turn structure) are complete. Games run from choosing the
starting player through mulligans, full turns with priority, land drops, mana and cleanup, to a
win, loss or draw, in 2 to 6 players. The cards implemented so far are the basic lands and three
vanilla creatures. M2 (spells and the stack) is under way. Its plan is approved
([`docs/plans/m2.md`](docs/plans/m2.md)), and its first step, documentation, is done. That step
added the rules coverage map in [`docs/roadmap.md`](docs/roadmap.md), which gives every numbered
rule and keyword a milestone on the way to handling every non-Un card, and the list of hardest
cards in [`docs/torture-tests.md`](docs/torture-tests.md). **Next:** removing the rule defaults
the early code hard-wired (land plays, hand size, the turn sequence, who decides), then casting
spells (601.2). Details: "Current status" in [`CLAUDE.md`](CLAUDE.md).

Resolve is unofficial Fan Content permitted under the Wizards of the Coast Fan Content Policy. It
is not approved or endorsed by Wizards. Portions of the materials used are property of Wizards of
the Coast. © Wizards of the Coast LLC.
