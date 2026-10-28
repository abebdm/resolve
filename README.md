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
win, loss or draw, in 2 to 6 players. Creature and artifact spells can now be cast, paid for
with mana and resolved onto the battlefield; a cast that can't be paid is undone. Instants and
sorceries choose their targets as they are cast and check them again as they resolve (a spell
whose targets are all gone does nothing), and can deal damage, destroy, exile, gain life and
draw cards. Modal spells let their caster choose modes (the same one more than once where the
card allows it), and a cost with {X} has its value announced and paid. Spells can be countered
(a countered spell goes to its owner's graveyard), and some can't be. Flash, hexproof, shroud,
indestructible and protection work for casting, targeting and destroying (protection's damage
prevention comes with prevention effects). Permanents can make spells cost less (only their
generic mana, after any increases, never changing a spell's mana value). A spell can let its
caster cast another spell from their hand for free while it resolves (with nobody getting
priority in between, and X counted as 0). Mana comes
from lands, artifacts and creatures (which can't tap the turn they arrive), including mana of a
color you choose, mana only some spells may use, and abilities that cost mana themselves. The
cards implemented so far are the basic lands, three vanilla creatures, Sol Ring, Arcane Signet,
Selesnya Signet, Command Tower, Temple of the False God, Llanowar Elves, Avacyn's Pilgrim,
Ixalli's Lorekeeper, Emerald Medallion, Kinjalli's Caller, Swords to Plowshares, Chandra's
Ignition, Decimate, Fiery Confluence, Cryptic Command, Cancel, Rishkar's Expertise, and one
card for each keyword: Ashcoat Bear, Gladecover Scout, Humble
Budoka, Darksteel Relic, Darksteel Myr, Repentant Blacksmith and Nacatl Savage.
Tools compare a new Comprehensive Rules version or card data snapshot against
the pinned ones (`tools/rules_diff.py`, `tools/card_diff.py`), and `tools/rule.py` prints any
rule of the pinned Comprehensive Rules by number. M2 (spells and the stack) is under
way. Its plan is approved ([`docs/plans/m2.md`](docs/plans/m2.md)). Its first step,
documentation, added the rules coverage map in [`docs/roadmap.md`](docs/roadmap.md), which gives
every numbered rule and keyword a milestone on the way to handling every tournament-legal card,
and the list of hardest cards in [`docs/torture-tests.md`](docs/torture-tests.md). Its second
step made the rules the early code hard-wired (land plays, hand size, the turn sequence, who
decides) into single functions that effects can change later, and added a test that keeps the
map in step with the Comprehensive Rules; games play exactly as before. Its third step taught
the engine to read mana costs (every kind of mana symbol), and so a card's colors and mana value,
added the typed words a text-changing effect will need and an answer space for paying mana; games
still play exactly as before. Its fourth step added casting (choosing how to cast, paying mana,
undoing an illegal cast) and resolving permanent spells. Its fifth step added the mana
abilities of the target decks' mana sources and summoning sickness. Its sixth step added a
helper that pays mana automatically, for people at the terminal (`--autopay`) and for half the
random test players. Its seventh step added targets, instants and sorceries that resolve, and the
first effects. Its eighth step added modes and X, its ninth the evergreen keywords,
countering spells and Cryptic Command, and its tenth cost reductions (Emerald Medallion and
Kinjalli's Caller make spells cost less), and its eleventh casting a spell for free while
another resolves (Rishkar's Expertise), the last of M2's cards. **Next:** M2's wrap-up (M2.11),
then the user's milestone check. Details: "Current status" in [`CLAUDE.md`](CLAUDE.md).

Resolve is unofficial Fan Content permitted under the Wizards of the Coast Fan Content Policy. It
is not approved or endorsed by Wizards. Portions of the materials used are property of Wizards of
the Coast. © Wizards of the Coast LLC.
