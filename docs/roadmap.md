# Resolve — Roadmap

Milestones are worked in order. Each milestone ends with every listed item done, tests passing,
and `pytest`, `ruff` and `pyright` clean in CI. Tick items off in the same PR that completes them.

**Current milestone: M2, in progress (plan approved: `docs/plans/m2.md`; M2.0 done). M0 and M1
are complete.**

---

## Target decks

The finish line for card coverage is fully supporting these two Commander decks (in `decks/`).
Sideboard cards are out of scope.

| Deck | Commander | Colors | Cards |
|---|---|---|---|
| `gishath_dinosaurs.txt` | Gishath, Sun's Avatar | R/G/W | 100 (86 unique non-commander lines) |
| `byrke_counters.txt` | Byrke, Long Ear of the Law | G/W | 100 (81 unique non-commander lines) |

**Mechanics these decks need.** From the M0 coverage audit: `tools/coverage.py --oracle` run on
both decks against the Scryfall snapshot of 2026-10-17. Example cards are in parentheses. Sideboard
cards are not included.

- **Keyword abilities:**
  - evasion and combat: flying, reach, trample, vigilance, haste, first strike, double strike,
    lifelink
  - protection: indestructible, hexproof, shroud, ward {2} (Rampaging Aetherhood, Sovereign Okinec
    Ahau), protection from blue / from multicolored / from each color (Shifting Ceratops, Basri's
    Lieutenant, Akroma's Will)
  - +1/+1 counter keywords: evolve (Gyre Sage, Dinosaur Egg), outlast, adapt (Evolution Witness,
    Incubation Druid), level up with the leveler layout (Joraga Treespeaker), riot granted to other
    creatures (Rhythm of the Wild)
  - others: equip, saddle and "attacks while saddled" (Bulwark Ox, Ornery Tumblewagg), offspring,
    an optional additional cost that creates a token copy (Tender Wildguide), myriad (Scion of
    Calamity), overload (Fangs of Kalonia), cycling and basic landcycling, ascend and the city's
    blessing (Arch of Orazca, Wayward Swordtooth), hideaway 4 (Mosswort Bridge)
  - Choose a Background (Lae'zel) only matters while the card is a commander. It is in the 99
    here, so it has no effect in game.
- **Keyword actions:**
  - fight (Apex Altisaur, Savage Stomp, Wayta); "deals damage equal to its power" bites
    (Hunter's Edge, Itzquinth, Chandra's Ignition)
  - proliferate (Karn's Bastion, Unnatural Restoration), double counters (see below), regenerate
    (Asceticism), scry, discover X (Pantlaza, Dinosaur Egg), transform (Dowsing Dagger // Lost Vale)
- **Ability words:** enrage (three Dinosaurs), landfall (Undergrowth Champion), lieutenant (Loyal
  Guardian, which needs "if you control your commander").
- **+1/+1 counters, heavily:**
  - replacement effects that change how many counters are placed, combined in the 616 order the
    affected player chooses: "twice that many" (Branching Evolution); "that many plus one" (Hardened
    Scales, Conclave Mentor, Kami of Whispered Hopes); "plus one of each kind" on creatures,
    planeswalkers *and players* (Lae'zel)
  - entering with counters, including X (Kalonian Hydra, Mikaeus, Wildwood Scourge), and Arwen's
    "enters with additional counters equal to Arwen's toughness" (614.1c)
  - doubling counters (Byrke, Kalonian Hydra, Biogenic Upgrade, Fangs of Kalonia, Ornery
    Tumblewagg); Aetheric Amplifier doubles every kind of counter on a permanent or on a player
  - distributing counters among targets at cast time (Biogenic Upgrade, 601.2d)
  - triggers on counters being put: "one or more" (Evolution Witness, Wildwood Scourge) and "the
    first time this turn" (Botanical Brawler, which needs per-turn history)
  - removing counters as a cost (Mikaeus; Quilled Greatwurm removes six from among creatures you
    control)
  - other counter kinds: level (Joraga), finality (From the Rubble), energy {E} on players,
    gained and paid (Rampaging Aetherhood)
- **Static and continuous effects:**
  - abilities granted to "each creature you control with a +1/+1 counter on it" (Abzan Battle
    Priest, Abzan Falconer, Ainok Bond-Kin, Duskshell Crawler, Pridemalkin) or with any counter
    (Bulwark Ox)
  - granted mana abilities: Rishkar (creatures with counters), Enduring Vitality (all creatures),
    Joraga level 5+ (Elves)
  - anthems and lords: Thundering Spineback, Regisaur Alpha (haste), Drover of the Mighty
    (conditional +2/+2), Return of the Wildspeaker
  - type-changing effects (layer 4): Xenagos (devotion to two colors), and Enduring Vitality
    returning as a non-creature enchantment
  - copy effects (layer 1): Sunfrill Imitator becomes a copy "except its name is … and it has this
    ability"; offspring and myriad create token copies
  - "power greater than its base power" (Kutzil, Sovereign Okinec Ahau)
  - Kutzil: "your opponents can't cast spells during your turn"
- **Replacement and prevention effects:**
  - entering tapped: always, conditionally (check lands, battle lands, Overgrown Farmland), with a
    reveal from hand (Fortified Village, Furycalm Snarl, Game Trail), and for opposing creatures
    (Kinjalli's Sunwing)
  - "as this enters, choose a color" or "choose a creature type" (Thriving lands, From the Rubble,
    Progenitor's Icon, Secluded Courtyard, Unclaimed Territory)
  - prevention: Undergrowth Champion (prevent, then remove a counter); Temple Altisaur (prevent all
    but 1)
  - finality counters (die → exile instead); Mana Reflection (mana doubling)
- **Triggered abilities:**
  - intervening-if (Scute Mob, Basri's Lieutenant, Loyal Guardian); "if you cast it" and "if you
    cast it from your hand" (Zacama, Wakening Sun's Avatar)
  - looking back in time (603.10): dies triggers that read counters, power or toughness (Basri's
    Lieutenant, Conclave Mentor, Dinosaur Egg)
  - reflexive triggers (Itzquinth: "When you do"); "Do this only once each turn" (Pantlaza)
  - Wayta: a creature being dealt damage makes triggers trigger an additional time
  - Wrathful Raptors: a damage-driven trigger that deals "that much damage"
  - spell and ability triggers: any player casting a spell (Managorger Hydra), casting a creature
    spell (Lifecrafter's Bestiary), an opponent activating a non-mana ability (Runic Armasaur)
  - "whenever you attack" (Ghalta and Mavren) and combat-damage triggers, including batched "one
    or more creatures … deal combat damage" (Quartzwood Crasher, Kutzil, Curious Altisaur,
    Gishath, Scion of Calamity)
- **Combat:**
  - creating tokens tapped and attacking (Ghalta and Mavren; myriad attacking other opponents in
    multiplayer)
  - restrictions: "can't attack or block unless" (Topiary Stomper, Wayward Swordtooth); "can't be
    blocked" (Rogue's Passage); "creatures with power less than this creature's power can't block
    creatures you control" (Champion of Lambholt)
- **Casting and costs:**
  - cost reduction: by color (Emerald Medallion), by type (Kinjalli's Caller, Otepec Huntmaster,
    Marauding Raptor), by a count (Hamza; Ghalta's "X less" for total power), when the spell
    targets a Dinosaur (Savage Stomp), and for an activated ability that targets two of your
    creatures (Wayta)
  - additional costs: "reveal a Dinosaur card or pay {1}" (Thunderherd Migration), offspring
  - casting without paying the mana cost from the library top (Descendants' Path), from cards
    exiled from *each player's* library (Etali), from hand (Rishkar's Expertise), via discover,
    and playing a hideaway card
  - casting from the graveyard with an extra cost (Quilled Greatwurm); flash granted to the next
    spell of a chosen type (Progenitor's Icon)
  - "can't be countered" (Shifting Ceratops, Rhythm of the Wild); modes: choose the same mode more
    than once (Fiery Confluence), "choose both if you control a commander" (Akroma's Will)
  - X spells (Mikaeus, Wildwood Scourge, Kessig Wolf Run)
- **Mana:**
  - "any color in your commander's color identity" (Command Tower, Arcane Signet, Path of Ancestry,
    which also triggers when its mana is spent on a creature sharing a type with your commander)
  - "any color that a land an opponent controls could produce" (Exotic Orchard) and "any type that
    a land you control could produce" (Incubation Druid)
  - variable amounts: Gyre Sage ({G} per counter), Kami of Whispered Hopes (X of one color equal
    to its power), Lost Vale (three of any one color), Incubation Druid (three with a counter)
  - restricted mana: Ixalli's Lorekeeper, Secluded Courtyard, Unclaimed Territory
  - mana abilities with activation conditions (Temple of the False God); a triggered mana ability
    (Regal Behemoth while you're the monarch, 605.1b); mana doubling (Mana Reflection)
- **Library and lands:**
  - land search: basics (Rampant Growth, Cultivate, Evolving Wilds, Path to Exile for the exiled
    creature's controller), by land type (Farseek), "two basics that share a land type" (Myriad
    Landscape), and as an optional enrage trigger (Ranging Raptors)
  - additional land plays (Explore, Wayward Swordtooth); returning a land to hand (Selesnya
    Sanctuary); no maximum hand size (Reliquary Tower)
  - revealing cards and putting the rest on the bottom in a random order (Gishath, discover,
    hideaway)
- **Designations:** the monarch (Regal Behemoth); the city's blessing (ascend).
- **Tokens and other players:** tokens created for another player (Generous Gift, Dowsing Dagger's
  Plants for an opponent); "each opponent" damage (Chandra's Ignition, Fiery Confluence).

---

## M0 — Skeleton

- [x] Tooling: `pyproject.toml` finalized, `uv`, `ruff`, `pyright`, `pytest`; GitHub Actions CI
  workflow.
- [x] `tools/fetch_scryfall.py`: download the Oracle-cards and rulings bulk data into `data/`, and
  record the snapshot date in `docs/rules/README.md`.
- [x] Card data loader (`resolve.data`) and decklist parser (the `decks/` format).
- [x] Card registry, plus `tools/coverage.py`: report implemented and missing cards per deck.
- [x] **Coverage audit:** run the coverage tool on both target decks, then update the "Mechanics"
  list above from the actual Oracle text.
- [x] Core state types:
  - `GameState`, `Player`, `GameObject`, zones
  - `ObjectId` and `CardId`, timestamps
  - `GameConfig`
- [x] Task loop with `Done` / `Push` / `NeedDecision`. The public API: `new_game`,
  `pending_decision`, `view_for`, `submit`.
- [x] Decision request and answer types (enumerated and constrained), plus answer validation.
- [x] Event type skeleton and event log, with CR citations.
- [x] `NotImplementedRule` exception, and `tools/gaps.py` to list the gaps.
- [x] Scenario builder (`tests/scenario.py`).
- [x] Agents: a random agent and a scripted test agent.
- [x] `tools/play_cli.py`: a minimal text renderer and CLI agent.
- [x] Fuzz harness, checking deepcopy/pickle round-trips and replay determinism. Until M1 every
  game stops at `NotImplementedRule("103.5: ...")`, which the harness treats as the end of an M0
  game; any other exception is a failure.

## M1 — Turn structure (1v1 first, multiplayer-shaped data)

- [x] Opening hands and mulligans (103.5), including the free first mulligan in multiplayer
  (103.5c), and the redaction of drawn cards in other players' views and logs (design.md §9).
- [x] All phases and steps (500–514), with priority passed in each step where it applies.
- [x] Untap, draw (including the first-turn draw skip in two-player games), and cleanup
  (discarding to hand size, removing damage, ending "until end of turn" effects; no "until end
  of turn" effect can exist yet).
- [x] Playing lands (305) as a special action; basic lands' mana abilities; mana pools emptying
  between steps.
- [x] Basic state-based actions: 0 or less life, drawing from an empty library, lethal damage and
  0 toughness.
- [x] Concession at any time (104.3a), through its own API entry point, `concede` (design.md §3),
  with leaving the game for what can exist in M1 (800.4a/h/j/k) and replays of answers and
  concessions. Random agents finish 2- to 4-player land-only games with random concessions.
- [x] Cards: basic lands and a few vanilla creatures.
- [x] The scenario builder sets the turn, phase, step and priority holder; the fuzz harness's
  allowed gaps move past 103.5.

## M2 — Spells and the stack

The approved plan is `docs/plans/m2.md` (steps M2.0 to M2.11).

- [x] The plan, the rules coverage map, the torture tests and rules 12 and 13 (M2.0,
  documentation).
- [x] The coverage-map consistency test, and the rule defaults M0/M1 hard-coded turned into
  single functions (rule 12, M2.1).
- [x] Mana costs and symbols (107.4), characteristics' mana cost, colors and mana value (202), typed
  words (612), and the `ChooseCounts` answer space (M2.2).
- [ ] The full casting process (601.2):
  - announce, with **cast variants and permissions** chosen before the card moves, so every
    layout that changes how a spell is cast fits (split cards and Rooms 709.3, double-faced
    cards 712.11, adventures 715.3, omens 720.3, prototype 718.3, face-down 708.4, casting from
    other zones);
  - choose modes, X, and targets;
  - total the cost;
  - activate mana abilities;
  - pay costs.
- [x] Timing rules for sorceries, instants and permanents (M2.3); flash (M2.8).
- [x] One permission and prohibition system for every legality check, where "can't" beats "can"
  (101.2): playing lands, casting, targeting, destroying and countering (M2.1 to M2.8); later
  milestones add their actions.
- [x] Reversing an illegal action (733) by checkpoint and restore (M2.3), with the dependency
  check between kept mana abilities (M2.4).
- [x] Evergreen keywords whose rules live here: flash (702.8), hexproof (702.11), shroud (702.18),
  indestructible (702.12), and the targeting part of protection (702.16) (M2.8). Design targeting
  so these restrictions fit naturally.
- [x] Evergreen keyword actions whose rules live here: cast (701.5), counter (701.6), destroy
  (701.8), exile (701.13); and "can't be countered" (113.6g) (M2.3 to M2.8).
- [x] Create the keyword table: widened into the rules coverage map at the end of this file
  (M2.0).
- [x] Resolution (608), including checking targets again on resolution (608.2b) and partial
  fizzling; last known information (608.2h) (M2.6); modal spells' modes (M2.7).
- [x] Mana payment details and the general cost model: generic, colored, {C}, X and restricted
  mana (106.6), with slots for hybrid, Phyrexian, snow and non-mana costs; cost increases and
  reductions in 601.2f's order (M2.3 to M2.9).
- [x] Casting without paying the mana cost, during resolution (608.2g, 118.9; Rishkar's
  Expertise) (M2.10).
- [x] Mana abilities beyond basic lands (605): "any color in your commander's color identity",
  activation conditions, mana costs on mana abilities, creatures' mana abilities and summoning
  sickness (302.6), restricted mana (Ixalli's Lorekeeper) (M2.4).
- [x] The agent-side auto-payer (design.md §6: convenience outside the engine), and the public
  payments and abilities in the views it plans from (M2.5).
- [x] The first primitives: damage, destroy, exile, draw, life gain (M2.6), counter target spell
  (M2.8).
- [x] Cards: 14 from the target decks, 8 keyword example cards and the torture tests Decimate
  and Cryptic Command (`docs/plans/m2.md` §7): the last, Rishkar's Expertise, in M2.10.

Moved out of M2 by the plan: dividing (601.2d), reductions from a count or from targets
(Ghalta, Hamza, Savage Stomp), overload, casting from the graveyard, exile and the library top,
triggered mana abilities and "when that mana is spent" → M4; offspring, casting prohibitions
(Kutzil) → M5; "as though it had flash" (Progenitor's Icon), "any color a land could produce"
(106.7) → M6; Regal Behemoth → M7; hybrid and Phyrexian payment → M9.

## M3 — Combat

- [ ] Beginning of combat, declare attackers, declare blockers, combat damage, end of combat
  (506–511).
- [ ] Attack and block requirements and restrictions (508.1d, 509.1c), including "can't attack or
  block unless" (Topiary Stomper), "can't be blocked" (Rogue's Passage) and power-based blocking
  restrictions (Champion of Lambholt).
- [ ] Creatures put onto the battlefield tapped and attacking (508.4, Ghalta and Mavren).
- [ ] First strike and double strike damage steps; trample; deathtouch; lifelink; flying and reach;
  vigilance; menace. Deathtouch and lifelink apply to noncombat damage too (M2's damage table).
- [ ] Defender (702.3); the retired evergreen evasion keywords intimidate (702.13), landwalk
  (702.14) and fear (702.36).
- [ ] Haste (702.10), including its 302.6 part.
- [ ] Summoning sickness for attacking (302.6), sharing M2.4's "controlled since the turn
  began" test. `defaults.can_tap_for_cost` covers only a creature's own {T}/{Q} abilities
  (302.6, 602.5a): the tap costs of convoke (702.51), improvise (702.126), crew (702.122) and
  "tap an untapped creature you control" ignore summoning sickness and must not use it.
  Consider renaming it here (for example a shared `summoning_sick(state, obj)` predicate for
  {T} costs and attacking; docs/decisions.md, 2026-10-21 "Deferred from M2.4").
- [ ] Protection's blocking part (702.16f).
- [ ] Multiplayer attacks: choosing which player or planeswalker each creature attacks, and
  leaving room for attacking battles (310). Attack and block declarations use a constrained
  answer space (`ChooseAssignment`, design.md §6).
- [ ] Extra turns, phases and steps (500.7–500.10), on M2.1's `TurnState.segments` and
  `next_turn` (Time Walk, Relentless Assault).
- [ ] Ending turns and phases (724): the design must allow it; implemented in M9 (exotic).

## M4 — Activated and triggered abilities

- [ ] Activated abilities (602), including costs like tapping and sacrificing; equip.
- [ ] Mana-ability activation goes through `legality.allowed` (101.2), like other activations:
  an `Action` with the rules' permissions (602.2, 605.3a) and the prohibitions effects add
  ("can't activate"; split second 702.61, M9, which spares mana abilities, 702.61b). Deferred
  from M2 (the M2 plan listed the action, but no M2 step built it; until then
  `ActivatedManaAbility.can_activate` decides, with 602.5 conditions in `activate_only_if`;
  docs/decisions.md, 2026-10-21 "Deferred from M2.4").
- [ ] Non-mana costs (118): sacrifice, discard, exile, life, counters, tapping other permanents,
  with reversal (733) by M2's checkpoint. Tapping an untapped creature for a cost ignores
  summoning sickness: not through `can_tap_for_cost` (302.6 covers only a creature's own
  {T}/{Q} abilities).
- [ ] Triggered abilities (603):
  - APNAP ordering
  - intervening-if conditions (603.4)
  - looking back in time (603.10, 608.2i), with a history derived from the event log
  - delayed triggers
  - "may" choices
- [ ] Trigger variants: reflexive triggers (603.12), triggering additional times (603.2d, Wayta),
  "do this only once each turn" (Pantlaza), batched "one or more" triggers, and spell-cast and
  ability-activation triggers.
- [ ] Triggered mana abilities (605.1b) and "when that mana is spent" delayed triggers (603.7a).
- [ ] Damage-driven triggers (enrage), fight (701.14).
- [ ] Counters (122) on permanents and on players (poison 704.5c, energy): putting and removing
  them, counters as costs, doubling (701.10e) and proliferate (701.34).
- [ ] Keyword abilities built on activated and triggered abilities: saddle (702.171) and "attacks
  while saddled", cycling and landcycling (702.29), outlast (702.107), level up (702.87), adapt
  (701.46), evolve (702.100), ward (702.21).
- [ ] Equipment and auras: attaching (701.3), enchant (702.5), and state-based actions for illegal
  attachments (704.5m-n); protection's enchant and equip parts (702.16c-d).
- [ ] Tokens (111, 701.7), including the predefined tokens (111.10) and investigate (701.16).
- [ ] Planeswalkers (306, 209), loyalty abilities (606), 704.5i and damage to planeswalkers
  (120.3c); emblems (114).
- [ ] The legend rule (704.5j).
- [ ] Double-faced cards (712): transforming (701.27) and casting modal double-faced cards' back
  faces through M2's cast variants.
- [ ] Library search and manipulation: search, including failing to find (701.23), reveal
  (701.20), scry (701.22), surveil (701.25), mill (701.17), with knowledge of library positions.
- [ ] Linked abilities (607); choosing a card name (201.4) with a constrained answer space.
- [ ] Casting from zones other than the hand: the graveyard (Quilled Greatwurm), exile and the top
  of the library (Etali, Descendants' Path, discover 701.57, hideaway 702.75).
- [ ] Dividing at cast time (601.2d, Biogenic Upgrade); cost reductions that depend on a count or
  on the spell's targets (Ghalta, Hamza, Savage Stomp; for abilities, Wayta); overload (702.96);
  "reveal a card or pay {1}" (Thunderherd Migration).

## M5 — Continuous effects and layers

- [ ] The layer system (613): layers 1–7 with the 7a–7d sublayers, timestamps (613.7), dependencies
  (613.8).
- [ ] Static abilities; counters as power/toughness modifiers; effects that grant abilities.
- [ ] Characteristic-defining abilities, Gods and devotion, type-changing effects.
- [ ] Copy effects (707) in layer 1, including copies with exceptions (707.9, Sunfrill Imitator)
  and token copies (offspring, myriad); copies of spells and abilities (707.10, 704.5e) and
  changing their targets (115.7).
- [ ] Text-changing effects (612) over the definitions' typed words.
- [ ] Durations (611.2): "until end of turn", "this turn", "until your next turn", "for as long
  as", ended by events.
- [ ] Permissions and prohibitions from static abilities (101.2), including casting prohibitions
  (601.3, Kutzil) and players' abilities (hexproof, shroud, protection for players).
- [ ] Modifiers of the rule defaults (rule 12): land plays (Explore, Wayward Swordtooth), maximum
  hand size (Reliquary Tower), cards drawn, untapping, mana emptying, losing the game
  (Platinum Angel), opening-hand actions (103.6). The M2.1 seam tests are replaced with tests
  using real effects.
- [ ] Leveler cards (711); exchanges (701.12); goad (701.15).
- [ ] Interaction tests for classic layer puzzles (the M5 rows of `docs/torture-tests.md`).

## M6 — Replacement and prevention effects

- [ ] Replacement effects (614), including entering-the-battlefield modifications (614.1c–d, 614.12)
  and choices stored on the permanent as it enters.
- [ ] Prevention effects (615), including Undergrowth Champion (prevent, then remove a counter),
  Temple Altisaur (prevent all but 1) and protection's damage prevention (702.16e).
- [ ] Entering-the-battlefield choices and modifications from other permanents: riot (702.136),
  "creatures your opponents control enter tapped" (Kinjalli's Sunwing).
- [ ] Multiple replacement effects with the affected player choosing order (616), including
  counter-placement stacking (for example doubling plus "one additional"), on players as well as
  permanents (Lae'zel).
- [ ] Regeneration (701.19); mana-doubling replacements.
- [ ] Skipping steps, phases and turns (500.11, 614.10); replacing draws (121.6).
- [ ] Replacements of where a spell goes as it leaves the stack (flashback-style exile).
- [ ] "Any color a land could produce" (106.7, Exotic Orchard); "as though it had flash"
  (601.3b, Progenitor's Icon); restricted mana tied to a chosen type (Secluded Courtyard,
  Unclaimed Territory).

## M7 — Multiplayer and Commander

- [ ] Games with any number of players: APNAP order everywhere; turn order; attacking multiple
  players.
- [ ] Leaving the game (800.4) and all its consequences (M1 did 800.4a/h/j/k for cards; still to
  do: control-changing effects, tokens and stack objects, 800.4b-g, 800.4i, 800.4m).
- [ ] Myriad (702.116): token copies attacking each other opponent.
- [ ] The command zone, casting commanders, and commander tax.
- [ ] Commander damage (903.10a) and the zone-change rules (903.9a/b).
- [ ] Color identity and deck validation; partner variants (702.124).
- [ ] The scenario builder refuses commanders `validate_deck` would refuse (903.3, 903.5,
  702.124a), and the tests that use the fixtures' non-legendary commanders are updated.
- [ ] Designations: the monarch (Regal Behemoth), the city's blessing; the general system for
  player and game designations (design.md §4).
- [ ] Cards outside the game (400.11, 903.11).
- [ ] Leave room for what players bring to a game besides their deck (implemented in M9): Attraction
  decks (717.2), sticker sheets (123.2), conspiracy cards (315.2) and playing for ante (407.2).
- [ ] Loop guard (104.4b); decide how much of shortcuts (732) to implement.

## M8 — Card coverage

- [ ] Implement the remaining cards of `gishath_dinosaurs.txt`, tracked by `tools/coverage.py`.
- [ ] Implement the remaining cards of `byrke_counters.txt`.
- [ ] Both decks pass validation and play complete random-agent games with no crashes or invariant
  violations, plus a ruling-derived test for every card.

## M9 — Rules coverage

- [ ] Implement every row of the rules coverage map below whose tier is **set mechanic** or
  **exotic** and that isn't done yet, in any section (keywords, card layouts, designations,
  special rules), each with rules tests and a fixture or excerpt card.
- [ ] Every row of the map is either implemented or out of scope with a reason the user approved.
- [ ] The torture tests assigned to M9 in `docs/torture-tests.md`.

## What's built

What each completed step added, with the modules to look in. Update this list in the PR that
completes a step (CLAUDE.md, "Documentation requirements").

- **Done (M0):**
  - Data and tooling: `resolve.data` (card data loader and decklist parser), the card registry
    and deck coverage (`resolve.cards.registry`, `resolve.cards.coverage`),
    `tools/fetch_scryfall.py`, `tools/coverage.py`, `tools/gaps.py` (lists every
    `NotImplementedRule`), CI, and the coverage audit (the Scryfall snapshot of 2026-10-17 is
    pinned).
  - The engine core: state types (`resolve.state`: `GameState`, `Player`, `GameObject`, zones,
    IDs, `GameConfig`, the engine's own PRNG, invariant and purity checks), the task loop and
    public API (`resolve.tasks`, `resolve.engine`: `new_game`, `pending_decision`, `view_for`,
    `submit`, `build_deck`), decision kinds, answer spaces and validation (`resolve.decisions`),
    events, the event pipeline (with stubbed replacement and trigger stages) and the event log
    (`resolve.events`), `NotImplementedRule` (`resolve.errors`), and zone moves (`move_object`,
    400.7).
  - Agents and test tooling: `resolve.agents` (the `Agent` protocol, the `play` driver,
    `RandomAgent`, `ScriptedAgent` with replays from the log, and the text renderer and
    `TextAgent` in `resolve.agents.text`); the scenario builder `tests/scenario.py`;
    `tools/play_cli.py`; and the fuzz harness `tools/fuzz.py` with `tests/fuzz/`.
- **Done (M1.1):** drawing (`resolve.engine.drawing.DrawCards`, `CardDrawn`, 121), opening hands
  and mulligans (`resolve.engine.mulligans.OpeningHands`, 103.5 and 103.5c), events logged as
  applied, and redacted log entries for other players (design.md §7, §9).
- **Done (M1.2):** turns, phases and steps (`resolve.state.turn`, `resolve.engine.turns`:
  `TakeTurn`, `RunStep`, 500-514, the 103.8a draw skip, 508.8), priority
  (`resolve.engine.priority.PriorityRound`, 117; casting is offered and raises
  `NotImplementedRule("601.2")` when chosen), the state-based actions 704.5a and 704.5b and the end
  of two-player games (`resolve.engine.sba`, 104.2a, 104.4a), discarding to hand size in cleanup
  (514.1) and 514.3a, type-line parsing (`resolve.data.types`, 205), the characteristics entry point
  without layers (`resolve.effects.characteristics`), turn info in views, and the scenario builder's
  `at(...)`. Two-player games with any decks play to a decking loss when every player passes.
- **Done (M1.3):** the five basic lands (`resolve.cards.definitions.basic_lands`), playing
  lands (305), the first primitives (`TapSelfCost`, `AddMana`, `ActivatedManaAbility`; 305.6
  intrinsic mana abilities added by `characteristics`), tapped status, the untap step (502.3),
  mana pools emptying as steps end (500.5), and mana abilities at priority (605.3a). Random
  agents finish two-player land-only games.
- **Done (M1.4):** vanilla creatures (`resolve.cards.definitions.vanilla_creatures`), power and
  toughness in `characteristics`, damage marked on permanents, the state-based actions 704.5f
  and 704.5g (with the owner ordering cards that reach a graveyard together, 404.3), and damage
  removal in cleanup (514.2).
- **Done (M1.5):** concession (`resolve.engine.concede`, 104.3a), leaving the game
  (`LeaveGame`, 800.4a, 800.4h, 800.4j, 800.4k), multiplayer endings (104.2a, 104.4a), re-entrant
  asking tasks, and replays of answers and concessions (`resolve.agents.replay`). The fuzz
  harness concedes at random and random agents finish 2- to 4-player land-only games.
- **Done (tooling, after M1):** `tools/fuzz.py` plays basic-land decks by default (from the
  committed excerpt `tools/excerpts/basic_lands.json`, written by `tools/card_excerpt.py`; no
  snapshot needed), with a quick default run (about 20 seconds) and a `--thorough` preset for
  the user's milestone verification (`docs/verification.md`), games in parallel (`--jobs`), and
  a summary of answers, turns, endings, lands and mana.
- **Done (tooling, CR and card-data updates):** `tools/rules_diff.py` compares two CR text files
  (changed, renumbered, removed and added rules, with the code and tests that cite them),
  `tools/card_diff.py` compares two card data snapshots for implemented and deck cards, and a
  test checks every CR number cited in `src/`, `tools/` and `tests/` against the pinned rules.
  The recipe is in `docs/howto.md` ("Update to a new Comprehensive Rules version").
  `tools/rule.py` prints a rule, a section outline or a glossary entry from the pinned CR, with
  the rules it cites (`docs/howto.md`, "Look up a rule").
- **Done (M2.0, documentation):** the approved M2 plan (`docs/plans/m2.md`), the rules coverage
  map and the per-milestone checklists in `docs/roadmap.md`, the torture tests
  (`docs/torture-tests.md`), rules 12 and 13 below, and the provisional design-ahead sections of
  `docs/design.md`.
- **Done (M2.1, rule defaults):** `tests/tooling/test_coverage_map.py` (the map agrees with the
  pinned CR); `resolve.rules.defaults`, one function for each rule default of plan §5.1, which
  the engine calls through the module (`defaults.maximum_hand_size(...)`) so a replacement is
  obeyed everywhere; `resolve.rules.legality` (`allowed`, `PlayLand`, permissions and
  prohibitions: 101.2, 305.1, 305.2b); `TurnState.segments` (the segments still to begin),
  `GameState.extra_turns` and `turn_direction`; `TakeTurn` as the turn frame (724); `DecisionRequest.for_player`
  (723.5) and `concede(by=)` (723.6); `ManaPoolEmptied.kept`. A normal game is unchanged: the
  quick fuzz summary is identical to M1's.
- **Done (M2.2, mana costs and characteristics):** `resolve.data.mana_cost` (`ManaSymbol` of every
  kind of 107.4, `ManaCost`, `parse_mana_cost`, mana value 202.3 and colors 202.2), parsed into
  `CardFace.cost` (an unreadable cost is refused by `DeckCard` and reported by the coverage tool
  like an unreadable type line); `Characteristics.mana_cost`, `colors` and `mana_value`;
  `characteristics` reads the normal front part of omen and preparation cards (720.4, 722.4);
  `resolve.cards.primitives.words` (`ColorWord`, `LandTypeWord`, `SubtypeWord`, `NameRef`,
  `rewrite_words`); `ChooseCounts` (601.2h) with random-agent, text-agent and fuzz-probe support;
  `Color` in `resolve.data.types`; `tools/excerpts/cards.json` (the three vanilla creatures).
  No behavior change: the quick fuzz summary is identical to M2.1's.
- **Done (M2.3, casting and resolving permanent spells):** `resolve.state.spell` (cast variants,
  `CastPermission` with `FROM_HAND` and `COMMANDER`, `CastChoices`), `GameObject.spell` and
  `cast_record` (400.7d); `CastSpellOption(object, variant, permission)`, `ManaOption`,
  `ManaActivationOption`, and the decision kinds `ACTIVATE_MANA_ABILITIES` and
  `REVERSE_MANA_ABILITIES`; `variant_characteristics` (601.3e; a spell on the stack has its
  variant's); the rule defaults `cast_permissions`, `cast_options` (per permission and layout
  variant), `may_cast_now(..., variant, permission)`, `has_sorcery_timing(..., ignoring=)` and
  `resolved_spell_destination` (608.2n); `legality.CastAction`; `resolve.engine.casting.CastSpell`
  (601.2a-i; other variants and commanders raise their gaps), `resolve.engine.payment.PayCosts`
  (601.2g-h, embedded in the casting task), `resolve.state.checkpoint` (733.1 reversal; players
  who leave meanwhile stay gone), `resolve.engine.resolution.ResolveTopOfStack` (608.1, 608.3a;
  instants and sorceries are the 608.2c gap until M2.6); the priority fixes 117.3b, 117.3c and
  733.2; events `SpellProposed`, `SpellCast`, `ManaSpent`, `ActionReversed`,
  `PermanentSpellResolved`; `ObjectView.spell`; Sol Ring
  (`resolve.cards.definitions.mana_rocks`, in the excerpt). The fuzz harness plays the
  `spells` and `creatures` deck recipes with commanders in every other Commander game, allows
  the 508.1 and 903.8 gaps, and reports casts, resolutions, reversals, casts per card and gaps.
- **Done (M2.4, mana abilities beyond basic lands, and summoning sickness):** 302.6 in
  `defaults.can_tap_for_cost`, with `GameObject.entered_turn` (set as a permanent is created)
  and `Player.last_turn_began` (set by `TurnBegan`); primitives `ManaPaymentCost`,
  `AddManaOfAnyColor`, `ControlsAtLeast` (`resolve.cards.primitives.conditions`),
  `SpendOnlyOnSubtype` (`resolve.cards.primitives.restrictions`) and
  `ActivatedManaAbility.activate_only_if`; `ManaRestriction`, `Mana.restriction`, `ForSpell` and
  `ForAbility` (`resolve.state.mana`); `resolve.rules.commander.commander_color_identity`
  (903.4); `ActivateManaAbility` in stages, with a nested `PayCosts` and checkpoint for a mana
  cost, the `CHOOSE_COLOR` decision (`ColorOption`) and its own reversal; `PayCosts(payer, cost,
  purpose, excluding)` (605.3c, 106.6); `resolve.engine.reversal` (activations in the order they
  began, nested ones included; 733.1's dependency check; `reverse_to`); `ManaSpent.redo`;
  `ActionReversed.source`. Cards: Arcane Signet, Selesnya Signet (`mana_rocks`), Llanowar Elves,
  Avacyn's Pilgrim, Ixalli's Lorekeeper (`mana_creatures`), Command Tower, Temple of the False
  God (`nonbasic_lands`); the fixture decks use the real Llanowar Elves. The fuzz recipes hold
  them all; the summary counts reversed mana ability activations apart from reversed casts.
- **Done (M2.5, the agent-side auto-payer):** `resolve.agents.autopay` (`AutoPayAgent`,
  `plan_payment`, `choose_payment`, `choose_color`): answers 601.2g-h, 106.1a and 733.1 payment
  decisions from the view alone, for `request.for_player` (723.5a); the views' public payment
  information: `PlayerView.payments` (`PaymentView`, from `Task.payment_under_way`, with the
  restrictions the engine says allow spending, 106.6) and `ObjectView.abilities` (`AbilityView`,
  `ManaOutput`) in `resolve.engine.view`; `play_cli.py --autopay` (`seat_agents`); the renderer's
  `Paying:` line. The fuzz harness's odd seats are `AutoPayAgent(RandomAgent)`; `PayableCasts`
  judges each cast at its first payment decision, and the summary's `Reversed casts:` line
  compares the seats on payable casts; the view oracle checks abilities and payments. Tests:
  `tests/agents/test_autopay.py`, `tests/agents/test_autopay_brute_force.py` (the planner
  against a search through the engine; `pytest --thorough`, `tests/conftest.py`),
  `tests/engine/test_view_abilities_and_payments.py`.
- **Done (M2.6, targets, last known information, values and the first effects):** spell
  abilities (`resolve.cards.primitives.spells`: `SpellAbility`, `Mode`, `ModeChoice`;
  `CardDefinition.spell`, read as `Characteristics.spell_ability`); targets
  (`resolve.cards.primitives.targets`: `TargetSpec`, `ObjectFilter`, `PlayerFilter`,
  `SpellFilter`, `ANY_TARGET`, `target`), references and values (`refs`: `ThisObject`,
  `TargetRef`, `You`, `ControllerOf`, `EachCreature`, `EachOpponent`, `Phrasing`; `values`:
  `Fixed`, `PowerOf`), effects (`Effect` in `base`; `DealDamage`, `Destroy`, `Exile`,
  `GainLife`, `DrawCards` in `effects`); `resolve.effects.evaluation` (`Context`, `Timing`,
  `information`, `objects`, `players`, `evaluate`; 608.2h); last known information
  (`resolve.state.last_known.LastKnown`, `GameState.last_known`, recorded by `move_object`,
  cleared at the empty-stack priority); `resolve.rules.targeting` (`target_problem` on
  `legality.allowed(TargetAction)`, with `Targeter`; 115.5 a prohibition; `legal_targets`,
  `can_choose_targets`), `legality.DestroyAction`; `CastChoices.targets` (`TargetObject`,
  `TargetPlayer`); `CastSpell`'s 601.2c (`CHOOSE_TARGETS`, `BecameTargets`); `cast_options`
  leaves out spells without legal targets; instant and sorcery resolution
  (`resolution.ResolveSpell`; 608.2b `SpellDidNotResolve`, 608.2n/608.2m `SpellResolved`);
  events `DamageDealt` (`resolve.events.damage`: the 120.3 results), `LifeGained`
  (`resolve.events.life`), `ObjectExiled`; the text renderer's targets; the fuzz summary's
  "didn't resolve" and `Damage:` line. Cards: Swords to Plowshares, Chandra's Ignition, Decimate
  (`resolve.cards.definitions.removal`, in the excerpt); fixtures Test Shock and Test Ponder (real
  definitions now), Test Shatter, Test Wall, Test Totem, Test Artifact Land Creature;
  `Scenario.targets`, `casting_support.choose_targets`.
- **Done (M2.7, modes and X):** `CastSpell`'s stages `MODES` (601.2b, 700.2: `CHOOSE_MODES`, a
  `ChooseOne` of `ModesOption`; `ModesChosen`), `X` (601.2b, 107.3a: `CHOOSE_X`, a
  `ChooseNumber(0, None)`; `XAnnounced`) and `TARGETS` (each chosen mode's instances, 700.2c);
  `CastChoices.modes` and `x`; `ModeChoice.combinations`, `SpellAbility.chosen`, `instances` and
  the modal text (`resolve.cards.primitives.spells`); `targeting.legal_modes`, `mode_choices`
  (700.2a), `can_choose_targets` for modal spells; the total cost with X (`ManaCost.has_x`,
  `with_x`; 601.2f), the mana value with X on the stack (202.3e); the value `X`
  (`resolve.cards.primitives.values`); modal resolution (`resolution.Instruction`: each mode's
  effects with its own targets, 608.2b over all of them, 608.2c); the text agent's
  `ModesOption`. Cards: Fiery Confluence (`resolve.cards.definitions.removal`, in the excerpt);
  fixtures Test Blaze ({X}) and Test Command (choose two); `Scenario.modes`, `Scenario.x`,
  `casting_support.choose_modes`, `choose_x`.
- **Done (M2.8, evergreen keywords, counter, Cryptic Command):** the keyword abilities `Flash`,
  `Hexproof(quality)`, `Shroud`, `Indestructible`, `Protection(quality)`,
  `protection_from_each_color`, `has_keyword`, `keywords` (`resolve.cards.keywords.evergreen`)
  and the qualities `ColorQuality`, `MulticoloredQuality`, `MonocoloredQuality`,
  `CardTypeQuality`, `SubtypeQuality`, `Everything` (`resolve.cards.keywords.qualities`); the
  prohibitions in `resolve.rules.legality` (targeting: shroud, hexproof, "hexproof from",
  protection, from a permanent's characteristics or `defaults.player_abilities`; destroying:
  indestructible; countering: `CounterAction` and `CantBeCountered`,
  `resolve.cards.primitives.statics`); flash in `defaults.may_cast_now`; 704.5g through
  `allowed(DestroyAction)`; protection's damage prevention a gap (`NotImplementedRule("702.16e")`
  in `DamageDealt.apply`); effects `CounterSpell`, `ReturnToHand`, `TapAll`, and
  `EachCreature.controlled_by`; events `SpellCountered` (to the owner's graveyard, never
  `resolved_spell_destination`) and `ReturnedToHand` (`resolve.events.permanents`); the fuzz
  summary's "countered" count and `FUZZ_EXCLUSIONS` (Repentant Blacksmith, 702.16e). Cards: the
  keyword example cards Ashcoat Bear, Gladecover Scout, Humble Budoka, Darksteel Relic,
  Darksteel Myr, Repentant Blacksmith, Nacatl Savage and Cancel
  (`resolve.cards.definitions.keyword_examples`) and Cryptic Command
  (`resolve.cards.definitions.counterspells`), in the excerpt; fixtures Test Redproof Bear, Test
  Multiproof Knight, Test Prismatic Knight, Test Untouchable, Test Twin Flash, Test
  Indestructible Wisp, Test Stubborn Spell, Test Gold Shock, Test Adventurer // Test Quest;
  `Scenario.stack(variant=)`, `casting_support.target_choices`.
- **Done (M2.9, cost reductions):** the 601.2f modifier pipeline: `resolve.rules.costs`
  (`spell_cost_modifiers`: the `SpellCostModifier` abilities of the permanents on the
  battlefield, 113.6, in battlefield order; `spell_total_cost`: increases, then reductions, then
  effects on the total), called by `CastSpell`'s `TOTAL` stage, which locks the total in
  (601.2f, 601.8); `resolve.cards.primitives.cost_modifiers` (`CostModifier`, `ModifierStep`,
  `ReduceGeneric`, 118.7a; `SpellCostModifier`, `SpellCostReduction`); `ManaCost.generic` and
  `with_generic`; `Quality.adjective`. Cards: Emerald Medallion and Kinjalli's Caller
  (`resolve.cards.definitions.cost_reducers`, in the excerpt and the fuzz recipes); fixtures
  Test Thorn (a test-only increase, `SpellCostIncrease`/`IncreaseGeneric` in
  `tests/game_fixtures.py`) and Test Growth ({X}{G}).
- **Done (M2.10, casting during resolution without paying the mana cost):** `CastPermission`'s
  `alternative_cost` (`AlternativeCost.WITHOUT_PAYING_MANA_COST`, 118.9) and
  `mana_value_at_most`; `CastGrant` and `GameState.cast_grants` (a permission an effect gives
  for now), read by `defaults.cast_permissions`; `CastTiming.DURING_RESOLUTION` in
  `defaults.may_cast_now` (608.2g); the mana value limit in `legality.allowed(CastAction)`
  (601.3e); `resolve.engine.casting.CastDuringResolution` (the `CAST_DURING_RESOLUTION`
  decision, `DECLINE`; a reversed attempt is asked again, 733.2); `CastSpell` announcing X as 0
  (107.3b), skipping the hybrid announcement and starting the total from {0} when the mana cost
  isn't paid (118.9, 118.9d, 118.6a); primitives `GreatestPower` (values), `MayCastFromHand`
  (effects) and `Mode.paragraphs`; the text agent names the alternative cost. Card: Rishkar's
  Expertise (`resolve.cards.definitions.card_draw`, in the excerpt and both fuzz recipes);
  fixtures Test Insight (no mana cost) and Test Two-Tone in the scenario database;
  `casting_support.cast_during_resolution`, `decline`.
---

## Rules coverage map

Every numbered section of the pinned CR, every keyword ability (702) and every keyword action
(701): the milestone where its rules live, and its tier. Created during M2 planning; each
milestone's plan checks and corrects it (CLAUDE.md, "Planning a milestone"). From M2.1 a test
checks that the map lists every heading of the pinned rules exactly once.

**Milestone** is where a row's rules live: the latest system it needs. "✓" marks parts already
done, and several milestones are listed when parts of a row land in different ones.

**Tiers and when each is implemented:**

- **E, evergreen/common** (flying, trample, flash, ward, scry, mill, and so on): in the milestone
  where its rules live.
- **S, set mechanic** (cascade, convoke, kicker, cycling, and so on): in M9, unless a target deck
  needs it, in which case it's done in the milestone where its rules live.
- **X, exotic** (banding, phasing, mutate, companion, one-card mechanics, and so on): the same as
  set mechanics.
- **Out of scope**: not implemented, for the reason given; the user approved each one.

**D** in the notes marks a row a target deck needs. Whatever the tier, the systems built in
earlier milestones must leave room for every row in this map.

### Numbered sections

| CR | Name | Milestone | Tier | Notes |
|---|---|---|---|---|
| 100 | General | M0 ✓ | E |  |
| 101 | The Magic Golden Rules | M1 ✓ (101.4); 101.2 system M2 ✓ (skeleton M2.1 ✓, casting M2.3 ✓, targeting and destroying M2.6 ✓, keyword prohibitions and countering M2.8 ✓); 101.1, 101.3 with each effect | E | `allowed` (design.md §17.2); land plays are its first action |
| 102 | Players | M1 ✓ | E | teams (102.3-102.4): out of scope with the team variants |
| 103 | Starting the Game | M1 ✓; 103.6 M5; 103.2b M7 | E | `opening_hand_actions`, `mulligan_options`, `starting_life`, `starting_hand_size`: default functions in place (M2.1 ✓) |
| 104 | Ending the Game | M1 ✓; 104.3c-d M4, M7; 104.4b M7; alternative wins and losses M5 | E | `can_lose_game`: default function in place (M2.1 ✓) |
| 105 | Colors | M2 ✓ (colors of objects, 105.1-105.2: M2.2; choosing a color, 105.4: M2.4); 105.3 M5 (color-changing effects); 105.5 with its first card | E |  |
| 106 | Mana | M1 ✓, M2 ✓ (spending mana, 106.4a: M2.3 ✓; restrictions 106.6, any color 106.1a, undefined mana 106.5: M2.4 ✓); 106.7 M6 | E | `Mana.restriction`, `ManaRestriction` |
| 107 | Numbers and Symbols | M2 ✓ (107.4 symbols parsed: M2.2 ✓; 107.3a X announced: M2.7 ✓; 107.3b M2.10 ✓); 107.3c, 107.3f with their first card; 107.4e-f, 107.4h M9; 107.14 M4; 107.15, 107.17 M9 | E | hybrid and Phyrexian: M2 builds the announcement stage |
| 108 | Cards | M0 ✓ | E |  |
| 109 | Objects | M1 ✓; 109.3 with each layout in its own row (M4, M5, M9; omen and preparation read as their normal part: M2.2 ✓; 720.4, 722.4); 109.4c with emblems (M4) | E |  |
| 110 | Permanents | M1 ✓; statuses with their mechanics | E |  |
| 111 | Tokens | M4 | E | D (Regisaur Alpha, Generous Gift) |
| 112 | Spells | M2 ✓ (spells on the stack with their record: M2.3 ✓); copies M5 | E |  |
| 113 | Abilities | M2 ✓ (spell abilities 113.3a: M2.6 ✓; 113.6 M2.8 ✓: permanents' abilities only on the battlefield, 113.6g can't be countered); M4; M5 | E | `CantBeCountered` |
| 114 | Emblems | M4 | E | with planeswalkers |
| 115 | Targets | M2 ✓ (115.1-115.6, 115.10: M2.6 ✓; shroud, hexproof and protection M2.8 ✓); 115.7 M5 | E | `target_problem` (M2.6 ✓) |
| 116 | Special Actions | M1 ✓ (116.2a); the others with their mechanics | E | 116.2i out of scope (Planechase); 116.2j is for conspiracy cards (315) |
| 117 | Timing and Priority | M1 ✓, M2 ✓ (117.1a casting, 117.3b-c, 117.4 with the stack: M2.3 ✓; flash M2.8 ✓) | E |  |
| 118 | Costs | M2 ✓ (mana: paying generic, colored and {C} mana M2.3 ✓; mana costs of mana abilities, restricted mana M2.4 ✓; X M2.7 ✓; generic reductions 118.7, 118.7a: M2.9 ✓; 118.9 "without paying its mana cost", 118.9a-d, 118.6a: M2.10 ✓; other alternative costs with their keywords); 118.7b-g with their first cards (colored, colorless, hybrid, Phyrexian, snow reductions); M4 (other costs, 118.12) | E | `resolve.rules.costs` |
| 119 | Life | M2 ✓ (gaining life, 119.3, 119.10: M2.6 ✓); paying life M4 | E |  |
| 120 | Damage | M2 ✓ (noncombat: 120.1-120.2, 120.3a, 120.3e, 120.4b, 120.8: M2.6 ✓), M3 (combat), M4 (120.3b-d, 120.3g-h) | E | the 120.3 table is `DamageDealt.apply` |
| 121 | Drawing a Card | M1 ✓; 121.6 M6 | E |  |
| 122 | Counters | M4 | E | D |
| 123 | Stickers | M5 (stickers change names, abilities, power and toughness: 123.6-123.8); M7 (sticker sheets chosen before the game, 123.2) | S | Unfinity: 47 cards that use stickers and 48 sticker sheets are Commander-legal |
| 200 | General | — | — | nothing to implement |
| 201 | Name | M1 ✓; 201.4 M4 | E |  |
| 202 | Mana Cost and Color | M2 ✓ (M2.2 ✓: 202.1-202.3; 202.3e on the stack: M2.7 ✓) | E |  |
| 203 | Illustration | out of scope | — | no game rules |
| 204 | Color Indicator | M2 ✓ (M2.2 ✓) | E | colors come from the card data |
| 205 | Type Line | M1 ✓; type changes M5 | E |  |
| 206 | Expansion Symbol | M9 | X | 206.3: City in a Bottle, Golgothian Sylex and Apocalypse Chime refer to names "originally printed" in a set; 206.3a-c list those names, so no extra card data is needed |
| 207 | Text Box | M1 ✓ | E | ability words have no rules meaning (207.2c) |
| 208 | Power/Toughness | M1 ✓; 208.2 M5 | E |  |
| 209 | Loyalty | M4 | E | planeswalkers |
| 210 | Defense | M4 | S | battles |
| 211 | Hand Modifier | out of scope | — | Vanguard |
| 212 | Life Modifier | out of scope | — | Vanguard |
| 213 | Information Below the Text Box | out of scope | — | no game rules |
| 300 | General | M1 ✓ | E |  |
| 301 | Artifacts | M2 ✓ (casting artifact spells: M2.3 ✓); Equipment M4; Vehicles M5; Fortifications M9 | E |  |
| 302 | Creatures | M1 ✓, M2 ✓ (302.6 for {T} costs: M2.4 ✓), M3 (302.6 for attacking) | E | `can_tap_for_cost`, `GameObject.entered_turn`, `Player.last_turn_began` |
| 303 | Enchantments | M2 ✓ (casting enchantment spells, 303.1-303.2: M2.3); Auras M4 | E | Sagas, Classes, Cases and Rooms have their own rows |
| 304 | Instants | M2 ✓ (304.1 timing: M2.3, flash M2.8; 304.2 resolving: M2.6); 304.4 with the first effect that puts a card onto the battlefield (M4); 304.5 with activated abilities (M4) | E |  |
| 305 | Lands | M1 ✓; modifiers M5 | E | `land_plays_allowed`, `land_play_options`: default functions in place (M2.1 ✓) |
| 306 | Planeswalkers | M4 (attacking them M3) | E |  |
| 307 | Sorceries | M2 ✓ (307.1 timing: M2.3; 307.2 resolving: M2.6); 307.4 with the first effect that puts a card onto the battlefield (M4); 307.5 with activated abilities (M4) | E |  |
| 308 | Kindreds | M1 ✓ | E |  |
| 309 | Dungeons | M7 | S | with venture (701.49) |
| 310 | Battles | M4 (attacking them M3) | S | M3 leaves room for attacking battles |
| 311 | Planes | out of scope | — | Planechase |
| 312 | Phenomena | out of scope | — | Planechase |
| 313 | Vanguards | out of scope | — | Vanguard |
| 314 | Schemes | out of scope | — | Archenemy |
| 315 | Conspiracies | M7 | X | used only in limited play (315.1); 25 conspiracy cards are banned rather than never legal, so they are in scope |
| 400 | General | M0 ✓ (400.3 returning to the owner's hand: M2.8 ✓); 400.7 exceptions with their mechanics; 400.11 M7 | E |  |
| 401 | Library | M1 ✓ | E |  |
| 402 | Hand | M1 ✓; modifiers M5 | E | D (Reliquary Tower); `maximum_hand_size`: default function in place (M2.1 ✓) |
| 403 | Battlefield | M1 ✓ | E |  |
| 404 | Graveyard | M1 ✓ | E |  |
| 405 | Stack | M2 ✓ (405.1-405.2, 405.5: M2.3 ✓); 405.3 M4 | E |  |
| 406 | Exile | M2 ✓ (exiling, 406.2-406.3: M2.6); face-down exile and the rest M4 | E |  |
| 407 | Ante | M7 | X | the 9 ante cards are banned in every format, not never legal; they need an option to play for ante (407.2, 407.3) |
| 408 | Command | M7; emblems M4 | E |  |
| 500 | General | M1 ✓; 500.7-500.10 M3; 500.11 M6 | E | `turn_structure`, `is_skipped`, `next_turn`, `mana_that_empties`, `TurnState.segments`: default functions in place (M2.1 ✓) |
| 501 | Beginning Phase | M1 ✓ | E |  |
| 502 | Untap Step | M1 ✓; 502.1 M9; 502.2 M7 | E | `permanents_that_untap`: default function in place (M2.1 ✓) |
| 503 | Upkeep Step | M1 ✓ | E |  |
| 504 | Draw Step | M1 ✓ | E | `draw_step_draws`: default function in place (M2.1 ✓) |
| 505 | Main Phase | M1 ✓; 505.3-505.5 M9 | E |  |
| 506 | Combat Phase | M3 | E |  |
| 507 | Beginning of Combat Step | M3 | E |  |
| 508 | Declare Attackers Step | M3 | E |  |
| 509 | Declare Blockers Step | M3 | E |  |
| 510 | Combat Damage Step | M3 | E |  |
| 511 | End of Combat Step | M3 | E |  |
| 512 | Ending Phase | M1 ✓ | E |  |
| 513 | End Step | M1 ✓ | E |  |
| 514 | Cleanup Step | M1 ✓; 514.2 effects ending M5 | E |  |
| 600 | General | — | — | nothing to implement |
| 601 | Casting Spells | M2 ✓ (M2.3 ✓: 601.2a, 601.2e-i, 601.3, 601.3e variants and permissions, 601.6; 601.2c M2.6 ✓; 601.2b modes and X: M2.7 ✓, hybrid and Phyrexian announcements M9; 601.2f increases, reductions and lock-in, 601.8: M2.9 ✓; casting during resolution with a permission's alternative cost: M2.10 ✓; 601.2d M4; 601.3b M6) | E | gaps per variant: 709.3, 712.11a-b, 715.3, 718.3, 720.3, 722.3, 708.4, 702.102; 903.8 |
| 602 | Activating Activated Abilities | M4 (for mana abilities, 602.2b mana costs and 602.5 "activate only if": M2.4 ✓) | E |  |
| 603 | Handling Triggered Abilities | M4 | E |  |
| 604 | Handling Static Abilities | M5 (M2 ✓: keyword statics M2.8 ✓, cost-reduction statics M2.9 ✓) | E |  |
| 605 | Mana Abilities | M1 ✓, M2 ✓ (605.3a while casting: M2.3 ✓; 605.2, 605.3a while paying a mana ability's cost, 605.3c: M2.4 ✓); 605.1b M4 | E |  |
| 606 | Loyalty Abilities | M4 | E |  |
| 607 | Linked Abilities | M4 | E | D (hideaway) |
| 608 | Resolving Spells and Abilities | M2 ✓ (608.1, 608.3a: M2.3 ✓; 608.2a-c, 608.2h, 608.2m-n: M2.6 ✓; 608.2c for modes: M2.7 ✓; 608.2g M2.10 ✓); 608.2d-f, 608.2i, 608.2k M4 | E | `resolved_spell_destination` (608.2n) in place (M2.3 ✓), called from M2.6 ✓ |
| 609 | Effects | M2 ✓ (one-shot effects of spells: M2.6 ✓) | E |  |
| 610 | One-Shot Effects | M2 ✓ (one-shot effects, 610.1: M2.6); 610.2-610.3 M4; 610.4 with phasing (M9); 610.5 M5 | E |  |
| 611 | Continuous Effects | M5 | E |  |
| 612 | Text-Changing Effects | M5 (typed words and `rewrite_words`: M2.2 ✓) | X |  |
| 613 | Interaction of Continuous Effects | M5 | E |  |
| 614 | Replacement Effects | M6 | E |  |
| 615 | Prevention Effects | M6 | E |  |
| 616 | Interaction of Replacement and/or Prevention Effects | M6 | E |  |
| 700 | General | M2 ✓ (700.2, 700.2a, 700.2c-d, 700.2f: M2.7 ✓; 700.2b M4 with triggered abilities; 700.2e, 700.2g-i with their cards); the others with their mechanics | E |  |
| 703 | Turn-Based Actions | M1 ✓, M3 | E |  |
| 704 | State-Based Actions | M1 ✓ (704.5a, b, f, g; 704.5g and indestructible: M2.8 ✓); 704.5c, d, i, j, m, n, p, q, r, z M4; 704.5e M5; 704.5h M3; 704.5k, s, t, u, v-y M9 | E | 704.5j is the legend rule; 704.5u is space sculptor |
| 705 | Flipping a Coin | M2 | S |  |
| 706 | Rolling a Die | M2 | S |  |
| 707 | Copying Objects | M5 | E | D (Sunfrill Imitator, offspring, myriad) |
| 708 | Face-Down Spells and Permanents | M5 (casting room M2 ✓: `FaceDown` variant, M2.3 ✓) | S | morph, manifest, disguise, cloak |
| 709 | Split Cards | M5 (casting room M2 ✓: halves offered, 709.3 gap, M2.3 ✓) | S | split cards and Rooms |
| 710 | Flip Cards | M5 | X |  |
| 711 | Leveler Cards | M5 (level up itself, 702.87, M4) | S | D (Joraga Treespeaker): level symbols are static abilities (711.2) |
| 712 | Double-Faced Cards | M4 (MDFC casting through M2's cast variants ✓: back face offered, 712.11b gap, M2.3 ✓) | E | D (Dowsing Dagger) |
| 713 | Substitute Cards | out of scope | — | substitute cards stand in for physical double-faced cards; the engine tracks faces itself |
| 714 | Saga Cards | M4 | S |  |
| 715 | Adventurer Cards | M4 (casting room M2 ✓: `Alternative(ADVENTURE)`, M2.3 ✓) | S |  |
| 716 | Class Cards | M5 | S |  |
| 717 | Attraction Cards | M7 (an Attraction deck in the command zone, 717.2; the junkyard, 717.6) | S | Unfinity: 22 Attractions without the acorn stamp are Commander-legal |
| 718 | Prototype Cards | M5 (casting room M2 ✓: `Alternative(PROTOTYPE)`, M2.3 ✓) | S |  |
| 719 | Case Cards | M4 | S |  |
| 720 | Omen Cards | M2 | S | casting and resolution; 720.4 normal characteristics M2.2 ✓ (plan corrected: not a 109.3 gap); 720.3 variant gap M2.3 ✓ |
| 721 | Station Cards | M4 | S |  |
| 722 | Preparation Cards | M5 | S | 722.4 normal characteristics M2.2 ✓ (plan corrected); 722.3 variant gap M2.3 ✓ |
| 723 | Controlling Another Player | M9 (seam M2.1 ✓) | X | `deciding_player`, `DecisionRequest.for_player`, `knows_identity`, `concede(by=)`: seams in place; the auto-payer pays with `for_player`'s resources (723.5a, M2.5 ✓) |
| 724 | Ending Turns and Phases | M3 (turn frame M2.1 ✓) | X | the turn frame is `TakeTurn` on the task stack (`turn_frame_index`) |
| 725 | The Monarch | M7 | S | D (Regal Behemoth) |
| 726 | The Initiative | M7 | S |  |
| 727 | Restarting the Game | M7 | X |  |
| 728 | Rad Counters | M4 | S |  |
| 729 | Subgames | M7 | X | Shahrazad |
| 730 | Merging with Permanents | M5 | X | mutate |
| 731 | Day and Night | M7 | S |  |
| 732 | Taking Shortcuts | M7 | E | how much of it is worth implementing: design.md §16 |
| 733 | Handling Illegal Actions | M2 ✓ (M2.3 ✓; reversing a mana ability activation and the kept-abilities dependency check of 733.1: M2.4 ✓; 733.2 for a cast during resolution, asked again: M2.10 ✓); keeping the results of sacrifice and discard (733.1) M4 | E | checkpoint and restore (`resolve.state.checkpoint`), `resolve.engine.reversal` |
| 800 | General | M1 ✓ (800.4a, h, j, k); the rest M7 | E |  |
| 801 | Limited Range of Influence Option | out of scope | — | Commander doesn't use it (903.2) |
| 802 | Attack Multiple Players Option | M3, M7 | E | Commander's multiplayer default |
| 803 | Attack Left and Attack Right Options | out of scope | — | a multiplayer option Commander doesn't use |
| 804 | Deploy Creatures Option | out of scope | — | a team option |
| 805 | Shared Team Turns Option | out of scope | — | a team option |
| 806 | Free-for-All Variant | M7 | E | Commander's multiplayer variant |
| 807 | Grand Melee Variant | out of scope | — | a variant needing range of influence and several turns at once |
| 808 | Team vs. Team Variant | out of scope | — | a team variant |
| 809 | Emperor Variant | out of scope | — | a team variant |
| 810 | Two-Headed Giant Variant | out of scope | — | a team variant |
| 811 | Alternating Teams Variant | out of scope | — | a team variant |
| 900 | General | — | — | nothing to implement |
| 901 | Planechase | out of scope | — | a casual variant |
| 902 | Vanguard | out of scope | — | a casual variant |
| 903 | Commander | M7 (903.4, 903.4a, 903.4f for mana: M2.4 ✓; 903.8 cast gap M2.3 ✓); 903.12 Brawl and 903.13 Commander Draft out of scope | E | the project's format; `commander_color_identity` |
| 904 | Archenemy | out of scope | — | a casual variant |
| 905 | Conspiracy Draft | out of scope | — | the draft itself (905.1-905.2) isn't a game the engine plays; the game's conspiracy rules are 315 and 702.106, which are in scope |

### Keyword abilities (702)

| CR | Name | Milestone | Tier | Notes |
|---|---|---|---|---|
| 702.2 | Deathtouch | M3 | E | noncombat damage too (the M2 damage table leaves room) |
| 702.3 | Defender | M3 | E | D |
| 702.4 | Double Strike | M3 | E | D |
| 702.5 | Enchant | M4 | E | Aura spells' targets use M2's targeting |
| 702.6 | Equip | M4 | E | D |
| 702.7 | First Strike | M3 | E | D |
| 702.8 | Flash | M2 ✓ (M2.8 ✓) | E | `Flash`, read by `may_cast_now` |
| 702.9 | Flying | M3 | E | D |
| 702.10 | Haste | M3 | E | D; the 302.6 hook is `defaults.can_tap_for_cost` (M2.4 ✓); the attack half shares its test |
| 702.11 | Hexproof | M2 ✓ (M2.8); a player with "hexproof from" (702.11d) M5, with its first card | E | D; including "hexproof from"; a player's from `player_abilities` |
| 702.12 | Indestructible | M2 ✓ (M2.8 ✓) | E | D |
| 702.13 | Intimidate | M3 | E | retired evergreen |
| 702.14 | Landwalk | M3 | E | retired evergreen |
| 702.15 | Lifelink | M3 | E | D; noncombat damage too |
| 702.16 | Protection | M2 ✓ (targeting: M2.8 ✓); M3 (blocking); M4 (enchant, equip); M6 (damage: `NotImplementedRule("702.16e")` until then) | E | D; a player as the quality (702.16k) with its first card |
| 702.17 | Reach | M3 | E | D |
| 702.18 | Shroud | M2 ✓ (M2.8 ✓) | E | D |
| 702.19 | Trample | M3 | E | D |
| 702.20 | Vigilance | M3 | E | D |
| 702.21 | Ward | M4 | E | D; M2 logs the targets chosen |
| 702.22 | Banding | M3 | X |  |
| 702.23 | Rampage | M5 | S |  |
| 702.24 | Cumulative Upkeep | M4 | S |  |
| 702.25 | Flanking | M5 | S |  |
| 702.26 | Phasing | M5 | X | affects every system |
| 702.27 | Buyback | M2 | S |  |
| 702.28 | Shadow | M3 | S |  |
| 702.29 | Cycling | M4 | S | D |
| 702.30 | Echo | M4 | S |  |
| 702.31 | Horsemanship | M3 | X |  |
| 702.32 | Fading | M6 | S |  |
| 702.33 | Kicker | M2 | S |  |
| 702.34 | Flashback | M6 | S |  |
| 702.35 | Madness | M6 | S |  |
| 702.36 | Fear | M3 | E | retired evergreen |
| 702.37 | Morph | M5 | S |  |
| 702.38 | Amplify | M6 | X |  |
| 702.39 | Provoke | M4 | X |  |
| 702.40 | Storm | M5 | S |  |
| 702.41 | Affinity | M2 | S |  |
| 702.42 | Entwine | M2 | S |  |
| 702.43 | Modular | M6 | S |  |
| 702.44 | Sunburst | M6 | S |  |
| 702.45 | Bushido | M5 | S |  |
| 702.46 | Soulshift | M4 | S |  |
| 702.47 | Splice | M5 | S | adds text to a spell |
| 702.48 | Offering | M4 | X |  |
| 702.49 | Ninjutsu | M4 | S |  |
| 702.50 | Epic | M5 | X |  |
| 702.51 | Convoke | M4 | S | a payment alternative; tapping a creature for convoke ignores summoning sickness: must not use `can_tap_for_cost` (302.6 covers only a creature's own {T}/{Q} abilities) |
| 702.52 | Dredge | M6 | S |  |
| 702.53 | Transmute | M4 | S |  |
| 702.54 | Bloodthirst | M6 | S |  |
| 702.55 | Haunt | M4 | X |  |
| 702.56 | Replicate | M5 | S |  |
| 702.57 | Forecast | M4 | X |  |
| 702.58 | Graft | M6 | S |  |
| 702.59 | Recover | M4 | X |  |
| 702.60 | Ripple | M4 | X |  |
| 702.61 | Split Second | M2 | S | a prohibition while on the stack |
| 702.62 | Suspend | M4 | S |  |
| 702.63 | Vanishing | M6 | S |  |
| 702.64 | Absorb | M6 | X |  |
| 702.65 | Aura Swap | M4 | X |  |
| 702.66 | Delve | M4 | S | a payment alternative |
| 702.67 | Fortify | M4 | X |  |
| 702.68 | Frenzy | M5 | X |  |
| 702.69 | Gravestorm | M5 | X |  |
| 702.70 | Poisonous | M4 | X |  |
| 702.71 | Transfigure | M4 | X |  |
| 702.72 | Champion | M4 | S |  |
| 702.73 | Changeling | M5 | S |  |
| 702.74 | Evoke | M4 | S |  |
| 702.75 | Hideaway | M4 | S | D (Mosswort Bridge; the card itself in M6) |
| 702.76 | Prowl | M3 | S |  |
| 702.77 | Reinforce | M4 | S |  |
| 702.78 | Conspire | M5 | S |  |
| 702.79 | Persist | M4 | S |  |
| 702.80 | Wither | M4 | S |  |
| 702.81 | Retrace | M4 | S |  |
| 702.82 | Devour | M6 | S |  |
| 702.83 | Exalted | M5 | S |  |
| 702.84 | Unearth | M6 | S |  |
| 702.85 | Cascade | M4 | S |  |
| 702.86 | Annihilator | M4 | S |  |
| 702.87 | Level Up | M4 | S | D (Joraga Treespeaker; leveler cards, 711, M5) |
| 702.88 | Rebound | M6 | S |  |
| 702.89 | Umbra Armor | M6 | S |  |
| 702.90 | Infect | M4 | S |  |
| 702.91 | Battle Cry | M5 | S |  |
| 702.92 | Living Weapon | M4 | S |  |
| 702.93 | Undying | M4 | S |  |
| 702.94 | Miracle | M4 | S |  |
| 702.95 | Soulbond | M5 | S |  |
| 702.96 | Overload | M4 | S | D (Fangs of Kalonia) |
| 702.97 | Scavenge | M4 | S |  |
| 702.98 | Unleash | M6 | S |  |
| 702.99 | Cipher | M4 | S |  |
| 702.100 | Evolve | M4 | S | D |
| 702.101 | Extort | M4 | S | needs hybrid payment |
| 702.102 | Fuse | M5 | S | split cards |
| 702.103 | Bestow | M5 | S |  |
| 702.104 | Tribute | M6 | S |  |
| 702.105 | Dethrone | M4 | S |  |
| 702.106 | Hidden Agenda | M7 | X | conspiracy cards (banned; limited play only, 315.1) |
| 702.107 | Outlast | M4 | S | D |
| 702.108 | Prowess | M5 | E | very common since 2015 |
| 702.109 | Dash | M5 | S |  |
| 702.110 | Exploit | M4 | S |  |
| 702.111 | Menace | M3 | E |  |
| 702.112 | Renown | M4 | S |  |
| 702.113 | Awaken | M5 | S |  |
| 702.114 | Devoid | M5 | S |  |
| 702.115 | Ingest | M4 | S |  |
| 702.116 | Myriad | M7 | S | D |
| 702.117 | Surge | M2 | S | needs a record of spells cast this turn |
| 702.118 | Skulk | M3 | S |  |
| 702.119 | Emerge | M4 | S |  |
| 702.120 | Escalate | M2 | S |  |
| 702.121 | Melee | M5 | S |  |
| 702.122 | Crew | M5 | S | tapping creatures to crew ignores summoning sickness: must not use `can_tap_for_cost` (302.6 covers only a creature's own {T}/{Q} abilities) |
| 702.123 | Fabricate | M4 | S |  |
| 702.124 | Partner | M7 | E | Commander deck construction; D (Lae'zel's Choose a Background, no in-game effect) |
| 702.125 | Undaunted | M2 | S |  |
| 702.126 | Improvise | M4 | S | a payment alternative; must not use `can_tap_for_cost` (302.6 is about creatures' own {T}/{Q} abilities) |
| 702.127 | Aftermath | M5 | S | split cards |
| 702.128 | Embalm | M5 | S |  |
| 702.129 | Eternalize | M5 | S |  |
| 702.130 | Afflict | M4 | S |  |
| 702.131 | Ascend | M7 | S | D |
| 702.132 | Assist | M4 | X | another player pays |
| 702.133 | Jump-Start | M6 | S |  |
| 702.134 | Mentor | M4 | S |  |
| 702.135 | Afterlife | M4 | S |  |
| 702.136 | Riot | M6 | S | D |
| 702.137 | Spectacle | M2 | S | needs a record of life lost this turn |
| 702.138 | Escape | M4 | S |  |
| 702.139 | Companion | M7 | X | outside the game |
| 702.140 | Mutate | M5 | X |  |
| 702.141 | Encore | M7 | S |  |
| 702.142 | Boast | M4 | S |  |
| 702.143 | Foretell | M4 | S |  |
| 702.144 | Demonstrate | M5 | S |  |
| 702.145 | Daybound and Nightbound | M7 | S |  |
| 702.146 | Disturb | M6 | S |  |
| 702.147 | Decayed | M4 | S |  |
| 702.148 | Cleave | M5 | S |  |
| 702.149 | Training | M4 | S |  |
| 702.150 | Compleated | M6 | S | needs Phyrexian payment |
| 702.151 | Reconfigure | M5 | S |  |
| 702.152 | Blitz | M5 | S |  |
| 702.153 | Casualty | M5 | S |  |
| 702.154 | Enlist | M5 | S |  |
| 702.155 | Read Ahead | M4 | S | Sagas |
| 702.156 | Ravenous | M6 | S |  |
| 702.157 | Squad | M5 | S |  |
| 702.158 | Space Sculptor | M7 | X | one card, Space Beleren (Unfinity, Commander-legal) |
| 702.159 | Visit | M7 | S | the 22 Commander-legal Attractions |
| 702.160 | Prototype | M5 | S |  |
| 702.161 | Living Metal | M5 | S |  |
| 702.162 | More Than Meets the Eye | M5 | X |  |
| 702.163 | For Mirrodin! | M4 | S |  |
| 702.164 | Toxic | M4 | S |  |
| 702.165 | Backup | M5 | S |  |
| 702.166 | Bargain | M4 | S |  |
| 702.167 | Craft | M4 | S |  |
| 702.168 | Disguise | M5 | S |  |
| 702.169 | Solved | M4 | S | Cases |
| 702.170 | Plot | M4 | S |  |
| 702.171 | Saddle | M4 | S | D |
| 702.172 | Spree | M2 | S |  |
| 702.173 | Freerunning | M3 | S |  |
| 702.174 | Gift | M4 | S |  |
| 702.175 | Offspring | M5 | S | D |
| 702.176 | Impending | M6 | S |  |
| 702.177 | Exhaust | M4 | S |  |
| 702.178 | Max Speed | M7 | S | with speed (702.179) |
| 702.179 | Start Your Engines! | M7 | S | player speed |
| 702.180 | Harmonize | M6 | S |  |
| 702.181 | Mobilize | M4 | S |  |
| 702.182 | Job Select | M4 | S |  |
| 702.183 | Tiered | M2 | S |  |
| 702.184 | Station | M4 | S |  |
| 702.185 | Warp | M4 | S |  |
| 702.186 | ∞ (Infinity) | M5 | S | grants an ability while harnessed (701.64) |
| 702.187 | Mayhem | M4 | S | needs a record of cards discarded this turn |
| 702.188 | Web-slinging | M4 | S |  |
| 702.189 | Firebending | M4 | S | mana that doesn't empty (the M2.1 default) |
| 702.190 | Sneak | M3 | S |  |
| 702.191 | Increment | M4 | S |  |
| 702.192 | Paradigm | M5 | S | copies |
| 702.193 | Power-up | M4 | S |  |
| 702.194 | Teamwork | M4 | S |  |
| 702.195 | Storied | M7 | S | a player designation |

### Keyword actions (701)

| CR | Name | Milestone | Tier | Notes |
|---|---|---|---|---|
| 701.2 | Activate | M4 | E |  |
| 701.3 | Attach | M4 | E |  |
| 701.4 | Behold | M4 | S | a cost |
| 701.5 | Cast | M2 ✓ (M2.3) | E |  |
| 701.6 | Counter | M2 ✓ (M2.8 ✓) | E | ward uses it (M4); `CounterSpell`, `SpellCountered` |
| 701.7 | Create | M4 | E | D (tokens) |
| 701.8 | Destroy | M2 ✓ (M2.6 ✓; indestructible M2.8 ✓) | E | `allowed(DestroyAction)` |
| 701.9 | Discard | M1 ✓ | E |  |
| 701.10 | Double | M4 (counters), M5 (power and toughness) | E | D |
| 701.11 | Triple | M5 | S |  |
| 701.12 | Exchange | M5 | E |  |
| 701.13 | Exile | M2 ✓ (M2.6 ✓) | E |  |
| 701.14 | Fight | M4 | E | D |
| 701.15 | Goad | M5 | E | common in Commander; needs durations |
| 701.16 | Investigate | M4 | E | Clue tokens |
| 701.17 | Mill | M4 | E |  |
| 701.18 | Play | M1 ✓ (lands), M2 ✓ | E |  |
| 701.19 | Regenerate | M6 | E | D |
| 701.20 | Reveal | M4 | E | D |
| 701.21 | Sacrifice | M4 | E | D |
| 701.22 | Scry | M4 | E | D |
| 701.23 | Search | M4 | E | D |
| 701.24 | Shuffle | M1 ✓ | E |  |
| 701.25 | Surveil | M4 | E |  |
| 701.26 | Tap and Untap | M1 ✓ (tapping by an effect, `TapAll`: M2.8 ✓) | E |  |
| 701.27 | Transform | M4 | E | D |
| 701.28 | Convert | M5 | X |  |
| 701.29 | Fateseal | M4 | X |  |
| 701.30 | Clash | M4 | X |  |
| 701.31 | Planeswalk | out of scope | — | Planechase |
| 701.32 | Set in Motion | out of scope | — | Archenemy |
| 701.33 | Abandon | out of scope | — | Archenemy |
| 701.34 | Proliferate | M4 | E | D |
| 701.35 | Detain | M5 | S |  |
| 701.36 | Populate | M5 | S |  |
| 701.37 | Monstrosity | M4 | S |  |
| 701.38 | Vote | M7 | S |  |
| 701.39 | Bolster | M4 | S |  |
| 701.40 | Manifest | M5 | S |  |
| 701.41 | Support | M4 | S |  |
| 701.42 | Meld | M5 | X |  |
| 701.43 | Exert | M4 | S |  |
| 701.44 | Explore | M4 | S |  |
| 701.45 | Assemble | M6 | X | Steamflogger Boss (Future Sight) modifies assembling; no tournament-legal card assembles, so it's a replacement that can't apply |
| 701.46 | Adapt | M4 | S | D |
| 701.47 | Amass | M4 | S |  |
| 701.48 | Learn | M7 | S | Lessons from outside the game (903.11) |
| 701.49 | Venture into the Dungeon | M7 | S |  |
| 701.50 | Connive | M4 | S |  |
| 701.51 | Open an Attraction | M7 | S | 20 Commander-legal cards |
| 701.52 | Roll to Visit Your Attractions | M7 | S | "Lifetime" Pass Holder, Line Cutter, Command Performance; the turn-based action of 717.4 |
| 701.53 | Incubate | M5 | S |  |
| 701.54 | The Ring Tempts You | M7 | S |  |
| 701.55 | Face a Villainous Choice | M4 | S | another player chooses |
| 701.56 | Time Travel | M4 | S |  |
| 701.57 | Discover | M4 | S | D |
| 701.58 | Cloak | M5 | S |  |
| 701.59 | Collect Evidence | M4 | S |  |
| 701.60 | Suspect | M5 | S |  |
| 701.61 | Forage | M4 | S |  |
| 701.62 | Manifest Dread | M5 | S |  |
| 701.63 | Endure | M4 | S |  |
| 701.64 | Harness | M4 | S | an object designation |
| 701.65 | Airbend | M4 | S |  |
| 701.66 | Earthbend | M5 | S |  |
| 701.67 | Waterbend | M4 | S | a payment alternative |
| 701.68 | Blight | M4 | S |  |
| 701.69 | Heal | M2 | S | removing marked damage |
| 701.70 | Recruit | M4 | S |  |
| 701.71 | Empower Jace | M4 | X | planeswalker tokens |

### Out of scope

**The scope test** (docs/decisions.md, 2026-10-19, "Card scope: tournament legality"):

- A **card is in scope** if Scryfall lists it as legal, restricted or banned in at least one
  paper format.
- A card is **out of scope** only if it has never been tournament-legal: acorn-stamped,
  silver-bordered, a playtest card, memorabilia, or a variant's card such as planes, schemes
  and vanguards.

**A rule is out of scope** only if no in-scope card and no supported format uses it. Each row
below was checked against the card data. The user approved the list.

| Rows | Reason |
|---|---|
| 211, 212, 311, 312, 313, 314, 701.31, 701.32, 701.33, 116.2i, 901, 902, 904 | Casual variants the project doesn't support: Vanguard, Planechase, Archenemy. Their cards (vanguards, planes, phenomena, schemes) are never tournament-legal. |
| 905 (the draft, 905.1-905.2) | A draft isn't a game the engine plays. The game rules for conspiracy cards (315, 702.106, 116.2j) are in scope. |
| 713 | Substitute cards stand in for physical double-faced cards; the engine tracks faces itself. |
| 203, 213 | No game rules. |
| 801, 803, 804, 805, 807, 808, 809, 810, 811; 903.12, 903.13 | Multiplayer options and variants Commander doesn't use (903.2: Free-for-All with the attack multiple players option); the Brawl option; Commander Draft. |

---

## Later (out of scope for this roadmap)

- AI player
- Desktop UI, including the stack visualizer and rules trace
- Networked play between friends
- A Forge-script bulk importer (would likely make the project GPL; decide deliberately)
