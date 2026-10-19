# Resolve

A Magic: The Gathering rules engine in Python, aimed at running Commander (multiplayer and 1v1)
and regular 1v1 games with Comprehensive-Rules accuracy, and at making every step of the game
(the stack, triggers, choices) inspectable.

This repository is the game processor only. A desktop UI, networked play and an AI player will
be built later on top of its API.

- Architecture: [`docs/design.md`](docs/design.md)
- Milestones: [`docs/roadmap.md`](docs/roadmap.md)
- How-to recipes: [`docs/howto.md`](docs/howto.md)
- Primitives catalog: [`docs/primitives.md`](docs/primitives.md)
- Decision log: [`docs/decisions.md`](docs/decisions.md)
- Pinned rules: [`docs/rules/`](docs/rules/)
- Target decks: [`decks/`](decks/)
- Guide for Claude Code: [`CLAUDE.md`](CLAUDE.md)

**Status:** see "Current status" in [`CLAUDE.md`](CLAUDE.md) and the milestones in
[`docs/roadmap.md`](docs/roadmap.md). This README doesn't repeat it, so it can't go stale.

Resolve is unofficial Fan Content permitted under the Wizards of the Coast Fan Content Policy. It
is not approved or endorsed by Wizards. Portions of the materials used are property of Wizards of
the Coast. © Wizards of the Coast LLC.
