# Torture tests

Famously difficult real cards, the rules each one stresses, and the milestone that must handle it.
The engine's goal is every tournament-legal card with no shortcuts (design.md §1), and these are the cards
most likely to expose a design that took one.

**How this list is used** (CLAUDE.md, rule 13):

- Each milestone's plan shows how its design handles the torture tests assigned to it, and those
  assigned to later milestones that touch the systems it builds ("Touches").
- The milestone implements the cards assigned to it: real card definitions, added to the excerpt,
  each with rules tests worked out from the CR and the card's rulings.
- The test-reviewer checks that a PR's design doesn't block any torture test whose systems it
  touches.
- When a card is handled, its status names the PR or milestone. Add new cards as they come up,
  with the rules they stress.

**Status** is "not yet" until the card is implemented and tested.

| Card | Rules it stresses | Milestone | Touches | Status |
|---|---|---|---|---|
| Decimate | four instances of "target"; one object chosen for several of them; no cast unless every instance has a legal target; partial fizzling (601.2c, 608.2b) | M2 | | M2.6 ✓ (`tests/cards/test_decimate.py`) |
| Cryptic Command | modes; countering; partial fizzling with one target gone; returning a permanent to its owner's hand (700.2, 701.6, 608.2b, 400.3) | M2 | M2.6 ✓: partial fizzling (608.2b keeps the legal targets per instance; a spell resolves while any is legal); M2.7 ✓: "choose two" without repeats (`ModeChoice(2, 2)`, Test Command, cast and resolved), only the chosen modes' targets (700.2c), one object as the target of two modes | not yet |
| Fiery Confluence | the same mode chosen more than once, each with its own target (700.2d) | M2 (target deck) | M2.6 ✓: targets per instance of "target" (`CastChoices.targets`), repeated damage effects as separate `DamageDealt` events; M2.7 ✓: choices of modes as multisets (`ModesOption`), each repetition's own instances, modal resolution (`resolution.Instruction`) | M2.7 ✓ (`tests/cards/test_fiery_confluence.py`, `tests/rules/test_700_2_modes.py`) |
| Lion's Eye Diamond | a mana ability with "activate only as an instant", sacrifice and discard costs, activated while casting, after the spell has left the hand (605.3a, 602.5e, 601.2g) | M4 | M2 payment and reversal (M2.3 ✓: a kept mana ability's results stand, `Event.redo`; M2.4 ✓: nested payments and their reversal, 602.5 conditions as `ActivatedManaAbility.activate_only_if`, where "activate only as an instant" plugs in) | not yet |
| Fact or Fiction | an opponent separates the piles: a decision by a player other than the controller; hidden then revealed cards (608.2d, 101.4) | M4 | M2.1 `deciding_player` | not yet |
| Panglacial Wurm | casting from the library while searching it, in the middle of a resolution (701.23, 608.2g) | M4 | M2 cast permissions | not yet |
| Sylvan Library | cards drawn this turn; pay life or put cards back (608.2i, 119) | M4 | look-back history | not yet |
| Force of Will | an alternative cost of life and exiling a card from hand (118.9) | M4 | M2 cost model | not yet |
| Mana Drain | a delayed trigger that adds mana at a later main phase (603.7) | M4 | M2 mana pool | not yet |
| Blood Artist + a board wipe | "dies" triggers look back in time: every creature dying at once is seen, Blood Artist included (603.10a) | M4 | | not yet |
| Felidar Sovereign / Emperor Crocodile | an intervening "if" checked when it triggers and again on resolution; a state trigger that doesn't trigger again while it's on the stack (603.4, 603.8) | M4 | | not yet |
| Doubling Season + a planeswalker | a planeswalker entering with loyalty counters, doubled by a replacement effect (614.1c, 306.5b, 122.6) | M6 | M4 counters and planeswalkers | not yet |
| Chains of Mephistopheles | replacing draws, and the order of several draw replacements (614, 616, 121.6) | M6 | | not yet |
| Laboratory Maniac + an empty library | a replacement of losing for drawing from an empty library (614, 704.5b) | M6 | M2.1 `can_lose_game` | not yet |
| Aven Mindcensor | searching only part of a zone (701.23f) | M6 | M4 searching | not yet |
| Hullbreacher / Notion Thief | replacing opponents' draws (614) | M6 | | not yet |
| Humility + Opalescence | layers 4, 6 and 7b; dependency and timestamps (613.8) | M5 | | not yet |
| Tarmogoyf | a characteristic-defining ability that works in every zone, applied first in its layer (604.3, 613.3, 613.4a) | M5 | | not yet |
| Overrun + Glorious Anthem | a resolved effect changes only the objects there when it resolved; a static ability's effect has no fixed set (611.2c, 611.3a) | M5 | | not yet |
| Twisted Image on a creature with counters and an anthem | switching power and toughness after every other layer 7 change (613.4d) | M5 | | not yet |
| Blood Moon + Urborg, Tomb of Yawgmoth | a layer 4 dependency; an ability removed by a type change (613.8) | M5 | | not yet |
| Mind Bend | changing color words and land types (612) | M5 | M2 typed words (M2.2 ✓) | not yet |
| Volrath's Shapeshifter | an object with the full text of another card (613, 612) | M5 | M2 definitions as data | not yet |
| Spellweaver Helix | linked abilities; casting a copy; matching names (607, 707.12) | M5 | M2 card-less spell objects | not yet |
| Painter's Servant + Grindstone | color-changing in layer 5; repeated mill (613, 701.17) | M5 | | not yet |
| Mycosynth Lattice + March of the Machines | type-changing, 0 toughness, spending mana as though any type (613, 118.14) | M5 | M2 payment check; the auto-payer's planner (M2.5) matches mana to symbols by 107.4 alone, so M5 gives the view what "as though any type" allows and the planner reads it | not yet |
| Necrotic Ooze | gaining the activated abilities of cards in graveyards (613) | M5 | | not yet |
| Dark Depths + Thespian's Stage | a copy with an exception; the legend rule (707.9, 704.5j) | M5 | | not yet |
| Platinum Angel + Abyssal Persecutor | "you can't lose" and "your opponents can't win" (104.3, 101.2) | M5 | M2.1 `can_lose_game`, M2 `allowed` | not yet |
| Leyline of Sanctity | a player with hexproof; an opening-hand action (702.11c, 103.6) | M5 | M2 `player_abilities` | not yet |
| Experimental Frenzy | a permission to play from the library top and a prohibition on playing from hand (101.2, 601.3) | M5 | M2 `allowed` | not yet |
| Bolas's Citadel | playing the top card of the library, paying life rather than mana (118.9) | M5 | M2 cost model | not yet |
| Twincast on a kicked spell | a copy keeps every choice, kicked included (707.10) | M5 | M2 `CastChoices` | not yet |
| Bolt Bend / Deflecting Swat | changing a spell's target (115.7) | M5 | M2 `target_problem` (M2.6 ✓) | not yet |
| Kami of the Crescent Moon | changing how many cards the draw step draws (504.1) | M5 | M2.1 `draw_step_draws` | not yet |
| Exploration / Azusa, Lost but Seeking | extra land plays (305.2) | M5 | M2.1 `land_plays_allowed` | not yet |
| Stranglehold | "can't search", and skipping extra turns (101.2, 500.7) | M5 | M2.1 turn structure | not yet |
| Pithing Needle | naming any card (201.4) | M5 | M4 `ChooseCardName` | not yet |
| Gilded Drake | exchanging control, with a fallback if it can't (701.12) | M5 | | not yet |
| Time Walk / Relentless Assault | an extra turn; an extra combat phase (500.7, 500.8) | M3 | M2.1 `TurnState.segments` | not yet |
| Lure + a creature that attacks each combat if able + Ghostly Prison | obeying as many attack and block requirements as possible without breaking a restriction or being made to pay a cost (508.1c-d, 509.1c) | M3 | | not yet |
| Basilisk Collar on a creature with trample | deathtouch makes 1 damage lethal when assigning trample damage among several blockers (702.2c, 702.19b) | M3 | M2.6 damage events | not yet |
| Worldgorger Dragon | linked exile and return; a mandatory loop ending the game in a draw (607, 610.3, 104.4b) | M7 | M4 linked abilities | not yet |
| A commander that dies, is bounced or is stolen | its owner's choice to move it to the command zone, as a state-based action or a replacement (903.9a-b); commander damage counted per commander, whoever controls it (903.10a) | M7 | M2.1 `commander_damage_threshold` | not yet |
| Teferi's Protection | phasing out; a player with protection from everything; "your life total can't change" (702.26, 702.16j, 101.2) | M9 | M2 `allowed`, `player_abilities` | not yet |
| Sundial of the Infinite | ending the turn: the stack exiled, straight to cleanup (724) | M9 | M2.1 turn frame | not yet |
| Mindslaver | controlling another player's turn and what that player sees (723) | M9 | M2.1 `deciding_player`, `knows_identity` | not yet |
| Karn Liberated | restarting the game, keeping the exiled cards (727) | M9 | state construction | not yet |
| Shahrazad | a subgame inside the game (729) | M9 | nested states | not yet |
| Krosan Grip | split second against mana abilities and special actions (702.61) | M9 | M2 `allowed` | not yet |
| Wear // Tear | split-card casting; fuse; the mana value of a split card off the stack (709, 702.102) | M9 | M2 cast variants | not yet |
| Bonecrusher Giant | casting an Adventure, then casting the creature from exile (715) | M9 | M2 cast variants and destinations | not yet |
| Ixidron | face-down permanents; hidden information (708) | M9 | M2 visibility | not yet |
| Golgothian Sylex | a name "originally printed" in a set (206.3b) | M9 | | not yet |
| Gemrazer (mutate) | a merged permanent: the top card's characteristics, and every card moving when it leaves (702.140, 730) | M9 | M5 layers, 400.7 identity | not yet |
| Bruna, the Fading Light + Gisela, the Broken Blade | melding two permanents into one card pair, and what happens when it leaves (701.42, 712.4) | M9 | M5 identity | not yet |
| Benalish Hero (banding) | banding; the defending player assigning an attacker's combat damage (702.22) | M9 | M3 damage assignment | not yet |
