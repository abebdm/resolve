# Resolve — Roadmap

Milestones are worked in order. Each milestone ends with every listed item done, tests passing,
and `pytest`, `ruff` and `pyright` clean in CI. Tick items off in the same PR that completes them.

**Current milestone: M1 (in progress). M0 is complete.**

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
- [ ] All phases and steps (500–514), with priority passed in each step where it applies.
- [ ] Untap, draw (including the first-turn draw skip in two-player games), and cleanup
  (discarding to hand size, removing damage, ending "until end of turn" effects).
- [ ] Playing lands (305) as a special action; basic lands' mana abilities; mana pools emptying
  between steps.
- [ ] Basic state-based actions: 0 or less life, drawing from an empty library, lethal damage and
  0 toughness.
- [ ] Concession at any time (104.3a), through its own API entry point, `concede` (design.md §3).
- [ ] Cards: basic lands and a few vanilla creatures.
- [ ] The scenario builder sets the turn, phase, step and priority holder; the fuzz harness's
  allowed gaps move past 103.5.

## M2 — Spells and the stack

- [ ] The full casting process (601.2):
  - announce
  - choose modes, X, and targets
  - total the cost
  - activate mana abilities
  - pay costs
- [ ] Timing rules for sorceries, instants and permanents; flash.
- [ ] Resolution (608), including checking targets again on resolution (608.2b) and partial
  fizzling.
- [ ] Mana payment details: generic, colored, hybrid, X costs, cost increases and reductions,
  including reductions that depend on a count or on the spell's targets (Ghalta, Hamza, Savage
  Stomp).
- [ ] Alternative and additional costs (118.9, 601.2b, 601.2f): casting without paying the mana
  cost, overload (702.96), optional additional costs (offspring, 702.175), "reveal a card or pay
  {1}" (Thunderherd Migration).
- [ ] Casting from zones other than the hand: the graveyard (Quilled Greatwurm), exile and the top
  of the library (Etali, Descendants' Path, discover 701.57, hideaway 702.75); flash granted by an
  effect (Progenitor's Icon); casting prohibitions (601.3, Kutzil); "can't be countered".
- [ ] Mana abilities beyond basic lands (605): "any color in your commander's color identity",
  "any color a land could produce", variable amounts, activation conditions, triggered mana
  abilities (605.1b, Regal Behemoth), and restricted mana with "when that mana is spent" triggers
  (Ixalli's Lorekeeper, Path of Ancestry).
- [ ] The first primitives: damage, destroy, exile, draw, life gain and loss, counter target spell.
- [ ] Cards: about 10 simple spells and creatures drawn from the target decks.

## M3 — Combat

- [ ] Beginning of combat, declare attackers, declare blockers, combat damage, end of combat
  (506–511).
- [ ] Attack and block requirements and restrictions (508.1d, 509.1c), including "can't attack or
  block unless" (Topiary Stomper), "can't be blocked" (Rogue's Passage) and power-based blocking
  restrictions (Champion of Lambholt).
- [ ] Creatures put onto the battlefield tapped and attacking (508.4, Ghalta and Mavren).
- [ ] First strike and double strike damage steps; trample; deathtouch; lifelink; flying and reach;
  vigilance; menace.
- [ ] Multiplayer attacks: choosing which player or planeswalker each creature attacks.

## M4 — Activated and triggered abilities

- [ ] Activated abilities (602), including costs like tapping and sacrificing; equip.
- [ ] Triggered abilities (603):
  - APNAP ordering
  - intervening-if conditions (603.4)
  - looking back in time (603.10)
  - delayed triggers
  - "may" choices
- [ ] Trigger variants: reflexive triggers (603.12), triggering additional times (603.2d, Wayta),
  "do this only once each turn" (Pantlaza), batched "one or more" triggers, and spell-cast and
  ability-activation triggers.
- [ ] Damage-driven triggers (enrage), fight.
- [ ] Counters (122) on permanents and on players (energy): putting and removing them, counters as
  costs, doubling (701.10e) and proliferate (701.34).
- [ ] Keyword abilities built on activated and triggered abilities: saddle (702.171) and "attacks
  while saddled", cycling and landcycling (702.29), outlast (702.107), level up (702.87), adapt
  (701.46), evolve (702.100), ward (702.21).
- [ ] Equipment and auras: attaching, and state-based actions for illegal attachments.

## M5 — Continuous effects and layers

- [ ] The layer system (613): layers 1–7 with the 7a–7d sublayers, timestamps (613.7), dependencies
  (613.8).
- [ ] Static abilities; counters as power/toughness modifiers; effects that grant abilities.
- [ ] Characteristic-defining abilities, Gods and devotion, type-changing effects.
- [ ] Copy effects (707) in layer 1, including copies with exceptions (707.9, Sunfrill Imitator)
  and token copies (offspring, myriad).
- [ ] Interaction tests for classic layer puzzles.

## M6 — Replacement and prevention effects

- [ ] Replacement effects (614), including entering-the-battlefield modifications (614.1c–d, 614.12).
- [ ] Prevention effects (615), including Undergrowth Champion (prevent, then remove a counter) and
  Temple Altisaur (prevent all but 1).
- [ ] Entering-the-battlefield choices and modifications from other permanents: riot (702.136),
  "creatures your opponents control enter tapped" (Kinjalli's Sunwing).
- [ ] Multiple replacement effects with the affected player choosing order (616), including
  counter-placement stacking (for example doubling plus "one additional"), on players as well as
  permanents (Lae'zel).
- [ ] Regeneration (701.19); mana-doubling replacements.

## M7 — Multiplayer and Commander

- [ ] Games with any number of players: APNAP order everywhere; turn order; attacking multiple
  players.
- [ ] Leaving the game (800.4) and all its consequences.
- [ ] Myriad (702.116): token copies attacking each other opponent.
- [ ] The command zone, casting commanders, and commander tax.
- [ ] Commander damage (903.10a) and the zone-change rules (903.9a/b).
- [ ] Color identity and deck validation.
- [ ] The scenario builder refuses commanders `validate_deck` would refuse (903.3, 903.5,
  702.124a), and the tests that use the fixtures' non-legendary commanders are updated.
- [ ] Designations: the monarch, the city's blessing.
- [ ] Loop guard (104.4b).

## M8+ — Card coverage

- [ ] Implement the remaining cards of `gishath_dinosaurs.txt`, tracked by `tools/coverage.py`.
- [ ] Implement the remaining cards of `byrke_counters.txt`.
- [ ] Both decks pass validation and play complete random-agent games with no crashes or invariant
  violations, plus a ruling-derived test for every card.

---

## Later (out of scope for this roadmap)

- AI player
- Desktop UI, including the stack visualizer and rules trace
- Networked play between friends
- A Forge-script bulk importer (would likely make the project GPL; decide deliberately)
