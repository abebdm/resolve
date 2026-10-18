# Resolve — Roadmap

Milestones are worked in order. Each milestone ends with every listed item done, tests passing,
and `pytest`, `ruff` and `pyright` clean in CI. Tick items off in the same PR that completes them.

**Current milestone: M0 (not started).**

---

## Target decks

The finish line for card coverage is fully supporting these two Commander decks (in `decks/`).
Sideboard cards are out of scope.

| Deck | Commander | Colors | Cards |
|---|---|---|---|
| `gishath_dinosaurs.txt` | Gishath, Sun's Avatar | R/G/W | 100 (86 unique non-commander lines) |
| `byrke_counters.txt` | Byrke, Long Ear of the Law | G/W | 100 (81 unique non-commander lines) |

**Mechanics these decks are expected to need.** This list is preliminary and will be confirmed by
the coverage audit in M0.

- **Combat:** flying, trample, double strike, vigilance, haste, indestructible, first strike,
  evasion restrictions.
- **Damage-driven triggers:** enrage-style "whenever this is dealt damage", and fight effects.
- **+1/+1 counters, heavily:**
  - replacement effects that modify how many counters are placed, with 616 ordering
  - counter doubling
  - proliferate
  - evolve
  - outlast
  - level up
- **Static and continuous effects:**
  - anthems and other effects that grant abilities
  - effects that grant mana abilities based on counters
  - Gods and devotion, which change whether something is a creature (layer 4)
- **Protection:** hexproof, protection, and indestructible grants; regeneration.
- **Equipment and auras;** a transforming double-faced card.
- **Mana:**
  - cost reduction
  - mana-doubling replacement effects
  - restricted mana ("spend only on creature spells of the chosen type")
  - conditional mana abilities
- **Library and lands:**
  - land search and fetch effects
  - lands that enter tapped conditionally
  - "choose a color as this enters"
- **Card selection:** reveal or exile from the top of the library, and casting without paying the
  mana cost; discover.
- **Designations:** the monarch, and the city's blessing (ascend).
- **Other:** hideaway; modal spells, including choosing the same mode more than once.

---

## M0 — Skeleton

- [ ] Tooling: `pyproject.toml` finalized, `uv`, `ruff`, `pyright`, `pytest`; GitHub Actions CI
  workflow.
- [ ] `tools/fetch_scryfall.py`: download the Oracle-cards and rulings bulk data into `data/`, and
  record the snapshot date in `docs/rules/README.md`.
- [ ] Card data loader (`resolve.data`) and decklist parser (the `decks/` format).
- [ ] Card registry, plus `tools/coverage.py`: report implemented and missing cards per deck.
- [ ] **Coverage audit:** run the coverage tool on both target decks, then update the "Mechanics"
  list above from the actual Oracle text.
- [ ] Core state types:
  - `GameState`, `Player`, `GameObject`, zones
  - `ObjectId` and `CardId`, timestamps
  - `GameConfig`
- [ ] Task loop with `Done` / `Push` / `NeedDecision`. The public API: `new_game`,
  `pending_decision`, `view_for`, `submit`.
- [ ] Decision request and answer types (enumerated and constrained), plus answer validation.
- [ ] Event type skeleton and event log, with CR citations.
- [ ] `NotImplementedRule` exception.
- [ ] Scenario builder (`tests/scenario.py`).
- [ ] Agents: a random agent and a scripted test agent.
- [ ] `tools/play_cli.py`: a minimal text renderer and CLI agent.
- [ ] Fuzz harness, checking deepcopy/pickle round-trips and replay determinism.

## M1 — Turn structure (1v1 first, multiplayer-shaped data)

- [ ] All phases and steps (500–514), with priority passed in each step where it applies.
- [ ] Untap, draw (including the first-turn draw skip in two-player games), and cleanup
  (discarding to hand size, removing damage, ending "until end of turn" effects).
- [ ] Playing lands (305) as a special action; basic lands' mana abilities; mana pools emptying
  between steps.
- [ ] Basic state-based actions: 0 or less life, drawing from an empty library, lethal damage and
  0 toughness.
- [ ] Concession at any time (104.3a).
- [ ] Cards: basic lands and a few vanilla creatures.

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
- [ ] Mana payment details: generic, colored, hybrid, X costs, cost increases and reductions.
- [ ] The first primitives: damage, destroy, exile, draw, life gain and loss, counter target spell.
- [ ] Cards: about 10 simple spells and creatures drawn from the target decks.

## M3 — Combat

- [ ] Beginning of combat, declare attackers, declare blockers, combat damage, end of combat
  (506–511).
- [ ] Attack and block requirements and restrictions (508.1d, 509.1c).
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
- [ ] Damage-driven triggers (enrage), fight.
- [ ] Equipment and auras: attaching, and state-based actions for illegal attachments.

## M5 — Continuous effects and layers

- [ ] The layer system (613): layers 1–7 with the 7a–7d sublayers, timestamps (613.7), dependencies
  (613.8).
- [ ] Static abilities; counters as power/toughness modifiers; effects that grant abilities.
- [ ] Characteristic-defining abilities, Gods and devotion, type-changing effects.
- [ ] Interaction tests for classic layer puzzles.

## M6 — Replacement and prevention effects

- [ ] Replacement effects (614), including entering-the-battlefield modifications (614.1c–d, 614.12).
- [ ] Prevention effects (615).
- [ ] Multiple replacement effects with the affected player choosing order (616), including
  counter-placement stacking (for example doubling plus "one additional").
- [ ] Regeneration (701.19); mana-doubling replacements.

## M7 — Multiplayer and Commander

- [ ] Games with any number of players: APNAP order everywhere; turn order; attacking multiple
  players.
- [ ] Leaving the game (800.4) and all its consequences.
- [ ] The command zone, casting commanders, and commander tax.
- [ ] Commander damage (903.10a) and the zone-change rules (903.9a/b).
- [ ] Color identity and deck validation; Commander mulligan rules.
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
