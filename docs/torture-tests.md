# Torture tests

Famously difficult real cards, the rules each one stresses, and the milestone that must handle it.
The engine's goal is every non-Un card with no shortcuts (design.md §1), and these are the cards
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
| Decimate | four instances of "target"; one object chosen for several of them; no cast unless every instance has a legal target; partial fizzling (601.2c, 608.2b) | M2 | | not yet |
| Cryptic Command | modes; countering; partial fizzling with one target gone; returning a permanent to its owner's hand (700.2, 701.6, 608.2b, 400.3) | M2 | | not yet |
| Fiery Confluence | the same mode chosen more than once, each with its own target (700.2d) | M2 (target deck) | | not yet |
| Lion's Eye Diamond | a mana ability with "activate only as an instant", sacrifice and discard costs, activated while casting, after the spell has left the hand (605.3a, 602.5e, 601.2g) | M4 | M2 payment and reversal | not yet |
| Fact or Fiction | an opponent separates the piles: a decision by a player other than the controller; hidden then revealed cards (608.2d, 101.4) | M4 | M2.1 `deciding_player` | not yet |
| Panglacial Wurm | casting from the library while searching it, in the middle of a resolution (701.23, 608.2g) | M4 | M2 cast permissions | not yet |
| Sylvan Library | cards drawn this turn; pay life or put cards back (608.2i, 119) | M4 | look-back history | not yet |
| Force of Will | an alternative cost of life and exiling a card from hand (118.9) | M4 | M2 cost model | not yet |
| Mana Drain | a delayed trigger that adds mana at a later main phase (603.7) | M4 | M2 mana pool | not yet |
| Doubling Season + a planeswalker | a planeswalker entering with loyalty counters, doubled by a replacement effect (614.1c, 306.5b, 122.6) | M6 | M4 counters and planeswalkers | not yet |
| Chains of Mephistopheles | replacing draws, and the order of several draw replacements (614, 616, 121.6) | M6 | | not yet |
| Laboratory Maniac + an empty library | a replacement of losing for drawing from an empty library (614, 704.5b) | M6 | M2.1 `can_lose_game` | not yet |
| Aven Mindcensor | searching only part of a zone (701.23f) | M6 | M4 searching | not yet |
| Hullbreacher / Notion Thief | replacing opponents' draws (614) | M6 | | not yet |
| Humility + Opalescence | layers 4, 6 and 7b; dependency and timestamps (613.8) | M5 | | not yet |
| Blood Moon + Urborg, Tomb of Yawgmoth | a layer 4 dependency; an ability removed by a type change (613.8) | M5 | | not yet |
| Mind Bend | changing color words and land types (612) | M5 | M2 typed words | not yet |
| Volrath's Shapeshifter | an object with the full text of another card (613, 612) | M5 | M2 definitions as data | not yet |
| Spellweaver Helix | linked abilities; casting a copy; matching names (607, 707.12) | M5 | M2 card-less spell objects | not yet |
| Painter's Servant + Grindstone | color-changing in layer 5; repeated mill (613, 701.17) | M5 | | not yet |
| Mycosynth Lattice + March of the Machines | type-changing, 0 toughness, spending mana as though any type (613, 118.14) | M5 | M2 payment check | not yet |
| Necrotic Ooze | gaining the activated abilities of cards in graveyards (613) | M5 | | not yet |
| Dark Depths + Thespian's Stage | a copy with an exception; the legend rule (707.9, 704.5j) | M5 | | not yet |
| Platinum Angel + Abyssal Persecutor | "you can't lose" and "your opponents can't win" (104.3, 101.2) | M5 | M2.1 `can_lose_game`, M2 `allowed` | not yet |
| Leyline of Sanctity | a player with hexproof; an opening-hand action (702.11c, 103.6) | M5 | M2 `player_abilities` | not yet |
| Experimental Frenzy | a permission to play from the library top and a prohibition on playing from hand (101.2, 601.3) | M5 | M2 `allowed` | not yet |
| Bolas's Citadel | playing the top card of the library, paying life rather than mana (118.9) | M5 | M2 cost model | not yet |
| Twincast on a kicked spell | a copy keeps every choice, kicked included (707.10) | M5 | M2 `CastChoices` | not yet |
| Bolt Bend / Deflecting Swat | changing a spell's target (115.7) | M5 | M2 `target_problem` | not yet |
| Kami of the Crescent Moon | changing how many cards the draw step draws (504.1) | M5 | M2.1 `draw_step_draws` | not yet |
| Exploration / Azusa, Lost but Seeking | extra land plays (305.2) | M5 | M2.1 `land_plays_allowed` | not yet |
| Stranglehold | "can't search", and skipping extra turns (101.2, 500.7) | M5 | M2.1 turn structure | not yet |
| Pithing Needle | naming any card (201.4) | M5 | M4 `ChooseCardName` | not yet |
| Gilded Drake | exchanging control, with a fallback if it can't (701.12) | M5 | | not yet |
| Time Walk / Relentless Assault | an extra turn; an extra combat phase (500.7, 500.8) | M3 | M2.1 `TurnState.segments` | not yet |
| Worldgorger Dragon | linked exile and return; a mandatory loop ending the game in a draw (607, 610.3, 104.4b) | M7 | M4 linked abilities | not yet |
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
