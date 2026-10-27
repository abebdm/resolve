# Decision log

Smaller decisions made during implementation that aren't obvious from the code: interpretations of
ambiguous rules, representation choices, deliberate limitations. Large architectural decisions live
in `docs/design.md` and need the user's sign-off; this log is for everything below that level.

Newest entries go at the top. Entries are never deleted. If a decision is reversed, add a new entry
that says so and mark the old one **Superseded by YYYY-MM-DD**.

## Entry format

```markdown
### YYYY-MM-DD: Short title
- **Decision:** what was decided.
- **Why:** the reasoning, including the alternatives considered.
- **Rules:** relevant CR numbers or rulings, if any.
- **Where:** the modules or files affected.
```

---

### 2026-10-27: M2.9: the random seats' payable reversals are checked deterministically
- **Decision (the user's, 2026-10-27):** `test_a_default_run_plays_turns_lands_and_spells_and_
  reports_them` no longer asserts that the random seats reverse some payable cast in the default
  run's first five games. It still asserts that the auto-paying seats reverse none of their
  payable casts and that both kinds of seat have payable casts. The random half is replaced by
  `test_a_payable_cast_reversed_is_counted_for_its_kind_of_seat`: scripted games in which a
  payable cast (Grizzly Bears with two Forests) is answered "pay" at once and reversed, by an
  even seat and by an odd one, plus an unpayable reversal, checked through `PayableCasts`,
  `GameStats` and the summary's `Reversed casts:` line. The quick preset stays at 10 games.
- **Why:** the assertion tested the metric, not a game rule, and it depended on what random
  games happened to do: with Emerald Medallion and Kinjalli's Caller in the recipes, none of
  the first five games (nor the full quick run, 0 of 8) had a random seat reverse a payable
  cast; the first was game 12. M2.7 had raised the sample from four games to five for the same
  reason, and every deck change would break it again. A deterministic test checks the same
  thing, that such reversals are counted for the right kind of seat, every time.
- **Where:** `tests/fuzz/test_fuzz_summary.py`. Partly supersedes the 2026-10-26 entry (M2.7,
  five games) and the "checks the criterion" sentence of the 2026-10-22 entry (M2.5).

### 2026-10-27: M2.9: cost modifiers come from battlefield statics, applied by step without asking
- **Decision:** the total cost (601.2f) is worked out by `resolve.rules.costs.spell_total_cost`
  in `CastSpell`'s `TOTAL` stage: the mana cost with X's value (601.2b first), then every
  `CostModifier` by `ModifierStep` (increases, then reductions, then effects on the total),
  each step's modifiers in battlefield order. The modifiers are those that the
  `SpellCostModifier` abilities of permanents on the battlefield give for the spell
  (`spell_cost_modifiers`), judged on the spell's characteristics on the stack and its
  caster. The total is stored (`CastSpell.total`, `PayCosts.cost`, `CastChoices.total_cost`)
  and never recomputed. A reduction is a modifier of the generic part only (`ReduceGeneric`,
  `ManaCost.with_generic`), so it can't touch colored or colorless symbols and stops at
  nothing (`{0}`).
- **Why:** 601.2f lets the player apply reductions in any order. With generic reductions only,
  every order gives the same total (the generic part is `max(0, generic + increases -
  reductions)`), so a question would have identical answers (design.md §6's canonical answers);
  a reduction whose order matters (118.7b-e: colored, colorless or hybrid amounts) must add
  that choice with its first card; until then, two reductions of which one isn't generic raise
  `NotImplementedRule` (601.2f) in `spell_total_cost`. 113.6 makes a permanent's abilities function only on the
  battlefield, so the Medallion on the stack, in a hand or in a graveyard reduces nothing;
  abilities that function from other zones (113.6b, "this spell costs {1} less", Ghalta) join
  the gathering with their cards (M4). "You cast" is judged as the caster being the
  controller of the ability's source. The first real increase is the commander tax (M7); the
  tests use a test-only one (Test Thorn, `tests/game_fixtures.py`) to check the order.
  `Quality` gained `adjective` ("green", "Dinosaur") so the reduction's text reuses the
  qualities of protection rather than a parallel spell filter.
- **Rules:** 601.2f, 601.8, 118.7, 118.7a, 113.6, 202.3, 205.3; the rulings of Emerald
  Medallion (2023-07-28) and Kinjalli's Caller.
- **Where:** `resolve.rules.costs`, `resolve.cards.primitives.cost_modifiers`,
  `resolve.engine.casting` (`_total`), `resolve.data.mana_cost` (`generic`, `with_generic`),
  `resolve.cards.keywords.qualities` (`adjective`).

### 2026-10-27: M2.8: a countered spell goes to its owner's graveyard, not where it would resolve to
- **Decision (approved by the user, 2026-10-27; revises design.md §17.12 and the M2.6 handoff
  note):** a countered spell is moved to its owner's graveyard by `SpellCountered`, an ordinary
  zone change through the event pipeline (`ApplyEvents`, a new object, 400.7), never by
  `defaults.resolved_spell_destination`. That function now decides only where an instant or
  sorcery goes as it resolves (608.2n). M6's replacement effects (Rest in Peace, flashback's
  exile) change the `SpellCountered` event like any other zone change.
- **Why:** every destination the function exists for applies only "as it resolves": an
  Adventure is exiled (715.3d), an Omen shuffled into its owner's library (720.3d), a buyback
  spell returned to its owner's hand (702.27a). A countered Adventure goes to the graveyard
  (701.6a), so using the resolution function would have been wrong. This matches the M2.6
  decision for a spell that doesn't resolve (608.2b, `SpellDidNotResolve`).
- **Rules:** 701.6a, 701.6b, 608.2n, 715.3d, 720.3d, 702.27a, 400.7, 614.
- **Where:** `resolve.events.spells.SpellCountered`, `primitives.effects.CounterSpell`,
  `defaults.resolved_spell_destination` (docstring); tests in `tests/rules/test_701_6_counter.py`
  (a permanent spell, an instant, the owner's graveyard, an Adventure with the resolution
  destination replaced by exile).

### 2026-10-27: M2.8: keyword prohibitions and where each keyword is read
- **Decision:**
  - Shroud, hexproof, "hexproof from" and protection are prohibitions of
    `legality.allowed(TargetAction)`, read from the candidate's computed characteristics (a
    permanent) or `defaults.player_abilities` (a player). A spell on the stack keeps none of them:
    a permanent's abilities function only on the battlefield (113.6), and 702.11b, 702.16b and
    702.18a speak of a permanent or player, so a hexproof creature spell can be countered.
  - "Opponents" for hexproof is every other player (102.2, 102.3: a free-for-all; teams in 810
    are M9's), the same idiom as `PlayerFilter` and `EachOpponent`.
  - "Hexproof from [quality]" on a player raises `NotImplementedRule("702.11d")`: 702.11d defines
    it for permanents only, and no card gives it to a player.
  - Protection and "hexproof from" judge the targeter's characteristics (`Targeter`): the spell's
    own, or an ability's source's last known information (113.7a). A card-type quality reads
    those characteristics wherever the object is (702.16a: a permanent with the type, or a source
    not on the battlefield of that type).
  - Indestructible is a prohibition of `allowed(DestroyAction)`, used by `Destroy` and by
    704.5g; an indestructible creature with lethal damage gets no event at all (so state-based
    actions don't repeat forever). For 704.5g the action's player is the permanent's controller.
  - "Can't be countered" (`CantBeCountered`, a static ability of the spell) is a prohibition of
    `allowed(CounterAction)`. Targeting the spell is allowed; the counter spell resolves and
    simply doesn't counter it (101.2).
  - Flash is read in `defaults.may_cast_now` from the variant's characteristics; it adds no zone.
  - Protection's damage prevention (702.16e, 702.16j) raises `NotImplementedRule("702.16e")` at
    the top of `DamageDealt.apply`, before anything changes, so every damage path (spells now,
    combat in M3) reaches it; Repentant Blacksmith stays out of the fuzz decks until M6.
  - Redundant instances (702.8b, 702.11h, 702.16m, 702.18b) give one prohibition each kind.
- **Why:** design.md §17.2 and §17.11: one legality check, keywords read only through
  characteristics so M5's grants need no change. 608.2b re-checks targets with the same check,
  so a target that gained hexproof is illegal on resolution (interpretation: 608.2b's "illegal
  target" is judged by the rules for choosing one).
- **Rules:** 702.8, 702.11, 702.12, 702.16, 702.18, 113.6, 113.6g, 113.7a, 101.2, 608.2b, 704.5g.
- **Where:** `resolve.rules.legality`, `resolve.cards.keywords`, `resolve.cards.primitives.statics`,
  `resolve.engine.sba`, `resolve.events.damage`, `defaults.may_cast_now`, `tools/fuzz.py`
  (`FUZZ_EXCLUSIONS`).

### 2026-10-26: M2.7: a choice of modes is a multiset in printed order
- **Decision:** `CHOOSE_MODES` is a `ChooseOne` of `ModesOption(modes)`, one option per choice
  `ModeChoice.combinations` allows among the legal modes: `itertools.combinations` (no repeats,
  700.2d) or `combinations_with_replacement` (repeats allowed), for each count from the minimum
  to the maximum, smallest first. Each lists the indices of its modes in printed order, a
  repeated mode that many times (Fiery Confluence: 10 choices with an artifact on the
  battlefield, 4 without). A mode is legal if each of its instances of "target" has at least its
  minimum of legal targets, each judged alone (700.2a, 115.3), so a mode's legality doesn't depend
  on the others chosen. With one choice nothing is asked; with none the spell isn't offered
  (`can_choose_targets`) and a cast that reaches the stage is reversed. The record keeps the
  modes (`CastChoices.modes`, through the public `ModesChosen`, refused if already set: 700.2f),
  and `CastChoices.targets` lists the instances of each chosen mode in turn. `ResolveTopOfStack`
  checks every target once (608.2b) and gives `ResolveSpell` one `Instruction` per effect with
  its own mode's targets, so `TargetRef(i)` indexes into that mode. A `ModeChoice` whose minimum
  is 0 raises `NotImplementedRule("700.2")` when its choices are listed: whether a modal spell may
  be cast with no mode isn't settled for spells (700.2b covers triggered abilities), and no
  implemented card has "choose up to" or "any number".
- **Why:** 700.2d says a repeated mode is "treated as if that mode appeared that many times in
  sequence", and 608.2c (and the Confluence ruling) that the modes are followed in printed order,
  so the order in which a player names the modes carries nothing: offering permutations would
  give several answers for one outcome (design.md §6). The ruling's "if the same mode is chosen
  more than once, you choose their relative order" matters only through what differs between
  the repetitions, their targets, so that order is the order their targets are chosen.
  design.md §17.8 keeps mode combinations enumerated (the largest real case is small).
- **Rules:** 601.2b, 601.2c, 608.2b, 608.2c, 700.2, 700.2a, 700.2c, 700.2d, 700.2f; Fiery
  Confluence's rulings (2015-11-04).
- **Where:** `resolve.cards.primitives.spells` (`ModeChoice.combinations`, `SpellAbility.chosen`,
  `instances`), `resolve.rules.targeting` (`legal_modes`, `mode_choices`, `can_choose_targets`),
  `resolve.engine.casting` (`MODES` stage), `resolve.engine.resolution` (`Instruction`),
  `resolve.events.spells.ModesChosen`, `resolve.decisions.spaces.ModesOption`.

### 2026-10-26: M2.7: X is any number from 0, and the total cost has its value
- **Decision:** a spell whose mana cost has {X} asks `CHOOSE_X`, a `ChooseNumber(0, None)`, after
  the modes and before the targets; the value is announced publicly (`XAnnounced`) into
  `CastChoices.x`. The total cost (601.2f) is `ManaCost.with_x(x)`: the generic amounts and the
  {X}s added up into one generic symbol where the first of them was, a 0 left out unless nothing
  else is in the cost (`{X}{R}` with 3 is `{3}{R}`, with 0 `{R}`). `SpellCast.total_cost`,
  `PayCosts.cost` and so `PaymentView.cost` are that total; `mana_need` still raises 107.3a for
  an {X} that reaches it (no announced value: an engine bug or a later milestone's case, such as
  107.3h). On the stack the mana value counts X as the announced value (202.3e), off it as 0. The
  value `X()` reads the record (or its last known information); with no value announced it raises
  107.3f.
- **Why:** 107.1b forbids negative choices and 107.3a sets no maximum; what can be paid is found
  out by paying, and an unpayable cast is reversed (733.1), as for every other cost, rather than
  having the engine predict payability (which cost reductions, M2.9, would complicate). Merging
  the generic amounts gives the cost a player would write, and the same `ManaNeed` either way.
  107.3b (X must be 0 when the spell is cast without paying its mana cost) needs M2.10's
  permission and is left to it; 107.3c (X defined by the text) to the first card that has it.
- **Rules:** 107.1b, 107.1c, 107.3a, 107.3b, 107.3c, 107.3f, 202.3e, 601.2b, 601.2f, 733.1.
- **Where:** `resolve.engine.casting` (`X` and `TOTAL` stages), `resolve.data.mana_cost`
  (`has_x`, `with_x`), `resolve.effects.characteristics` (`_x_on_stack`),
  `resolve.effects.evaluation`, `resolve.cards.primitives.values.X`,
  `resolve.events.spells.XAnnounced`.

### 2026-10-26: M2.7: the fuzz summary test reads the default run's first five games
**Partly superseded by 2026-10-27** ("M2.9: the random seats' payable reversals are checked
deterministically"): the five games stay, the random-seat assertion they were chosen for is gone.
- **Decision:** `test_a_default_run_plays_turns_lands_and_spells_and_reports_them` runs the
  default run's first five games (2 to 6 players, all standard) instead of four; its assertions
  are unchanged, and the averages divide by the number of games.
- **Why:** with Fiery Confluence in both recipes the decks changed, and the first four games no
  longer contained a payable cast that a random seat reversed, which the test asserts (M2.5's
  "done when"). The fifth game has one. The full quick run still shows it (1 of 7).
- **Where:** `tests/fuzz/test_fuzz_summary.py`.

### 2026-10-23: M2.6: a spell ability is part of the definition, read through characteristics
- **Decision:** an instant's or sorcery's spell ability (113.3a) is `CardDefinition.spell`, a
  `SpellAbility` (`resolve.cards.primitives.spells`) of one `Mode` (targets, effects) or, from
  M2.7, several with a `ModeChoice`. The engine reads it only as
  `characteristics(...).spell_ability`, apart from `abilities` (so permanents' ability views and
  the auto-payer don't see it). Its text is written from its primitives (`Mode.text`,
  `refs.Phrasing`: the first mention of a target in full, later ones "it"), and the three real
  cards' texts equal their Oracle text without reminder text.
- **Why:** the plan names `CardDefinition.spell`; reading it through `characteristics` keeps the
  rule that everything an object is comes from one place, where M5's text-changing (612) and
  layer 6 plug in. Writing the text from the primitives lets a card test compare the definition
  with the Oracle text, as the mana abilities' tests do.
- **Rules:** 113.3a, 608.2c, 612.
- **Where:** `resolve.cards.primitives.spells`, `resolve.cards.registry`,
  `resolve.effects.characteristics`.

### 2026-10-23: M2.6: targets are chosen per instance of "target"; impossible spells aren't offered
- **Decision:** `CastSpell`'s `ANNOUNCE` stage asks one `CHOOSE_TARGETS` (`ChooseSubset` of the
  legal targets, `minimum` to `min(maximum, legal)`) per instance of the word "target", in the
  order of the text; an instance whose only possible answer is every legal target isn't asked.
  The choices join the record (`CastChoices.targets`, one tuple per instance) through one public
  `BecameTargets` once all are chosen. `defaults.cast_options` doesn't offer a spell for which
  some instance has fewer legal targets than its minimum (`targeting.can_choose_targets`); if
  that happens anyway during the cast (the board changed), the cast is reversed (733).
- **Why:** 601.2c makes such a cast illegal, so offering it could only end in a reversal (the
  plan's "earlier stages offer only legal choices"). A subset space enforces 115.3 (no object
  twice in one instance) by its shape, and separate instances may each choose the same object
  (Decimate's ruling). Asking per instance keeps each question small; the instances are
  independent while no "different targets" wording exists (M4 adds such constraints in
  `check_answer` when a card needs them).
- **Rules:** 601.2c, 115.3, 115.6, 733.1.
- **Where:** `resolve.engine.casting`, `resolve.rules.targeting`, `resolve.rules.defaults`.

### 2026-10-23: M2.6: 115.5 is a prohibition; 608.2b's graveyard isn't the destination function
- **Decision:** `legality.allowed(TargetAction)`'s permissions are the kind, zone and filter
  (115.2, 115.4; a player still in the game, 800.4a; an object whose ID still exists, so still
  in the zone it was targeted in, 608.2b); its one rules prohibition so far is 115.5 (a spell
  can't target itself). Shroud, hexproof and protection join the prohibitions in M2.8. A spell
  that doesn't resolve (608.2b) goes straight to its owner's graveyard (`SpellDidNotResolve`);
  `defaults.resolved_spell_destination` is only for a spell that resolves (608.2n) and, from
  M2.8, a countered one (701.6a).
- **Why:** 115.5 is a "can't" of the rules, and as a prohibition it is cited when it refuses.
  608.2b names the graveyard itself; adventures (715.3d), Omens and buyback change only where a
  *resolving* spell goes, and flashback-style exile is a replacement effect (M6).
- **Rules:** 115.2, 115.4, 115.5, 608.2b, 608.2n, 701.6a, 800.4a.
- **Where:** `resolve.rules.legality`, `resolve.engine.resolution`, `resolve.events.spells`.

### 2026-10-23: M2.6: last known information is a snapshot taken as an object leaves
- **Decision:** `move_object` stores a `LastKnown` (characteristics, controller, owner, zone,
  tapped, damage, spell record) for every object with a card leaving the battlefield or the
  stack, under its old ID in `GameState.last_known`; `PriorityRound` clears it when a player is
  about to receive priority with an empty stack. `effects.evaluation.information(state, obj)`
  gives the current information while the object exists, else this snapshot. Card-less objects
  (copies, abilities on the stack, M4/M5) record none yet: their characteristics can't be
  computed until they exist. Objects leaving with their owner (800.4a) record none either.
- **Why:** an object that changes zones is a new object (400.7), so "is it still where it was
  expected" (608.2h) is "does its ID still exist". A snapshot is taken because characteristics
  are computed, never stored, and can't be computed after the object is gone. Clearing at the
  empty-stack priority keeps the state small; nothing resolving can still refer to them.
- **Rules:** 608.2h, 113.7a, 400.7.
- **Where:** `resolve.state.last_known`, `resolve.state.game.move_object`,
  `resolve.effects.evaluation`, `resolve.engine.priority`.

### 2026-10-23: M2.6: effects give tasks; damage is one event whose apply is the 120.3 table
- **Decision:** a spell's `Effect` gives the tasks that apply it (`Effect.tasks(state, context)`),
  worked out when it applies; `ResolveSpell` applies the effects one at a time in order. Most
  give one `ApplyEvents`; `DrawCards` gives the engine's `DrawCards` task (one draw at a time,
  121.2). `DealDamage` gives one `DamageDealt` to every recipient at once (120.4b), whose `apply`
  turns damage into its results (120.3a, 120.3e; 120.3c and 120.3h raise until counters exist),
  reading the source as it is or as it last existed. 0 damage, 0 life and 0 cards give no task
  (120.8, 119.10, 107.1b), and so does an effect that needs information about an illegal target
  (608.2b).
- **Why:** an effect may need several events in sequence (drawing) or, later, a question
  (608.2d, 608.2g: M2.10, M4); tasks allow both, and `ResolveSpell`'s cursor makes it resume
  where it was. Putting the results in the event's `apply` keeps them after the replacement and
  prevention stage (614-616, M6), which acts on the proposed damage (120.4a-b).
- **Rules:** 608.2c, 608.2h, 120.3, 120.4, 120.8, 119.10, 121.2.
- **Where:** `resolve.cards.primitives.base.Effect`, `resolve.cards.primitives.effects`,
  `resolve.engine.resolution.ResolveSpell`, `resolve.events.damage`.

### 2026-10-22: M2.5's "done when": payable casts reversed, judged by a cross-checked planner
- **Decision:** the plan's M2.5 criterion "the auto-paying seats reverse far fewer casts than the
  random ones" is replaced, by the user, with: **of the casts that could be paid when their
  payment began, the auto-paying seats reverse none and the random seats reverse some.**
  `tools.fuzz.PayableCasts` judges each cast at its first payment decision: payable if that
  decision is `PAY_COSTS` (601.2h asks only when the pool pays in two or more ways) or if the
  auto-payer's planner finds a plan for its `ACTIVATE_MANA_ABILITIES`; a cast asking nothing is
  payable if it is cast. The summary line `Reversed casts:` gives, per kind of seat, the reversed
  casts of all attempts and of the payable ones; `test_a_default_run_...` checks the criterion
  (the random seats' half deterministically since 2026-10-27, M2.9).
- **Why:** the inner random agent casts whatever priority offers, mostly with no way to pay
  (in 30 sample games about nine attempts in ten), and every seat reverses those, so the raw
  reversal counts were about equal (44 of 45 against 61 of 66 in the quick run's first games)
  although the auto-payer cast every payable spell. Because "payable" is judged by the planner
  itself, `tests/agents/test_autopay_brute_force.py` checks it against an exhaustive search
  through the engine (every answer to every payment decision, on copies of the state) on random
  boards (up to six permanents, some tapped or summoning-sick, a pool of up to two units, some
  restricted, an opponent's permanents and mana, a spell cast or a Signet activated with
  priority): the planner must find a plan whenever the search finds a payment, and its plan must
  complete the action. The search's completeness rests on assumptions stated in its docstring.
  150 boards by default, 20 000 with `pytest --thorough` (`tests/conftest.py`). The search found
  two faults in the first version, each now a regression test in `test_autopay.py`: a Signet's
  {1} paid with another Signet's mana wasn't planned (the planner now tries each activation
  order of the Signets it plans); and paying a Signet's {1} from a pool holding the spell's
  {R} could spend the {R}, because `choose_payment` can't see the lands the outer payment will
  still tap (it now keeps colored symbols payable first: a later land pays any generic symbol,
  but a colored one only with its color).
- **Rules:** 601.2g-h, 605.3a, 602.2b, 106.6, 107.4a-c, 118.3, 733.1.
- **Where:** `tools/fuzz.py` (`PayableCasts`, `FuzzResult.payable_reversed`, `GameStats`,
  `summary_lines`), `resolve.agents.autopay` (`_try`), `docs/plans/m2.md` (M2.5).

### 2026-10-22: Payments under way and permanents' abilities are in the view
- **Decision (approved by the user):** `PlayerView.payments` lists the payments under way,
  outermost first (a spell's total cost, then the mana cost of a mana ability activated while
  paying it): payer, cost, purpose, and `spendable`, the mana restrictions (among the payer's
  pool and the mana their permanents' abilities add) that allow spending on it, evaluated by the
  engine. `ObjectView.abilities` gives each permanent's abilities as `AbilityView`s: index, text,
  the mana part of the cost and the mana it adds now (`ManaOutput`: fixed types, or a choice of
  types such as Command Tower's identity colors, and the restriction). Tasks say what they are
  paying through `Task.payment_under_way()`; `view_for` walks the task stack from the bottom.
- **Why:** an agent sees only views (rule 4), and the plan didn't say how the auto-payer learns
  the cost it pays: `PAY_COSTS` gives only the total, the spell's record gets its total cost only
  at 601.2i, a nested request names only the Signet, and `ManaRestriction.allows` needs the
  state. All of it is public (400.2: the battlefield and the stack; 601.2a, 602.2a: what is being
  cast or activated is announced), so every player may see it. The alternatives were a payment
  context on the request (only the deciding player would see it) and giving the auto-payer the
  state (breaks rule 4).
- **Rules:** 400.2, 601.2a, 601.2f-h, 602.2a-b, 605.3a, 106.6, 903.4.
- **Where:** `resolve.engine.view`, `resolve.tasks.Task.payment_under_way`
  (`CastSpell`, `ActivateManaAbility`), design.md §9 and §17.7.

### 2026-10-21: Identical mana in 733.1's dependency check
- **Decision:** when a player reverses some of the mana abilities activated during an illegal
  action, 733.1 refuses to reverse one "unless mana from those abilities ... was spent on another
  mana ability that wasn't reversed". The check replays the kept activations' mana events on the
  pool as it was at the checkpoint. If a kept payment could have spent either of two identical
  units (same type, source and restriction), one already in the pool before the action and one
  that a reversed ability made, it counts as having spent the one already there, so the
  reversal is allowed. A kept payment whose units can't be found at all spent a reversed
  ability's mana, and the answer is refused.
- **Why:** identical units are interchangeable, and `PAY_COSTS` groups them into one class, so
  the player never chose a particular unit; 733.1 can't tell them apart either. Either way the
  state after the reversal is consistent (the kept payment's units are there to spend again).
  The alternative, assuming the newest unit was spent, would forbid reversals that are
  indistinguishable from allowed ones.
- **Rules:** 733.1, 106.4, 601.2h.
- **Where:** `resolve.engine.reversal.check_kept`; tests
  `test_733_1_identical_mana_from_before_the_action_counts_as_what_was_spent` and
  `test_733_1_identical_mana_already_spent_elsewhere_is_no_excuse`
  (`tests/cards/test_selesnya_signet.py`).

### 2026-10-21: Deferred from M2.4: mana abilities and `allowed`; the scope of `can_tap_for_cost`
- **Decision (approved by the user):** mana-ability activation doesn't go through
  `legality.allowed` (101.2) yet. The M2 plan's §2 listed the action, but none of its steps
  built it, so it moves to M4 with the other activations (roadmap M4 item).
  `ActivatedManaAbility.can_activate` decides meanwhile (602.2, 602.5 via `activate_only_if`).
- **Decision (approved by the user):** `defaults.can_tap_for_cost` is for a permanent's own {T}
  in its ability's cost (302.6, 602.5a; {Q} in M9 too). The tap costs of convoke, improvise,
  crew and "tap an untapped creature you control" ignore summoning sickness and must not call
  it. M3's plan should consider renaming it, for example to a shared `summoning_sick` predicate
  that both {T} costs and attacking use (roadmap M3 item; coverage-map notes on 702.51, 702.122
  and 702.126).
- **Why:** both were found during M2.4. The first is the plan's own inconsistency; building it
  now would have widened the step. The second is the test reviewer's note; the plan named the
  function, and renaming it is M3's call.
- **Rules:** 101.2, 602.2, 602.5, 602.5a, 302.6, 702.10, 702.51, 702.61b, 702.122, 702.126.
- **Where:** `resolve.rules.legality`, `resolve.rules.defaults.can_tap_for_cost`,
  `resolve.cards.primitives.abilities`.

### 2026-10-21: M2.4: mana abilities with mana costs, restricted mana, summoning sickness
- **Decision (nested payments):** a mana ability with a mana cost (Selesnya Signet) is paid by an
  embedded `PayCosts` inside `ActivateManaAbility`, which takes its own checkpoint first and, if
  the payment can't be made, reverses itself like a cast (733.1: it asks which of the abilities
  activated meanwhile to reverse). `PayCosts.activations` now holds the `ActivateManaAbility`
  tasks themselves (shared references, pure data), each with its log range and its own payment,
  instead of M2.3's frozen `ManaActivation` records, so a reversal of the outer action sees the
  activations made while paying for an activation. The reversal list is in the order the
  activations began (Signet before the Forest that paid for it); an activation already reversed
  isn't listed, but the abilities kept from it are (`resolve.engine.reversal.activations_made`).
  An activation's own events are its log range minus those of the activations nested in it.
- **Decision (733.1's dependency, "unless mana from those abilities ... was spent on another mana
  ability that wasn't reversed"):** checked by replaying the kept activations' `ManaAdded` and
  `ManaSpent` on the pool as it was at the checkpoint; a kept payment whose units are missing
  spent mana of a reversed ability, and the answer is refused. Identical units: see "Identical
  mana in 733.1's dependency check" above.
- **Decision (passes, 117.4 and 733.2):** activating a mana ability with priority no longer
  clears the passes before it begins; `ActivateManaAbility` clears them when it completes, and a
  reversed activation leaves them (as a reversed cast does).
- **Decision (106.6):** `Mana.restriction` holds a `ManaRestriction` (abstract in
  `resolve.state.mana`, primitives in `resolve.cards.primitives.restrictions`); a payment names
  its purpose (`ForSpell`, `ForAbility`). A class of mana the restriction forbids is offered with
  a maximum of 0 in `PAY_COSTS`, so the space stays canonical and shows the mana.
- **Decision (302.6):** `GameObject.entered_turn` (the turn a permanent came under its
  controller's control; 0 before the first turn) and `Player.last_turn_began` (set by
  `TurnBegan`). A creature may pay {T} costs iff `entered_turn < last_turn_began`; a player who
  hasn't begun a turn can't tap creatures. M5's control-changing effects must set
  `entered_turn` again. The scenario builder defaults permanents to `entered_turn=0` and sets
  each player's last turn as if turns had gone around in order (`at(last_turns=...)` overrides).
- **Decision (903.4, 903.4f, 106.5):** "any color in your commander's color identity" reads the
  combined `color_identity` of the controller's commanders from the card data (903.4a). No
  commander, or no color in the identity, leaves no color to choose: the ability is still
  activated and paid (605.2) and adds nothing. One color isn't asked.
- **Decision (Temple of the False God):** 602.5's "activate only if" is a field of
  `ActivatedManaAbility` (`activate_only_if`), checked in `can_activate`, so it applies with
  priority and while paying alike.
- **Rules:** 106.1a, 106.5, 106.6, 117.4, 302.6, 602.2b, 602.5, 602.5a, 605.2, 605.3a, 605.3c,
  733.1, 733.2, 903.4, 903.4a, 903.4f.
- **Where:** `resolve.engine.mana`, `resolve.engine.payment`, `resolve.engine.reversal`,
  `resolve.engine.casting`, `resolve.engine.priority`, `resolve.rules.defaults`,
  `resolve.rules.commander`, `resolve.state.mana`, `resolve.state.game`,
  `resolve.cards.primitives` (`costs`, `effects`, `conditions`, `restrictions`, `abilities`).

### 2026-10-21: Kept mana abilities' results stand after a reversal (733.1)
- **Decision (the user: "follow the MTG rulebook"):** after an illegal action is reversed, the
  mana abilities the player didn't reverse keep their results exactly as they happened. The
  checkpoint is restored, then each kept activation's logged events are made again as recorded
  (`Event.redo`, in activation order, not logged again); the ability is not activated again.
  `ActionReversed.kept` names their sources. **Supersedes** the plan's and design.md §17.4's
  "re-apply the kept mana abilities with their recorded choices".
- **Why:** 733.1 lets a player reverse mana abilities; those not reversed simply aren't undone.
  Activating one again acts on the restored state: "add {G} for each card in your hand" would
  count the spell back in hand, and Lion's Eye Diamond (M4) would discard it. The test reviewer
  found the problem.
- **How:** each activation records the log range of its activation (`log_from`, `log_to`;
  M2.4 moved them onto `ActivateManaAbility`). Events no player's action causes (`Event.outside_actions`: a concession, leaving,
  the game ending) are skipped: `restore_checkpoint` keeps their consequences. `redo` is
  implemented for `PermanentTapped` and `ManaAdded`; any other event raises
  `NotImplementedRule("733.1")` until a mana ability can cause it (M4).
- **Rules:** 733.1, 605.3a, 800.4a.
- **Where:** `resolve.engine.casting`, `resolve.engine.payment`, `resolve.events.base`,
  `resolve.events.mana`, `resolve.events.permanents`, `resolve.events.game`.

### 2026-10-21: M2.3: casting, paying, reversing and resolving
- **Decision (casting variants):** `cast_options` offers one option per permission and per
  variant the card's layout gives (a split card's halves, both faces of a modal double-faced
  card, an omen's normal part and its Omen, an adventurer and its Adventure), each judged on its
  own characteristics (601.3e, `variant_characteristics`). Choosing a variant other than
  `NORMAL` raises its rule's gap before anything moves (709.3, 712.11b, 720.3, 715.3; 712.11a
  for a transforming card cast transformed, 718.3, 722.3, 708.4, 702.102). A transforming card
  and a preparation card offer only `NORMAL` (712.11, 722.3).
- **Decision (casting zones, rule 12):** `cast_options` asks `cast_permissions` about every card
  in every zone but the stack and the battlefield (the player's hand first, then the command
  zone, graveyards, exile, libraries top first, other hands), so `cast_permissions` alone decides
  which zones a player may cast from; a seam test grants a graveyard permission. The test
  reviewer found the first version listed only the hand and the command zone.
- **Decision (split cards in hand):** a split card's combined characteristics (709.4) are M5,
  so `characteristics` still raises 109.3 for one off the stack, and priority (which asks
  `land_play_options` about every card in hand) reaches that gap first. The 709.3 test asks
  `cast_options` directly. **Why:** implementing 709.4 (two names, combined costs) belongs with
  the split-card row (M5); the halves themselves are read from their own faces.
- **Decision (`PayCosts` is embedded):** `PayCosts` is a procedure object the action's task
  holds in a field (`CastSpell.payment`) and calls (`step`, `check_answer`, `resume`), not a
  task of its own on the task stack. **Why:** reversing a cast (733.1) needs the mana abilities
  activated while paying, and tasks can't read each other; a separate task would have to pass
  them through the game state. M2.4's mana abilities with mana costs and M4's activated
  abilities embed it the same way.
- **Decision (passes and reversal, 733.2):** the priority task no longer clears `passed` when
  a cast begins; `CastSpell` clears it as the spell becomes cast (601.2i). A reversed attempt
  restores the turn from the checkpoint, so earlier passes still count. Nobody holds priority
  while a spell is being cast (`TurnState.priority` is `None`, as during any action).
- **Decision (601.2e):** the check after the proposal asks `legality.allowed` again for the
  spell on the stack, judged from the zone it came from (`cast_permissions` reads
  `spell.cast_from`) and with sorcery timing ignoring the spell itself
  (`has_sorcery_timing(..., ignoring=)`). **Why:** the proposal can't stand in its own way;
  ignoring it everywhere would wrongly allow sorcery-speed actions during casting.
- **Decision (unique answers):** a payment decision isn't asked when exactly one choice of
  counts pays; mana classes are equal `Mana` values (type and source), so two {G} from different
  Forests are different classes. "Pay" alone isn't asked either. A card with no mana cost
  (118.6) can be begun and is reversed at 601.2f.
- **Decision (reversal and leaving):** a player who leaves the game during an attempt (a
  concession) stays gone after the reversal: their current record replaces the restored one and
  their restored objects are removed again (800.4a). A caster who leaves ends the cast silently:
  their spell left with them. The fuzz harness found the first case.
- **Decision (knowledge after reversal):** `ActionReversed` adds every player still in the game
  to the returned card's `known_to` (400.2: they saw it on the stack).
- **Decision (deferred fields):** `CastPermission` has no alternative-cost or destination field
  yet (M2.10, M4); `CastChoices` has no modes, X or targets yet (M2.6, M2.7). `SpellCast`
  records the spell's name as applied, for the log and the fuzz summary.
- **Decision (fuzz decks):** the default run cycles the `spells` (basic lands and every
  noncreature card of the excerpt) and `creatures` (every excerpt card but `FUZZ_EXCLUSIONS`)
  recipes, with `copies` of each basic land and `copies // 2` (at least one) of each card;
  every other Commander game (odd seeds) gives each seat one of the excerpt's creatures as a
  commander. The allowed gaps are 508.1 and 903.8. Reversals far outnumber casts with random
  agents (they often pay before tapping enough), until the auto-payer seats of M2.5.
- **Rules:** 601.2a-i, 601.3, 601.3e, 601.6, 605.3a, 107.4a-c, 118.3, 118.6, 117.3b-c, 117.4,
  405.5, 608.1, 608.3a, 608.2n, 733.1, 733.2, 800.4a, 903.8.
- **Where:** `resolve.state.spell`, `resolve.state.checkpoint`, `resolve.engine.casting`,
  `resolve.engine.payment`, `resolve.engine.resolution`, `resolve.engine.priority`,
  `resolve.rules.defaults`, `resolve.rules.legality`, `resolve.events.spells`, `tools/fuzz.py`.

### 2026-10-21: M2.2: mana costs, colors, 109.3 layouts and `ChooseCounts`
- **Decision:**
  - A `ManaSymbol` has a `kind`, its `colors` and a `number`. 107.4 lists `{C/W}` ... `{C/G}`
    among the monocolored hybrid symbols; they get their own kind (`COLORLESS_HYBRID`) because
    their alternative is one colorless mana, not generic mana, and 202.3f counts it as 1. Hybrid
    pairs are accepted only in the orientation 107.4 lists (`{W/U}`, not `{U/W}`), as Scryfall
    prints them. `{0}`, `{1}`, ... take any decimal number without a leading zero, so Un-set
    costs such as `{1000000}` read.
  - A face with no mana cost has `cost = None`, never `ManaCost(())` (202.3a: no cost, mana value
    0; `{0}` is a cost with mana value 0). A cost that doesn't follow 107.4 (Un-set `{HW}`, `{D}`,
    `{L}`, `{Y}`, `{Z}`) also reads as `None`, with `mana_cost_problem` giving the reason; the
    card loads, and `DeckCard`, `build_deck` and the coverage tool refuse it like an unreadable
    type line.
  - `Characteristics.colors` come from the card data's colors, not from the cost alone. Scryfall
    derives them from the cost and any color indicator (202.2, 204.2), and a card whose colors a
    characteristic-defining ability sets (devoid) reads right too. They are listed in WUBRG order.
    The Scryfall colors of a face with no colors of its own (a split or adventure face) fall back
    to the card's, which is only right once M9 gives those layouts their own characteristics.
  - `Characteristics.mana_value` takes {X} as 0 (202.3e). An object on the stack gets the chosen
    X when M2.3/M2.7 build the stack object. The 202.3b back-face rule needs nothing yet, because
    `characteristics` reads only the front face (712.8d).
  - **The plan was corrected on 109.3 (user, 2026-10-21).** The plan (§6 item 16) said
    `characteristics` should raise a 109.3 gap for omen and preparation cards. The test-reviewer
    showed that 720.4 and 722.4 give these cards only their normal characteristics outside an
    Omen spell on the stack (preparation: in every zone), so the gap blocked cards the rules
    let us read. `characteristics` now returns the front part, whether the data has one face or
    two, for layouts `omen`, `prepare` and Scryfall's `adventure` layout when the second part has
    the Omen subtype (the data files real omens that way). A plain adventure card stays a 109.3
    gap (715.4 would allow the same, but adventures are M4). The gaps that matter are the cast
    variants: casting as an Omen (720.3) and a preparation card's alternative part (722.3) must
    raise `NotImplementedRule` in M2.3; the plan's M2.3 tests list them.
  - `rewrite_words` refuses a mapping from one kind of word to another (613.1c: a color word
    changes into a color word), and walks only `init` fields, so derived fields such as
    `CardFace.types` are recomputed by `__post_init__`.
  - `ChooseCounts(options, maxima, total)` has no minima: units not spent are 0. It needs at
    least one option, and can't be built unless `sum(maxima) >= total`. `RandomAgent` draws each
    valid answer with equal probability by counting completions.
  - `tools/excerpts/cards.json` holds Grizzly Bears, Savannah Lions and Hill Giant, copied from
    the 2026-10-21 snapshot. The coverage tool's "Unreadable" heading now names both the type
    line and the mana cost (the existing test's expected heading changed with it).
- **Why:** the plan (§3.4, §3.8, design.md §17.6-17.10) asks for these; the choices above are the
  ones the plan left open. Per-unit payment options would give several answers for one outcome
  (design.md §6), hence counts.
- **Rules:** 107.4, 109.3, 202.1-202.3, 204.2, 105.2, 612.2, 613.1c, 720, 722, 601.2h.
- **Where:** `src/resolve/data/mana_cost.py`, `src/resolve/data/cards.py`,
  `src/resolve/effects/characteristics.py`, `src/resolve/cards/primitives/words.py`,
  `src/resolve/decisions/spaces.py`, `src/resolve/agents/`, `tools/fuzz.py`.

### 2026-10-21: M2.1: rule defaults, legality and the turn frame
- **Decision:**
  - Every rule default of the M2 plan (§5.1) is a function in `resolve.rules.defaults`. Engine
    code calls it through the module (`defaults.maximum_hand_size(state, player)`), never
    `from ... import`, so replacing the function (a `monkeypatch` seam test now, a real effect
    from M5) is obeyed at every use. `tests/seams.py` has typed helpers for the replacement.
  - `land_play_options` asks `legality.allowed(state, PlayLand(player, card))` for each land in
    the hand. The rules' permission is 305.1 (hand, main phase, empty stack; 305.3 follows from
    sorcery timing). The limit is a **prohibition**, 305.2b ("can't play a land if the number of
    lands they can play is not greater than the number played"), so an effect's extra permission
    doesn't lift it (101.2); an effect that raises `land_plays_allowed` does (305.2a). Playing
    lands from other zones (M5) adds candidates and changes `LandPlayed`, which still takes the
    card from the hand.
  - `cast_options` (plan: M2.3) was extracted now, unchanged, so priority has no inline casting
    timing left. M2.3 replaces its body.
  - `TakeTurn` stays on the task stack for the whole turn and is the turn frame (724):
    `turn_frame_index(state)` finds it; removing the tasks above it and the remaining
    `TurnState.segments` cuts the turn. `segments` holds the phases and steps still to begin
    (a turn starts with all twelve, `TurnBegan.apply` fills it from `turn_structure`).
  - Extra turns: `GameState.extra_turns`, the next one last (500.7). `TakeTurn` carries `extra`
    and `regular`: the turn after an extra turn is the one after the *regular* turn it was added
    to, not after the extra turn's player. An extra turn of a player who left doesn't begin
    (800.4k).
  - `knows_identity(state, obj, viewer)` replaces `view.is_known_to`; the controller of a player
    knows what that player knows (723.4). The same rule shows the controller the controlled
    player's private log entries. The fuzz tests that patched `is_known_to` patch it now.
  - `ManaPoolEmptied` has `kept`: the pool must be exactly `mana` plus `kept`, and `kept` stays
    (500.5 with an effect that keeps mana). `concede(state, player, by=...)` refuses
    `by != player` (723.6); a controlled player may still concede (104.3a).
  - `can_tap_for_cost` keeps M1's behavior: a creature's {T} cost is the 302.6 gap until M2.4.
    `commander_damage_threshold` and `player_abilities` have no engine consumer yet (M7, M2.8).
- **Why:** CLAUDE.md rule 12. Alternatives rejected: patching imported names in each engine module
  (a seam test would pass while another module kept the old function); a separate `TurnFrame`
  marker task (`TakeTurn` already is one); a `position` index into `TURN_SEQUENCE` (an inserted
  phase can't be an index).
- **Rules:** 101.2, 103.4-103.6, 104.3, 117.1a, 302.6, 305.1-305.3, 402.2, 500.5, 500.7-500.11,
  502.3, 504.1, 514.1, 723.4-723.6, 724.1, 800.4k.
- **Where:** `src/resolve/rules/`, `src/resolve/engine/` (`turns`, `priority`, `loop`, `sba`,
  `mana`, `mulligans`, `start`, `view`, `concede`, `setup`), `src/resolve/state/` (`turn`,
  `game`, `invariants`), `src/resolve/events/` (`turn`, `mana`).

### 2026-10-19: Tooling: `tools/rule.py` prints CR text by number
- **Decision:**
  - Rules print line for line from the file (`rule_blocks` in `resolve.data.rules_text`, which
    `parse_rules` is now built on), not rebuilt from number and text: two lines of the pinned CR
    break the usual punctuation (`119.1d.` has a period, `606.5` lacks one).
  - A rule prints with its subrules; a subrule never takes others (704.5a doesn't include
    704.5aa). A section number prints an outline (first lines truncated to 100 characters, with
    subrule counts), never the full section.
  - "See also" lists dotted numbers (`cited_rules`) plus sections cited as "rule 509" or
    "section 4", which the CR uses often; `cited_rules` itself still ignores bare section
    numbers in prose. Numbers printed are left out; for an outline, every number in its section.
  - The glossary is the text after the last "Glossary" line and before the last "Credits"
    (`parse_glossary`). Terms match exactly, ignoring case; a miss lists terms containing the
    text, then the closest spellings, and exits 1 like an unknown rule number.
  - The pinned file's path is `PINNED_RULES_FILE` in `resolve.data.rules_text`, the one place a
    CR update changes; the citation test uses it too.
- **Why:** agents looked rules up with Grep, which misses continuation paragraphs and pulls in
  704.5aa when asked for 704.5a; a full section can be thousands of lines.
- **Where:** `tools/rule.py`, `src/resolve/data/rules_text.py`,
  `tests/tooling/test_rule_tool.py`.

### 2026-10-19: Agents look up reference docs instead of reading them in full
- **Decision:** agents read `docs/design.md`, the current milestone's roadmap section and their
  step of the plan in full. They look up everything else by heading or rule number: the CR,
  the rest of the roadmap, the torture tests, howto, primitives, decisions and verification.
  CLAUDE.md's "Current status" holds only the current step, known rule violations and what's
  next. The per-step list of what was built moved to `docs/roadmap.md`, "What's built". Test
  runs use `-q`, and only failing tests are re-run while fixing.
- **Why:** reading every listed doc cost each new agent about 50,000 tokens before it began,
  and CLAUDE.md is re-sent with every request. Sessions hit usage limits mid-task. The reference
  docs are logs and catalogs, so one task needs only a few entries, and the heading list shows
  what else exists. No check or test is skipped.
- **Rules:** none.
- **Where:** `CLAUDE.md` ("Read first", "Current status", "Run everything before finishing",
  "Keep your context small", "Documentation requirements"), `docs/roadmap.md`,
  `.claude/agents/test-reviewer.md`.

### 2026-10-19: Card scope: tournament legality
- **Decision (the user's test):** a card is **in scope** if Scryfall lists it as legal or banned
  in at least one format. It is **out of scope** only if it is acorn-stamped, silver-bordered, or
  otherwise never tournament-legal. This replaces "appears in an Un set". A rule is out of scope
  only if no in-scope card and no supported format uses it.
- **Decision (reading the test):** only **paper formats** count, and "restricted" (Vintage)
  counts as legal.
  - Of 38,861 cards in the snapshot, 702 are legal only in MTG Arena formats (alchemy, historic,
    timeless, gladiator, brawl, standardbrawl, competitivebrawl): 638 Alchemy cards plus
    digital-only versions.
  - Sixteen of those are acorn-stamped Mystery Booster Commander cards that Arena lists as
    legal, so counting every format would put acorn cards in scope, which the test says can't
    happen.
  - Alchemy cards also use mechanics the CR doesn't define ("seek", "perpetually"), and the
    engine follows the CR.
  - **Confirmed by the user** (paper formats only).
- **Check against the card data:** the pinned snapshot (2026-10-17) can't be downloaded again
  (2026-10-18 "Snapshot drift"). The check used Scryfall's Oracle-cards file of 2026-10-18
  (`oracle-cards-20261018210200`), the same one the excerpts came from.
  - Legal or banned in a paper format: 32,199 cards. **None** is acorn-stamped or
    silver-bordered, so the test and the stamp and border criteria agree exactly.
  - Never legal in a paper format: 6,662 cards. 3,863 are tokens, emblems, art cards and
    variant cards; 129 are acorn-stamped; 458 silver-bordered; 702 legal only on Arena. The
    other 1,510 are playtest cards, memorabilia and unreleased sets, such as Star Trek (released
    2026-11-13).
  - Scryfall gives unreleased cards no legality, so they come into scope when a later snapshot
    is pinned after their release. Stamps and borders belong to a printing, while legality
    belongs to the card, so legality decides.
- **Rows moved into scope** (all were out as "Un-set only" or as a variant):

  | Rows | In-scope cards | Tier, milestone |
  |---|---|---|
  | 123 stickers | 47 Unfinity cards that use stickers and 48 sticker sheets, all Commander-legal | set mechanic, M5 (characteristics) and M7 (sheets chosen before the game) |
  | 717 Attraction cards | 22 Attractions without the acorn stamp, Commander-legal | set mechanic, M7 |
  | 702.159 visit | the same 22 Attractions | set mechanic, M7 |
  | 701.51 open an Attraction | 20 Commander-legal cards (Complaints Clerk, Coming Attraction, ...) | set mechanic, M7 |
  | 701.52 roll to visit your Attractions | "Lifetime" Pass Holder, Line Cutter, Command Performance | set mechanic, M7 |
  | 702.158 space sculptor, 704.5u | Space Beleren (oval stamp, Commander-legal) | exotic, M7 |
  | 701.45 assemble | Steamflogger Boss (Future Sight) modifies assembling; no tournament-legal card assembles | exotic, M6 |
  | 407 ante | 9 ante cards (Contract from Below, Darkpact, Jeweled Bird, ...), banned rather than never legal | exotic, M7 |
  | 315 conspiracies, 702.106 hidden agenda, 116.2j | 25 conspiracy cards, banned rather than never legal (14 with hidden agenda); used only in limited play (315.1) | exotic, M7 |

  All are set mechanics or exotic, so they're implemented in M9. Their milestones say which
  systems must leave room. M7's checklist now names what players bring besides their deck
  (Attraction decks, sticker sheets, conspiracies, ante).
- **Rows that stay out of scope:** the Vanguard, Planechase and Archenemy rows (none of their 414
  cards is legal or banned anywhere); 905's draft (the game's conspiracy rules are 315 and
  702.106); substitute cards; the sections with no game rules; and the multiplayer options and
  variants Commander doesn't use.
- **Why:** the user's goal is every card that has ever been tournament-legal. Unfinity's
  black-bordered cards are legal in Commander, the project's format. Ante cards and conspiracies
  are banned, not never legal.
- **Rules:** 123, 315, 407, 701.45, 701.51, 701.52, 702.106, 702.158, 702.159, 704.5u, 717, 905.
- **Where:** `docs/roadmap.md` (the coverage map and its out-of-scope list, M7), `docs/design.md`
  §1, `docs/plans/m2.md` (approval notes), `README.md`, `docs/torture-tests.md`.

### 2026-10-19: The M2 plan, the rules coverage map, torture tests, and rules 12 and 13
**Superseded in part by 2026-10-19 "Card scope: tournament legality"**: the rows below marked out
of scope as Un-set only (717, 702.158, 702.159 and the rest) are in scope, and so are ante and
conspiracy cards.
- **Decision:** M2 follows an approved plan, `docs/plans/m2.md`, in twelve steps (M2.0 to
  M2.11). M2.0, documentation only, comes first, so every later step starts from the updated
  rules.
- **Decision:** the keyword table becomes the **rules coverage map** (`docs/roadmap.md`): every
  numbered section of the pinned CR, every keyword ability and every keyword action, each with
  the milestone where its rules live and a tier. The tiers and the M9 rule are unchanged; M9
  becomes "Rules coverage".
  - The pinned rules have 145 numbered sections outside 701 and 702, 194 keyword abilities
    (702.2-702.195) and 70 keyword actions (701.2-701.71). The "Keyword coverage" entry below
    said 71 actions.
  - Rows the map assigns to a milestone also became checklist items in that milestone's own
    roadmap section: planeswalkers and loyalty abilities, tokens, emblems, the legend rule,
    double-faced cards and library search in M4; extra turns, phases and steps in M3.
- **Decision:** the rows flagged for review were decided against the pinned CR. The user
  decided:
  - planeswalkers (306) M4, evergreen;
  - extra turns and phases (500.7-500.10) M3;
  - the legend rule (704.5j) M4;
  - double-faced cards (712) evergreen;
  - Sagas (714) set mechanic;
  - text-changing (612) exotic;
  - Attractions (717) out of scope (Un-only);
  - subgames (729) in scope, exotic, M9;
  - 206 in scope, exotic, M9. City in a Bottle, Golgothian Sylex and Apocalypse Chime refer to
    names "originally printed" in a set; 206.3a-c list those names, so the card data needs
    nothing more.

  The rest were decided here:
  - Intimidate, landwalk and fear: evergreen, M3 (retired evergreen, on many cards).
  - Prowess: evergreen, M5 (common since 2015).
  - Partner: evergreen, M7 (Commander is the project's format).
  - Exchange (701.12) evergreen M5; goad (701.15) evergreen M5 (it needs durations); investigate
    (701.16) evergreen M4.
  - Phasing: exotic, M5.
  - Level up: M4. Leveler cards (711): M5, since level symbols are static abilities setting
    base power and toughness (711.2).
  - Preparation cards (722): set mechanic, M5.
  - Shortcuts (732): evergreen, M7.
  - ∞ (702.186): set mechanic, M5. It is the harness mechanic (701.64), not Un-only.
  - Paradigm (702.192) set mechanic M5; storied (702.195) set mechanic M7 (a designation);
    harness (701.64) set mechanic M4.
  - Heal (701.69) set mechanic M2; recruit (701.70) set mechanic M4; Empower Jace (701.71)
    exotic M4; learn (701.48) set mechanic M7 (outside the game, 903.11).
  - Space sculptor (702.158) and visit (702.159): out of scope, Un-set only.
- **Decision:** the out-of-scope list (in the map) was approved by the user: Un-set rules,
  casual variants, ante, substitute cards, sections with no game rules, and the multiplayer
  options and variants Commander doesn't use.
- **Decision:** a new non-negotiable rule, **12: no hard-coded rule defaults**. The M0/M1 code
  breaks it (one land per turn, maximum hand size seven, the fixed turn sequence, the affected
  player always deciding, and the others listed in `docs/plans/m2.md` §5.1), and M2.1 removes
  every violation. The test-reviewer checks for it. Until M5, each default is tested through a
  `monkeypatch` seam (CLAUDE.md, "Rule defaults are tested through their seam"); M5 replaces
  those tests with tests using real effects.
- **Decision:** a new non-negotiable rule, **13: torture tests**. `docs/torture-tests.md` lists
  famously difficult cards. Each milestone's plan handles those that touch its systems, and
  implements those assigned to it. The test-reviewer checks for it.
- **Decision:** `docs/design.md` §17 holds designs a milestone's plan approved before their code
  exists. Each is marked provisional: the milestone that builds it may revise it with the user's
  sign-off, and once built it moves into the section it belongs to. This is an exception to
  design.md's "same PR as the code" rule.
- **Decision:** illegal actions are reversed (733) by **restoring a checkpoint** taken when the
  action began, then applying again the mana abilities the player chose to keep (design.md
  §17.4). The counters and the RNG are never rewound. The alternative considered, recording an
  inverse for each change, can't restore exactly the objects M4's costs move.
- **Decision:** M2 implements, besides its 14 target-deck cards:
  - eight real keyword example cards, whose only text is the keyword: Ashcoat Bear, Gladecover
    Scout, Humble Budoka, Darksteel Relic, Darksteel Myr, Repentant Blacksmith, Nacatl Savage,
    Cancel;
  - two torture-test cards, Decimate and Cryptic Command.

  They go in the default registry and the fuzz decks, except Repentant Blacksmith, which stays
  out of the fuzz decks until protection's damage prevention (702.16e) exists in M6.
- **Decision:** the plan file stays cheap to read. The coverage map and the torture tests live
  only in their own files, and the plan points to them. Each step's agent reads the plan's "How
  to use this plan", its own step, the sections that step references, and the handoff notes.
- **Why:** the user's goal is every non-Un card with no shortcuts. Each change makes sure the
  systems built now leave room for every rule and the hardest known cards, without implementing
  them all now.
- **Rules:** 101.2, 206.3, 500.7-500.11, 601.2, 601.3e, 702, 701, 704.5j, 707.10, 712, 723,
  733.
- **Where:** `docs/plans/m2.md`, `CLAUDE.md`, `docs/roadmap.md`, `docs/design.md` §17,
  `docs/torture-tests.md`, `.claude/agents/test-reviewer.md`, `README.md`.

### 2026-10-19: Keyword coverage: tiers, M9, and planning for every keyword
**Superseded in part by 2026-10-19 "The M2 plan, the rules coverage map, torture tests, and rules
12 and 13"**: the keyword table became the rules coverage map, M9 became rules coverage, and
CR 701 has 70 keyword actions, not 71.
- **Decision:** the engine aims to support every keyword ability (CR 702: 194 in the pinned rules)
  and keyword action (CR 701: 71), not only those the target decks use. The roadmap's keyword
  table gives each one the milestone where its rules live and a tier:
  - **evergreen/common** keywords are implemented in that milestone;
  - **set mechanics** and **exotic** keywords are implemented in the new M9 (keyword coverage),
    unless a target deck needs one, which is then done in its own milestone.

  Card coverage for the target decks is M8 (formerly "M8+"). Every milestone's plan skims all of
  CR 702 and 701 and designs its systems to leave room for every keyword, implemented now or not
  (CLAUDE.md, "Planning a milestone").
- **Why:** the user wants every keyword eventually. Adding a keyword is cheap once the system it
  plugs into exists, but retrofitting a system not designed for it is expensive (for example two
  combat damage steps for first strike, or priority for split second). Implementing all ~265
  keywords as their milestones land would roughly double each milestone, so only the common ones
  are done early, and the engine reaches playable games with the target decks sooner.
- **Where:** `CLAUDE.md` ("Planning a milestone"), `docs/roadmap.md` (M2, M8, M9, "Keyword
  table"), `docs/design.md` §11.

### 2026-10-19: Basic-land decks, presets and the summary of the fuzz command line
- **Decision:** `uv run python tools/fuzz.py` gives the players decks of basic lands, the same
  number of each, so its games play turns (lands, mana abilities, priority, cleanup, decking,
  concessions); this supersedes "The CLI defaults to empty decks" in 2026-10-18 "The fuzz
  harness". The seats get two deck sizes in turn (40 and 10 cards in the quick run, 40 and 20 in
  the thorough one; `--copies`). `--empty-decks` keeps the old decks, and `--deck` still takes
  decklists from the snapshot.
- **Why:** before each decision a player concedes with a fixed chance, and the number of
  decisions per turn grows with the square of the player count, so with 40-card decks every
  multiplayer game ended by concession (20 of 20 measured at 1 in 500). The smaller decks deck
  out first, so both endings show up (quick: 4 decked, 6 conceded; thorough's first 10 games:
  4 and 6), and the seats' libraries differ in size.
- **Decision:** the basic lands' card data is an *excerpt*: their Scryfall records copied by
  `tools/card_excerpt.py` from a snapshot into `tools/excerpts/basic_lands.json` (committed),
  trimmed to the fields `parse_card` reads (`EXCERPT_CARD_FIELDS`), with their rulings (none)
  and the snapshot's manifest (`taken_from`), and loaded by `resolve.data.cards.
  load_card_excerpt`. `--check` compares an excerpt with the local snapshot. It was taken from
  the Scryfall snapshot of 2026-10-18, as Scryfall no longer serves the pinned 2026-10-17 one;
  basic lands' Oracle data doesn't change between snapshots.
- **Why:** CI and fresh checkouts have no snapshot, tools never invent card data (2026-10-18
  "The fuzz harness"), and tools can't import `tests/scryfall_fixtures.py`, whose records are
  hand-written. A copied excerpt is real data, small, and checkable against a snapshot. The
  loader lives in `resolve.data` because tools run as scripts can't import each other.
  Printing fields (prices, images, sets) are dropped because they change daily.
- **Decision:** the command line has two presets (`Preset`): the quick default (`QUICK`: 10
  games, one of each player count 2-6 in each format, concessions 1 decision in 200, full checks
  every 10 answers; about 20 seconds on 4 cores) for agents and day-to-day work, and
  `--thorough` (`THOROUGH`: 100 games, concessions 1 in 500, full checks before every decision;
  about an hour on 8 cores) for the user's verification at the end of a milestone
  (`docs/verification.md`). Explicit options override either. Games run in worker processes
  (`--jobs`, default the number of CPUs, "spawn" start method everywhere because Windows has no
  other); each game depends only on its spec, so the output is the same for any `--jobs` except
  the timing. Long runs print a line every 10 games, and a failure prints the run's options with
  the game's reproduce command.
- **Why:** the user asked for runs that are short when agents test and long when they verify a
  milestone by hand; CLAUDE.md now makes this the rule for every run whose length is a
  trade-off. Checking every decision costs about 60 to 170 ms per decision in long 2- to
  6-player games here, so the thorough run needs parallel games to finish in about an hour; 10
  rounds of the player counts and formats give 100 seeds.
- **Decision:** `fuzz_run` takes `check_every` (default 1, so the tests' games are checked
  before every decision as before): the full checks (`state_problems`, the copies, the invalid
  answers, and that a rejected answer changed nothing) run when the number of accepted answers
  is a multiple of it and on the final state; `invariant_violations` runs before every decision
  and the replay after every game. A rejected answer that changed the state between full checks
  still fails the replay, which never submits it.
- **Decision:** a full check walks only the log entries added since the previous one
  (`CheckedLog`, `state_impurities(log_from=...)`): the log only grows and its entries are
  deeply immutable, so an entry checked once stays checked while the log holds that same
  object; a checked entry that was replaced or removed is reported. The purity and
  immutability walks build a path string only for a problem and cache dataclass field names.
- **Why:** the full checks walk, copy and compare the whole state, and the event log grows with
  the game, so checking every decision costs time quadratic in its length: a 3-player 40-card
  game of 500 answers took 90 seconds. The incremental log walk and the cheaper walks halved
  the quick run's time; the rest (deepcopy, pickling, equality, building views) is inherent to
  the checks.
- **Decision:** the summary names a game's ending by how the last player to lose lost
  (`ending`): decked (704.5b), life total (704.5a), concession (104.3a); a game without a winner
  is a draw (104.4a) however its players lost; a game stopped at an allowed gap is a rules gap;
  anything else is "other (<rule>)". It also reports answers and turns per game (min, average,
  max; turns are the last turn's number) and the lands played and mana abilities activated
  (`LandPlayed` and `ManaAdded` events).
- **Rules:** 104.2a, 104.3a, 104.4a, 305.1, 305.2, 605.3a, 704.5a, 704.5b; design.md §7, §14.
- **Where:** `tools/fuzz.py`, `tools/card_excerpt.py`, `tools/excerpts/basic_lands.json`,
  `resolve.data.cards`, `resolve.state.invariants`, `tests/fuzz/`, `tests/tooling/
  test_card_excerpt_tool.py`, `docs/verification.md`.

### 2026-10-18: Conceding and leaving the game
- **Decision (plan ★1):** M1 implements leaving the game for everything that can exist in M1:
  `LeaveGame` (`PlayerLeftGame`) removes every object the player owns from every zone and
  empties their mana pool (800.4a); if they held priority, the priority task gives it to the
  next player in turn order (800.4a); a turn whose active player left continues without one
  (800.4j: no draw, no discard, priority starts with the next player); a player who left begins
  no turns (800.4k); a choice a rule asks of a player who left goes to the next player in turn
  order (800.4h; before 103.1 in seating order). Objects whose controller differs from their
  owner (only control-changing effects could make them, and none exist; the scenario builder
  can) raise `NotImplementedRule("800.4a")`. M7 keeps the rest of 800.4.
- **Decision:** `Player.lost` and `Player.left_game` are separate: a loss (704.5, 104.3a) is
  followed by leaving (104.5). The game ends once at most one player is left (104.2a, 104.4a);
  the losers leave first, so their objects are gone from the final state. Losers of one check
  leave one at a time in APNAP order, then the end check runs once.
- **Decision (★2):** `concede(state, player)` withdraws the pending request, logs `Conceded`,
  applies `PlayerLost` (104.3a) and the leaving, and runs the loop. Every asking task's `run`
  is re-entrant: `StartGame` keeps its chooser instead of drawing again; `OpeningHands`,
  `DiscardToHandSize` and `CheckStateBasedActions` ask again or skip players who left (an SBA
  check whose objects or players vanished is computed again); `PriorityRound` asks again.
- **Decision (interpretation):** when the player who would receive priority has left, earlier
  passes still count. If every player still in the game has passed in succession, that is all
  players passing (117.4): the step ends (or the stack resolves). Otherwise the next player in
  turn order receives priority. The fuzz harness found the first case (four players: three had
  passed when the holder conceded). **Why:** 800.4a's last sentence alone ("priority passes to
  the next player in turn order") could be read as giving that player priority again even
  though they passed; but 117.4 ends the step once all players have passed in succession,
  just as it overrides 117.3d after an ordinary pass, and 800.4j says the same for a
  departed active player ("or the phase or step ends, whichever is appropriate"). The CR
  doesn't settle it explicitly; the user confirmed this reading (2026-10-18).
- **Decision (★3):** a replay is the config, decks, seed and the ordered inputs: answers and
  concessions (`resolve.agents.replay`). The fuzz harness concedes for a random player now and
  then (`--concessions N`, default 1 in 200 decisions), in the state and its copies alike, and
  replays the inputs at the end. A replay whose game asks another question, ends sooner, or
  has the conceding player already out raises `ReplayDiverged`.
- **Decision:** `PlayerLeftGame` is public and names the objects that left from every zone
  but the library; it only counts the library's (`library_size`). Library object IDs are
  never shown to other players (design.md §9), and redacting a public event would have hidden
  the rest for no gain; the leaving player doesn't need the IDs either.
- **Decision:** a concession during another player's decision keeps the answers already
  given where the question is unchanged: the cards chosen for a discard or for the bottom of
  a library are kept and only their order is asked again; an owner's order of dying
  creatures stands unless the check changes (it is computed again, and its orders asked
  again, when a player who left owned some of its creatures). A concession draws no
  randomness: the 103.1 chooser isn't determined again.
- **Decision:** a game that began with more than two players stays multiplayer after players
  leave (100.1b, 103.5c, 103.8c): `is_multiplayer` counts seats.
- **Rules:** 100.1b, 103.5c, 103.8c, 104.2a, 104.3a, 104.4a, 104.5, 117.4, 800.4a, 800.4h,
  800.4j, 800.4k.
- **Where:** `resolve.engine.concede`, `resolve.engine.sba`, `resolve.engine.priority`,
  `resolve.engine.start`, `resolve.engine.mulligans`, `resolve.engine.turns`,
  `resolve.agents.replay`, `tools/fuzz.py`.

### 2026-10-18: Creatures, damage and state-based actions 704.5f and 704.5g
- **Decision:** damage is a number marked on the permanent (`GameObject.damage`, 120.6); only
  permanents have any, and a new object has none (400.7). Nothing deals damage yet (combat is
  M3, damage effects M2), so tests mark it with the scenario builder.
- **Decision:** `characteristics` gives power and toughness from the printed numbers (208.1,
  302.4c) through `power` and `toughness`, which raise `NotImplementedRule("208.2")` for a star;
  a missing value counts as 0 for the state-based actions (208.5). A noncreature permanent has
  `None` even with numbers printed on it (a Vehicle); off the battlefield a card has its printed
  numbers (208.3).
- **Decision:** 704.5f puts a creature with 0 or less toughness into its owner's graveyard as
  `PutIntoGraveyard` (not destroyed, 701.8b); 704.5g destroys a creature with toughness above 0
  and damage at least its toughness (`PermanentDestroyed`, 701.8a). A creature with 0 toughness
  and damage gets only 704.5f. The events of one check are listed creatures first (battlefield
  order), then players; they are applied as one `ApplyEvents`.
- **Decision:** when one check puts two or more cards into one player's graveyard, that owner
  orders them first (404.3, `ORDER_CARDS`, listed top to bottom; owners asked in APNAP order,
  from the active player: `apnap_order`, 101.4).
  `CheckStateBasedActions` holds the check's events while it asks, so the check isn't
  recomputed between the answers.
- **Decision:** 514.2 removes all damage from permanents as one `DamageRemoved` event after the
  discard, and before 514.3a's check, so damage marked as cleanup begins can't kill. A
  state-based action in the cleanup step now gives the active player priority there, and
  another cleanup step follows (514.3a, tested with a 0-toughness creature).
- **Decision:** the vanilla creatures are Grizzly Bears, Savannah Lions and Hill Giant, whose
  Oracle text is empty. Their definitions hold only names. Their test fixtures were checked
  against the Scryfall snapshot of 2026-10-18: same mana cost, type line, power and toughness,
  and empty Oracle text.
- **Decision:** mana pools now empty in APNAP order (101.4, `apnap_order`), not turn order as
  the M1.3 entry "Lands, mana abilities and mana pools" said (superseded on that point). The
  pools empty simultaneously either way; APNAP is the order the engine lists simultaneous
  per-player events in.
- **Rules:** 101.4, 120.6, 208.1, 208.2, 208.3, 208.5, 302.4c, 404.3, 514.2, 514.3a, 701.8a,
  701.8b, 704.3, 704.5f, 704.5g.
- **Where:** `resolve.engine.sba`, `resolve.engine.turns.RemoveDamage`,
  `resolve.events.permanents`, `resolve.effects.characteristics`,
  `resolve.cards.definitions.vanilla_creatures`, `resolve.engine.mana`.

### 2026-10-18: Lands, mana abilities and mana pools
- **Decision:** playing a land is a `PlayLandOption` at priority (305.1-305.3, 116.2a) and one
  `LandPlayed` event: the land becomes a new, untapped permanent under its player's control
  (400.7, 110.5b) and `TurnState.lands_played` counts it (305.2a). The limit is one land per
  turn; no effect can add land plays yet.
- **Decision:** mana abilities are activated at priority with `ActivateAbilityOption(object,
  ability)`, where `ability` indexes the object's *computed* abilities (`characteristics`), so
  intrinsic abilities (305.6) are activatable like printed ones. Activation pays the costs as
  one `ApplyEvents`, then applies the effect as another (602.2b, 601.2h, 605.3b); nothing goes
  on the stack. Like a land play, it is an action: the same player receives priority again and
  `passed` starts over (117.3c, 117.4). Mana abilities during casting or payment (605.3a's other
  cases) come with casting in M2.
- **Decision:** a basic land type's mana ability isn't in any definition: `characteristics` adds
  "{T}: Add [mana symbol]" for each basic land type of a land, after its printed abilities, in
  type-line order (305.6). Basic land definitions therefore have no abilities: their Oracle text
  is reminder text.
- **Decision:** mana pools hold `Mana` units (type and source, 106.3), so 106.6 restrictions
  can attach to units later. As each step and main phase ends, every non-empty pool empties
  (`ManaPoolEmptied`, 500.5, 703.4q), in turn order (**superseded by 2026-10-18 "Creatures,
  damage and state-based actions 704.5f and 704.5g"**: APNAP order). A player who passes
  announces their pool (`PriorityPassed.mana_in_pool`, 117.3d, 106.4b). Pools and tapped
  status are public in views.
- **Decision:** the untap step untaps every tapped permanent the active player controls as one
  `PermanentsUntapped` event (502.3); with nothing tapped, nothing is logged.
- **Decision:** `TapSelfCost` on a creature raises `NotImplementedRule("302.6")`: whether a
  creature has been controlled since its controller's most recent turn began isn't tracked
  yet. No M1 card has such an ability.
- **Decision:** primitives' base classes live in `resolve.cards.primitives.base`, which imports
  nothing from the engine, so `CardDefinition` (imported by `resolve.state.game`) can name
  `Ability` without an import cycle. `TapSelfCost` imports `characteristics` inside its method
  for the same reason.
- **Rules:** 106.3, 106.4, 106.4b, 107.5, 110.5b, 110.5d, 116.2a, 117.3c, 117.4, 118.3, 302.6,
  305.1-305.3, 305.6, 305.8, 500.5, 502.3, 602.2, 605.3a, 605.3b, 701.26, 703.4q.
- **Where:** `resolve.cards.primitives`, `resolve.cards.definitions.basic_lands`,
  `resolve.engine.priority`, `resolve.engine.mana`, `resolve.events.permanents`,
  `resolve.events.mana`, `resolve.state.mana`.

### 2026-10-18: Turns, steps and priority
- **Decision:** `TakeTurn` runs `TURN_SEQUENCE` (`resolve.state.turn`): every step, with a main
  phase as a segment whose step is `None` (505.2). Each segment is a `RunStep`: `StepBegan`
  (logged; "at the beginning of" triggers will match it, 500.6), turn-based actions, a
  `PriorityRound` except in untap and cleanup (117.3a, 502.4, 514.3), then the end of the step.
  Skipped steps don't begin at all (500.11): the starting player's first draw step in a game
  with exactly two seats (103.8a; a game that began with more players never skips, 103.8c,
  even after players leave), and declare blockers and combat damage whenever no attackers were
  declared (508.8), which is always until M3 because declaring attackers raises
  `NotImplementedRule("508.1")` whenever the active player controls a creature. The turn after
  cleanup belongs to the next player in turn order still in the game.
- **Decision:** the priority holder (`TurnState.priority`) and the players who passed in
  succession (`TurnState.passed`) are procedural pointers kept by `PriorityRound`, not events.
  `PriorityPassed` is logged as the record of each pass but changes nothing. They live in the
  state, not in the task, so views, invariants and the scenario builder can read and set them.
- **Decision:** each time a player would receive priority, `CheckStateBasedActions` runs first
  (117.5, 704.3), also before the next player after a pass. The step ends when every player
  still in the game has passed in succession with an empty stack; with an object on the stack
  the game stops at `NotImplementedRule("608.1")` (M2).
- **Decision:** legal actions the engine can't take yet are offered and raise
  `NotImplementedRule` when chosen (plan ★7): playing a land (305.1) until M1.3 (now done) and
  casting a spell (601.2) until M2. Hiding them would silently shrink the set of legal actions an AI
  searches. A player who controls a land with a basic land type would have its intrinsic mana
  ability (305.6, 117.1d) as an option, so building that player's options raises
  `NotImplementedRule("305.6")` until M1.3. Options are listed pass first, then hand cards in
  hand order, then commanders in the command zone (903.8).
- **Decision:** cast timing (117.1a): an instant whenever the player has priority; any other
  spell type of 205.2a that is cast (artifact, battle, creature, enchantment, planeswalker,
  sorcery; kindred through its other type, 308.1) only in the player's own main phase with an
  empty stack. A land is never cast (305.9). Flash can't exist yet (no definition has
  abilities). Whether the spell's cost could be paid is part of 601.2 and isn't checked.
- **Decision:** every multiplayer game uses the attack multiple players option (plan ★6), so the
  beginning of combat has no 507.1 choice: all the active player's opponents are defending
  players (802.2). It is Commander's default multiplayer setup (903.2), and a Free-for-All game
  must use one of the attack options (806.2b). It is a deliberate non-parameter, like the
  mulligan rule.
- **Why:** a step is a value (phase and step) rather than a task per step so that later extra
  steps and phases (500.7-500.10) can be inserted into one sequence; the scenario builder can
  then resume a turn at any segment.
- **Rules:** 103.8, 500-514, 117.1-117.5, 802.2, 806.2b, 903.2, 903.8.
- **Where:** `resolve.state.turn`, `resolve.engine.turns`, `resolve.engine.priority`,
  `resolve.events.turn`.

### 2026-10-18: State-based actions 704.5a and 704.5b, and losing
- **Decision:** `state_based_actions(state)` checks every condition before anything happens,
  and `CheckStateBasedActions` applies all the results as one `ApplyEvents` (704.3), repeating
  until a check finds nothing. A loss is `PlayerLost`, which sets `Player.lost` and clears the
  player's empty-draw record. `drew_from_empty_library` is cleared only by the loss: a player
  with the flag set always loses at the next check, so "since the last time state-based actions
  were checked" (704.5b) needs no separate clearing. A player who lost has left the game
  (104.5): `players_in_game` and `next_in_turn_order` skip them.
- **Decision:** after a loss `EndCheck` ends the game when at most one player is left: that
  player wins (104.2a), and if none is left the game is a draw (104.4a). A loss that leaves two
  or more players in the game raises `NotImplementedRule("800.4a")` until M1.5 implements
  leaving the game. Because the check runs after the whole simultaneous event, two players of
  three losing together leaves one winner, not a gap.
- **Rules:** 104.2a, 104.4a, 104.5, 117.5, 121.4, 704.3, 704.5a, 704.5b, 800.4a.
- **Where:** `resolve.engine.sba`, `resolve.events.game.PlayerLost`.

### 2026-10-18: Cleanup: discarding to hand size
- **Decision:** 514.1 asks the active player `DISCARD` (a `ChooseSubset` of exactly the excess)
  when their hand holds more than seven cards. The maximum hand size is seven (402.2) whatever
  the starting hand size. When two or more cards are discarded, their owner then orders them in
  the graveyard (404.3) with `ORDER_CARDS`, listed top to bottom; a single card asks no order.
  The cards are discarded together (one `ApplyEvents` of `CardDiscarded` events, bottom card
  first). Discards are public. 514.2 has nothing to remove until damage exists (M1.4). 514.3a is
  implemented: if state-based actions would be performed in cleanup, the active player receives
  priority and another cleanup step follows. Until M1.4 the only possible state-based actions
  end the game (tested: a player at 0 life loses in that cleanup step, after the discard); the
  path where priority and a second cleanup follow is tested in M1.4.
- **Rules:** 402.2, 404.3, 514.1-514.3a, 701.9a, 701.9b.
- **Where:** `resolve.engine.turns.DiscardToHandSize`, `RunStep`.

### 2026-10-18: Characteristics without layers, and type lines
- **Decision:** `resolve.effects.characteristics.characteristics(state, obj)` is the one place
  the engine reads an object's name and types. It starts from the printed face and applies no
  continuous effects (none can exist until M5). It isn't cached: design.md §8 allows a cache,
  but invalidation bugs would be correctness bugs and nothing is slow yet. Transforming and
  modal double-faced cards use their front face (712.8a, 712.8c, 712.8d); any other multi-faced
  layout raises `NotImplementedRule("109.3")` when its characteristics are needed (split 709.4,
  flip 710.1, adventurer 715.4, meld 712.4 all have their own rules).
- **Decision:** type lines are parsed when card data is built (`CardFace.types`). An unreadable
  type line (Un-set joke types) doesn't stop the database from loading (binding change 1): the
  face's `types` is `None`, `CardData.type_line_problems` explains why, and the card is refused
  where it would be used: `DeckCard` (so `build_deck`, `new_game` and the scenario builder) and
  the coverage report (`UNREADABLE`, listed in its own section; the tool exits with 1).
  "Time Lord" is the only two-word creature type (205.3m); a plane's subtype is the whole phrase
  after the dash (205.3b). Supertypes must come before card types (205.4a).
- **Rules:** 109.3, 205, 709.4, 712.8.
- **Where:** `resolve.effects.characteristics`, `resolve.data.types`, `resolve.data.cards`,
  `resolve.cards.coverage`, `tools/coverage.py`.

### 2026-10-18: Tests for long random games
- **Decision:** the fuzz tests add `PatientAgent` (`tests/engine_support.py`): a random agent that
  passes priority 31 times in 32, so random games reach later turns (draws, discards, decking)
  instead of stopping at the first offered gap. Only some long games run the copy and invalid-answer
  checks, which are slow on long logs. The broad fuzz test
  (`test_random_agent_games_complete_with_every_check_passing`) uses decks of 8 to 11 cards, each
  with two elves (one in M1.2 to M1.4; two since M1.5, whose multiplayer games go on after a player
  leaves, to keep it fast), and one empty deck in some games: with 6 or fewer cards every player
  drew from an empty library during 103.5 and every game ended at the first state-based-action
  check, before any priority. When every deck has 8 or more cards it asserts that priority was
  asked, and it counts every object a player owns, in every zone. `ALLOWED_GAPS` was 305.1, 601.2
  and 800.4a in M1.2; M1.3 removed 305.1 and M1.5 removed 800.4a.
- **Rules:** none.
- **Where:** `tests/fuzz/test_fuzz.py`, `tools/fuzz.py`.

### 2026-10-18: Opening hands and mulligans
- **Decision:** `OpeningHands` follows 103.5 literally. Opening hands are drawn one card at a time,
  the starting player first, then the others in turn order (121.2c, 101.4e). The starting player
  declares first, then each other player in turn order (`MULLIGAN`, options `keep` and
  `mulligan`); declarations are public events (101.4b). Once all have declared, every player who
  chose to mulligan shuffles their hand into their library (one `HandShuffledIntoLibrary` event
  each, together), draws a new hand (121.2c order), and then, in APNAP order (101.4), chooses
  which cards to put on the bottom (`PUT_ON_BOTTOM`) and their order (`ORDER_CARDS`, listed
  **top to bottom**); the cards then go to the bottom together. A game "begins with more than two
  players" (100.1b, 103.5c) when it has more than two seats; seats are never removed. "A player
  can take mulligans until their opening hand would be zero cards, after which they may not take
  further mulligans" is read literally, by cards: another mulligan is allowed while the player's
  hand holds at least one card. The mulligan that leaves zero cards is allowed, and the player
  then keeps without being asked. With seven-card hands that is seven mulligans (eight with
  103.5c); a short library reaches zero cards sooner, and a player whose library was empty is
  never asked. A player who must put every card of their hand on the bottom is asked only for
  the order. Cards put on
  the bottom stay known to their owner (`known_to`) until the next shuffle. After the mulligans,
  103.6 has nothing to do (no definition can have such an ability), and the game stops at
  `NotImplementedRule("103.8: ...")` until the turn structure exists.
- **Why:** 103.5 puts the bottoming inside "to take a mulligan", so it happens each time, not when
  keeping. "After which they may not take further mulligans" places the limit after the zero-card
  hand. The first version counted mulligans against the starting hand size instead; the test
  review pointed out that the text speaks of the hand's cards, which differs for short libraries. **Questions with a single possible answer are not asked** (a forced keep, which cards go
  to the bottom when all must); priority is the exception and is always asked, because passing
  automatically is an agent's convenience (design.md §6). Commander has no mulligan rule of its
  own (the user approved removing "Commander mulligan rules" from design.md §10 and roadmap M7).
- **Rules:** 100.1a, 100.1b, 101.4, 101.4b, 101.4e, 103.5, 103.5c, 121.2c, 400.2, 400.7, 701.24a.
- **Where:** `src/resolve/engine/mulligans.py`, `src/resolve/events/cards.py`,
  `src/resolve/engine/start.py`, `tests/rules/test_103_5_mulligans.py`.

### 2026-10-18: Drawing, events logged as applied, and redacted log entries
- **Decision:** `DrawCards(player, count, rules)` makes one `CardDrawn` event per card (121.2,
  so replacement effects will apply per draw, 121.6b). An event is proposed without its outcome
  and `Event.apply` may return a copy recording it (the drawn library object, the new hand
  object); the pipeline logs that applied form. Drawing from an empty library draws nothing,
  sets `Player.drew_from_empty_library` (cleared by the state-based action check, 704.5b;
  **superseded by 2026-10-18 "State-based actions 704.5a and 704.5b, and losing"**: only the
  loss clears it) and
  adds 121.4 to the event's rules. A `LogEntry` hidden from some players may carry a `redacted`
  form (`Event.redacted()`), which `view_for` shows to the others with `visible_to=None`
  (`LogEntry.shown_to`). A draw is fully visible only to the drawer; others see the new hand
  object's ID but not the library object's. `CardsPutOnBottom` shows others only the count.
  `HandShuffledIntoLibrary` is public: it names hand objects, whose IDs everyone already sees.
  `move_object(..., bottom=True)` puts the new object at the bottom of a pile.
- **Why:** design.md §9 required log redaction to be designed with drawing: library object IDs
  survive shuffles, so revealing one tells where a card went. One entry per event with two forms
  was chosen over two separate entries so that each event keeps one index and one trigger
  check. Hand placeholder IDs are already public in views (design.md §9), so showing the new hand
  object reveals nothing more. Returning the applied event keeps events immutable values while
  letting the log say which objects were involved, which the UI and the redaction need.
- **Rules:** 121.1, 121.2, 121.4, 121.6b, 400.7, 401.2, 402.3, 704.5b; design.md §7, §9.
- **Where:** `src/resolve/events/base.py`, `src/resolve/events/pipeline.py`,
  `src/resolve/events/cards.py`, `src/resolve/engine/drawing.py`, `src/resolve/engine/view.py`,
  `src/resolve/state/game.py`, `tools/fuzz.py` (the view oracle shows redacted forms and fails if
  a redacted draw or bottoming still names cards).

### 2026-10-18: Windows first: the CI matrix and the encoding checks
- **Decision:** CI runs ruff, pyright and pytest on `windows-latest` and `ubuntu-latest` with
  Python 3.12, 3.13 and 3.14 (supersedes the CI part of "Tooling: uv lockfile, pyright from a
  wheel, CI on two Pythons"). Every text file is opened with an explicit encoding, UTF-8 unless
  there is a reason. Two checks enforce it: `tests/tooling/test_portability_lint.py` scans
  `src`, `tools` and `tests` for text I/O without an encoding (also shell-string subprocesses,
  POSIX-only modules and calls, and `/tmp`), and CI sets `PYTHONWARNDEFAULTENCODING=1` while
  `pyproject.toml` turns `EncodingWarning` into a test failure. There is no `.gitattributes`:
  code must read `\r\n` and `\n` alike, and tests feed it `\r\n` explicitly.
- **Why:** Python 3.12 to 3.14 on Windows default to the ANSI code page (cp1252) for files and
  redirected output; UTF-8 becomes the default only in 3.15 (PEP 686). PR #11's Windows jobs
  failed exactly this way: a test wrote the rules README with `write_text()` and no encoding
  (`©` became byte 0xa9) and the tool read it as UTF-8. The scan runs on every platform and
  every local `uv run pytest`; the warning catches calls a scan can't see. Running in UTF-8 mode
  (`PYTHONUTF8=1`) was rejected: it would hide the bug from CI while players, who don't run in
  that mode, still hit it. Ruff's `PLW1514` was rejected: it is preview-only and found none of
  the 15 offending calls (it can't tell that `readme` is a `Path`).
- **Where:** `.github/workflows/ci.yml`, `pyproject.toml`, `tests/tooling/test_portability_lint.py`.

### 2026-10-18: Tools write UTF-8 output and LF files
- **Decision:** each tool's `__main__` block reconfigures `sys.stdout` to UTF-8 before calling
  `main()`. `tools/fetch_scryfall.py` writes the rules README and `snapshot.json` with
  `newline="\n"`. Standard input and standard error are left alone.
- **Why:** output redirected to a file or pipe on Windows is encoded as cp1252, which has no
  `−` (U+2212, the minus sign of planeswalker abilities) and nothing outside Western European
  scripts; `coverage.py --oracle > report.txt` crashed halfway. A console already gets UTF-8
  (PEP 528), so this changes only redirected output, and matches what Python 3.15 will do.
  `errors="replace"` was rejected because it silently changes the text. The README is tracked
  by git, so the tool writes the same bytes on every platform. Standard error already escapes
  what it can't encode (`backslashreplace`), and the terminal player's input is ASCII.
- **Where:** `tools/*.py`, `tests/tooling/test_tool_output_encoding.py` (probes every tool),
  `tests/tooling/test_coverage_tool.py`, `tests/tooling/test_fetch_scryfall_tool.py`.

### 2026-10-18: Decklist and source file encodings
- **Decision:** `load_decklist` reads UTF-8, with or without a byte order mark, and UTF-16 with
  a byte order mark. Anything else is a `DecklistError` naming the file. `tools/gaps.py` parses
  source files from their bytes, so it decodes them as Python does (BOM, PEP 263 declarations).
- **Why:** these are what Windows editors and shells write: Notepad and PowerShell 5.1's
  `Out-File -Encoding utf8` add a UTF-8 byte order mark, and PowerShell 5.1's `>` writes UTF-16.
  Before, a BOM made the first line unreadable and UTF-16 crashed with a `UnicodeDecodeError`.
  A file saved as "ANSI" is refused rather than guessed at: the same bytes are different card
  names in different code pages (non-negotiable rule 1: accuracy over convenience).
- **Where:** `src/resolve/data/decklist.py`, `tools/gaps.py`.

### 2026-10-18: The fuzz harness
- **Decision:** the harness is `tools/fuzz.py` (`fuzz_run`, `fuzz_game`, `state_problems`,
  `invalid_answers`), tested and used by `tests/fuzz/test_fuzz.py` (imported as `tools.fuzz`,
  like `tools.coverage`). Before every answer it checks invariants, purity, and every player's
  view against an oracle written out from the rules, not from the engine's `is_known_to`:
  immutable; the request only in the decider's view; life, library counts (401.2), the objects
  of every hand, graveyard and shared zone in order (402.3, 404.2); card names exactly where
  the viewer may know them (400.2, 402.3, 404.2, 406.3); and exactly the log entries visible to
  the viewer, with answers visible only to their player. It checks that `deepcopy` and `pickle`
  give equal states, and that answers for another request or from another player (carrying the
  agent's own, valid value, so only the id or player is wrong), of the wrong type or outside
  the space are rejected without changing anything. It then submits the random answer to the state, a deep
  copy and a pickled copy, which must end the same way and in equal states. A rejected random
  answer must change nothing, and the agent answers again; 100 rejections in a row
  (`MAX_ATTEMPTS`) or 10,000 accepted answers (`MAX_ANSWERS`) are failures. At the end the game
  is replayed from its start with `ScriptedAgent.from_log` and must reproduce the identical
  state. `NotImplementedRule` ends a game only for a rule in `allowed_gaps` (default `("103.5",)`,
  the end of an M0 game); any other exception is a `FuzzFailure` naming the seed and a command
  that reproduces it. Seat `i` is played by `RandomAgent(seed + i)`. The command line cycles
  player counts 2-6 and both formats, gives seat `i` of game seed `s` deck
  `(s + i) % len(decks)` so a failure reproduces from its seed alone, and prints games per
  second; the number isn't stored anywhere yet. Every check relies on `==` between states, so
  `tests/state/test_state_equality.py` forbids `compare=False` fields, `eq=False`
  dataclasses and hand-written `__eq__` methods in the engine; and a test replays a game in two processes with different
  `PYTHONHASHSEED`s and requires byte-identical pickles (CLAUDE.md rule 6).
- **Why:** design.md §14 and the roadmap. The harness lives in `tools/` because rule 4 keeps
  agent-using code out of the engine and tools can't import `tests/`. Submitting to copies at
  every decision tests the strongest form of design.md §5 (a state copied mid-task resumes
  exactly as the original) at little cost. Each check has a negative test built from a broken
  test-only task (`tests/engine_support.py`), so a check that silently stops working is noticed.
  The CLI defaults to empty decks because no card is implemented and tools never invent cards
  (**superseded by 2026-10-19** "Basic-land decks, presets and the summary of the fuzz command
  line": basic-land decks from a copied excerpt).
  Widen `ALLOWED_GAPS` deliberately as milestones change where games stop.
- **Rules:** 400.2, 401.2, 402.3, 404.2, 406.3; design.md §5, §6, §7, §9, §12.
- **Where:** `tools/fuzz.py`, `tests/fuzz/test_fuzz.py`, `tests/engine_support.py`.

### 2026-10-18: The text interface and `tools/play_cli.py`
- **Decision:** the renderer (`render_view`, `render_request`, `render_log_entry`), the answer
  parser (`parse_answer`) and the CLI agent (`TextAgent`) are in `resolve.agents.text`;
  `tools/play_cli.py` only parses arguments, builds decks and runs `play`. Options are numbered
  from 0, matching `Pick` indices. The parser checks only the shape of what was typed (out-of-range
  numbers go to the engine, which rejects them, and the driver asks again). Each human seat
  sees its own view, so hot-seat play doesn't leak hands; for the same reason the final view is
  printed only when a single seat is human (player 0's when every seat is random), and hot-seat
  games end with just the result. Without `--deck` every player gets an
  empty deck; with `--deck`, decks come from the snapshot and must be fully implemented. Exit
  statuses: 0 game over, 1 couldn't start, 2 bad arguments, 3 stopped at a `NotImplementedRule`,
  4 quit.
- **Why:** the renderer is useful outside the CLI (debugging, failure messages), and keeping it
  in the agents package keeps it on the agent side of rule 4. Zero-based numbering keeps the CLI
  and the log saying the same thing. Empty decks are the only decks that need no card
  implementation, and decks are never approximated.
- **Where:** `src/resolve/agents/text.py`, `tools/play_cli.py`.

### 2026-10-18: The scenario builder in M0
- **Decision:** `tests/scenario.py`'s `Scenario` starts from `initial_state` with empty decks and
  creates objects immediately, so every call returns real `ObjectId`s and IDs and timestamps
  follow call order. It sets player count, config, seed, starting player (default 0; `None` for
  "not chosen yet"), life (any integer), cards in every zone, `known_to` and commanders (in any
  zone, only with the Commander rules). Piles (library, graveyard, stack) are listed **top
  first**, and a later call puts its cards on top. A card in another player's library, hand or
  graveyard is refused rather than redirected (400.3); a controller is required exactly on the
  battlefield and the stack. A failed `add` leaves the scenario unchanged. `build(*tasks)` checks
  invariants and purity and runs the given tasks to their first decision. Turn, step, phase and
  priority holder are added with the turn structure in M1. Like `new_game`, the builder doesn't
  check whether a card may be a commander (legendary, partner for a second one: 903.3, 903.5,
  702.124a); that is deck validation in M7. The test review suggested refusing such commanders;
  it was kept consistent with `new_game` instead, and a second commander reaches the existing
  613.7m gap when the game starts. `run_script(state, *steps)` plays a
  script and requires every step to be used; `names(state, zone)` lists a zone's card names.
- **Why:** design.md §14. Building through the engine's own `create_object` keeps scenario
  states identical in shape to played ones. Top-first lists read like "the top card is X".
  Refusing an impossible placement catches test mistakes that a redirect would hide. The builder
  can't set what the engine doesn't model yet.
- **Rules:** 103.1, 108.4, 110.2, 119, 400.2, 400.3, 401.2, 405.2, 613.7d, 702.124a, 903.3,
  903.5.
- **Where:** `tests/scenario.py`, `tests/engine/test_scenario_builder.py`.

### 2026-10-18: Agents, the driver and replays
- **Decision:** `resolve.agents` holds the `Agent` protocol (`decide(view, request) ->
  DecisionAnswer`), the driver `play(state, agents, max_answers=None, on_invalid=None)`,
  `RandomAgent` and `ScriptedAgent`. `play` takes one agent for every player or one per seat.
  A rejected answer raises `InvalidAnswer` unless `on_invalid` is given; then the same agent is
  asked again, up to 100 times per decision. `RandomAgent` uses its own `Rng` (the engine's
  generator) and is uniform over each space's answers: over options, over subset sizes and then
  subsets of that size, over permutations, over numbers, and over divisions (stars and bars). An
  unbounded `ChooseNumber` is capped at `minimum + 20` (`unbounded_span`). A script is a list of
  `Step(value)` or `Choose(options)` (resolved against the space, so a test needn't know option
  indices), each optionally naming the expected player and kind; a mismatch or running out raises
  `ScriptError`. A replay is `ScriptedAgent.from_log(state.event_log)`: the recorded answers with
  their players and kinds, played from the same config, decks and seed. The save-file format with
  engine, CR and data versions (design.md §12) is not built yet. The determinism lint scans
  `resolve.agents`.
- **Why:** design.md §3 already defines the driver loop and the `decide` interface. Uniform
  answers explore every kind of answer, including the extremes. Replaying through the same
  agent interface means a replay checks itself: a step whose player or kind no longer matches
  stops the replay at the first divergence. Rejected answers aren't logged, so replays contain
  only accepted ones.
- **Rules:** 101.4; design.md §3, §6, §12.
- **Where:** `src/resolve/agents/`, `tests/agents/`, `tests/state/test_determinism_lint.py`.

### 2026-10-18: Every CR citation in the engine must exist in the pinned rules
- **Decision:** `tests/tooling/test_rule_citations.py` collects every CR number the engine cites
  and checks it against the section, rule and subrule numbers parsed from
  `docs/rules/MagicCompRules-20260925.txt`. It collects them statically (string constants passed
  as `rules=`, every `NotImplementedRule` message via `tools/gaps.py`, and every dotted number such
  as `613.7m` anywhere in the source text of `src/resolve`, comments and docstrings included) and
  at run time (the rules of every log entry and request of a played game). Citations have one
  format, checked when events and requests are built (`resolve.citations`): `"103"`, `"103.1"` or
  `"701.24a"`, one rule per string.
- **Why:** the user asked for it. Citations are how readers check the engine against the CR; a
  mistyped or renumbered rule would otherwise go unnoticed until someone looked it up. Bare
  three-digit section numbers in prose aren't scanned (too many false positives such as "100
  cards"), but structured citations may be sections.
- **Rules:** CLAUDE.md rules 2 and 3.
- **Where:** `src/resolve/citations.py`, `tests/tooling/test_rule_citations.py`.

### 2026-10-18: Immutable values are shared between copies of a state
- **Decision:** value types derive from `resolve.values.Immutable`, whose `__copy__` and
  `__deepcopy__` return the object itself: `CardData`, `CardFace`, `CardDefinition`, `Card`,
  `Zone`, `GameConfig`, events, log entries, requests, answer spaces, options, answers, decks and
  player views. Each must be a frozen dataclass whose fields hold only scalars, enums, tuples and
  other `Immutable` values. `tests/state/test_immutability.py` checks every subclass from its type
  hints (so field annotations must be resolvable at run time, not imported only under
  `TYPE_CHECKING`), and `resolve.state.invariants.mutable_parts` checks actual values. `CardData`
  holds no rulings: they stay in `CardDatabase`, for writing tests.
- **Why:** the user asked for it. Under design.md decision A the state holds every card's data and
  definitions; copying them on every clone would make AI search pay for Oracle text that never
  changes. Sharing is only safe for deeply immutable values, hence the test. Frozen dataclasses
  don't check types at run time, so the value check also exists (a list passed where a tuple is
  annotated would otherwise be shared and mutable).
- **Where:** `src/resolve/values.py`, `src/resolve/data/cards.py`, `src/resolve/cards/registry.py`,
  `src/resolve/state/invariants.py`.

### 2026-10-18: Starting the game in M0
- **Decision:** `initial_state` creates every card's object in its owner's library (commanders
  first, then deck order), which stands for the player's deck before 103.3: hidden and unshuffled.
  It records each player's commanders (`Player.commanders`, 903.3) and sets life from the config
  (103.4). `CardId`s and setup timestamps follow seat order, commanders first, then deck order.
  `StartGame` then:
  1. picks the player who chooses the starting player uniformly with the game's RNG and asks them
     (`CHOOSE_STARTING_PLAYER`; every player is an option, the chooser included) (103.1);
  2. in a Commander game, puts every commander into the command zone with one set of simultaneous
     `CommanderPutIntoCommandZone` events in turn order from the starting player (103.2c, 903.6).
     Each commander becomes a new object (400.7) whose timestamp follows APNAP order (613.7m,
     with the starting player as active player, 101.4e). A player with several commanders
     (partners) raises `NotImplementedRule("613.7m: ...")`, because that player chooses the
     order among their own;
  3. shuffles each library in turn order (103.3);
  4. stops at `NotImplementedRule("103.5: ...")`.

  The opponents' optional extra shuffle or cut (103.3) is left out. Matches aren't modeled:
  `new_game` is one game, so 103.1's "loser of the previous game chooses" belongs to whoever runs a
  match.
- **Why:** 103.2 puts 103.2c after the starting player is determined, so the chooser must not see
  the other players' commanders yet. The test review caught that an earlier version of this branch
  put them in the command zone at setup. 103.1 leaves the method of picking the chooser to the
  players; a uniform random pick is such a method and keeps the game a function of its seed. A
  uniformly random library stays uniformly random after any further shuffle or cut, so offering
  that choice would add a decision with no effect. The setup timestamps aren't ordered by
  613.7m: there is no starting player yet, and nothing can observe the relative timestamps of
  cards in a library before they next change zone. The `CommanderPutIntoCommandZone` log entries
  show the commanders' old library IDs to everyone; that reveals nothing, because the commander
  is leaving and the rest of the library is shuffled next.
- **Rules:** 101.4e, 103.1-103.5, 400.7, 613.7d, 613.7m, 701.24a, 903.3, 903.6, 903.7.
- **Where:** `src/resolve/engine/setup.py`, `src/resolve/engine/start.py`,
  `src/resolve/events/game.py`.

### 2026-10-18: Moving objects between zones
- **Decision:** `resolve.state.game.move_object` implements 400.7:
  - The object is removed, and a new object with a new ID and timestamp is created on top of the
    destination.
  - A move from the command zone into the command zone also makes a new object (400.10).
  - An object sent to another player's library, hand or graveyard goes to its owner's instead
    (400.3); `create_object` applies the same redirect.
  - The destination is checked before anything changes: a controller must be given exactly for
    the battlefield and the stack (109.4, 110.2).
  - A controlled object in the command zone (an emblem, 109.4c) raises `NotImplementedRule`.
  - No knowledge carries over to the new object. An event that moves a card whose identity
    players saw (a revealed card put back on top of a library, 701.20) records that on the new
    object itself; that arrives in M1.
  - Only events call `move_object`. Last-known information and the other 400.7 exceptions arrive
    with the milestones that need them (M1, M4).
- **Why:** 400.3 is a redirect, not a prohibition: "put it into your hand" on a card you don't own
  is legal and sends it to its owner's hand. The test review caught that an earlier version
  raised `EngineError` instead. Keeping knowledge decisions in the event that knows what players
  saw keeps the primitive simple and correct by default (400.7: "no memory of ... its previous
  existence").
- **Rules:** 109.4, 109.4c, 110.2, 400.3, 400.7, 400.10, 613.7d, 701.20.
- **Where:** `src/resolve/state/game.py`.

### 2026-10-18: Identifiers, seating and pile order
- **Decision:** `PlayerId`, `ObjectId` and `CardId` are `NewType` ints. `PlayerId` is the seat
  index and `players` is in seating order (deck `i` is player `i`); turn order is computed from
  `starting_player` (`turn_order`). `ObjectId`s and `CardId`s start at 1 and are never reused. In
  every pile (library, graveyard, stack) the last list element is the top; hand, battlefield,
  exile and command lists keep arrival order. Objects without a controller have
  `controller=None`; 108.4a's "use the owner" is for whoever asks.
- **Why:** ints pickle, compare and hash cheaply and deterministically; `NewType` keeps them
  apart for pyright. Seat indices stay valid when players leave (800.4). One orientation for all
  piles avoids a class of top/bottom bugs.
- **Rules:** 103.1, 108.4, 109.4, 400.5, 400.7, 404.1, 405.2.
- **Where:** `src/resolve/state/ids.py`, `src/resolve/state/game.py`, `src/resolve/state/zones.py`.

### 2026-10-18: Answer validation and canonical answers
- **Decision:** an answer is checked in two stages, neither of which changes the state: the
  request's id and player and its answer space (`validate_answer`), then the asking task's
  `check_answer`. Each outcome has exactly one valid answer: subsets are strictly increasing
  indices, orders are permutations, distributions are one amount per recipient. Booleans are not
  accepted as integers. A space that can't be answered (no options, impossible bounds) raises
  `ValueError` when built, as an engine bug. `DecisionKind` lists the vocabulary of design.md §6;
  only `CHOOSE_STARTING_PLAYER` is asked in M0.
- **Why:** rejecting before changing anything lets an agent (or a network peer) retry, and makes
  "the state is unchanged" testable by comparing with a copy. Canonical answers mean equal
  answers have equal meaning, which AI search and replays rely on.
- **Rules:** 101.4, 601.2d, 107.3a.
- **Where:** `src/resolve/decisions/`, `src/resolve/engine/loop.py`.

### 2026-10-18: The engine loop, errors and the state after an error
- **Decision:** the task base class lives in `resolve.tasks` (top level), not `resolve.engine`,
  because events use it and `resolve.engine` imports the events. The loop raises `EngineError` if
  a task changes `state.tasks` itself, if the stack empties during a game, or after
  `MAX_TASKS_PER_RUN` (one million) tasks without a decision. `submit` isn't transactional: after
  `NotImplementedRule` or `EngineError` the state stays as it was when the error was raised, isn't
  waiting for anything, and must not be played on (`pending_decision` raises `EngineError`).
- **Why:** a rollback would mean copying the state on every `submit`, which AI search can't
  afford. The runaway budget only catches engine bugs; mandatory game loops are 104.4b (M7).
- **Where:** `src/resolve/tasks.py`, `src/resolve/engine/loop.py`, `src/resolve/errors.py`.

### 2026-10-18: The event log records answers and who may see each entry
- **Decision:** a `LogEntry` holds an event or an `AnswerRecord`, its index and its visibility
  (`None` for everyone, or sorted player IDs). Answers are visible only to the player who gave
  them; whatever they make public is logged as events. An event's visibility is judged before it
  is applied. Views include the entries their player may see. Views show printed card names until
  the layer system exists (M5); an object without a card in a view raises
  `NotImplementedRule("111.1: ...")`, since tokens don't exist yet.
- **Why:** replays are rebuilt from the answers (design.md §12), and some answers are secret
  (cards put on the bottom after a mulligan, 103.5). How zone-change entries are redacted for
  other players is decided in M1, when cards are drawn.
- **Rules:** 101.4, 103.5, 111.1.
- **Where:** `src/resolve/events/base.py`, `src/resolve/engine/view.py`.

### 2026-10-18: Deck construction isn't checked until M7
- **Decision:** `new_game` checks only that there are at least two decks (100.1), that every card
  has a definition for each face (`DeckCard`), and that commanders are given only with the
  Commander rules. Deck size, singleton, color identity and "has a commander" (100.2a, 903.3,
  903.5) are left to `validate_deck` in M7.
- **Why:** deck legality is a pre-game check, not a game rule, and the decision to move the
  deck-construction settings out of `GameConfig` until they're enforced was approved with
  design.md §10. Tests and the scenario builder need small, illegal decks anyway.
- **Rules:** 100.1, 100.2a, 903.3, 903.5.
- **Where:** `src/resolve/engine/deck.py`, `src/resolve/engine/setup.py`.

### 2026-10-18: Purity, determinism and gap tooling
- **Decision:** `resolve.state.invariants.state_impurities` accepts scalars, enums, lists, tuples,
  dicts with int/str/enum keys and any dataclass instance whose fields are pure (and that has no
  attributes besides its fields, so test-only tasks qualify); it also rejects a `GameObject` or
  `Player` held outside `state.objects`/`state.players`. `tests/state/test_determinism_lint.py`
  scans the engine packages for imports of `time`, `datetime`, `random`, `uuid`, `secrets`, `os`
  and `threading` and calls to `id()` and `hash()`. `tools/gaps.py` lists every
  `NotImplementedRule` by AST and fails on any whose message isn't a literal starting with a CR
  number.
- **Why:** CLAUDE.md rules 1, 5 and 6, enforced by tools rather than by review. Set iteration
  can't be found by a scan, so sets are kept out of the state instead.
- **Where:** `src/resolve/state/invariants.py`, `tests/state/`, `tools/gaps.py`.

### 2026-10-18: Engine test layout and helpers
- **Decision:** engine infrastructure tests live in `tests/state/`, `tests/engine/`,
  `tests/decisions/` and `tests/events/`; rules tests in `tests/rules/` as before.
  `tests/game_fixtures.py` builds decks from the Scryfall fixtures with test-only definitions and
  starts games. `tests/engine_support.py` holds test-only tasks and a `Marker` event, in an
  importable module so that states holding them can be pickled; `running(*tasks)` starts a game
  with those tasks above a `Hold` task that keeps the game waiting once they finish.
- **Why:** the scenario builder (later in M0) will replace most of the fixtures, but the loop
  needs tasks that exercise every result type before any real turn structure exists.
- **Where:** `tests/`.

### 2026-10-18: Test layout and Scryfall fixtures
- **Decision:** Infrastructure tests live in `tests/data/` (card data, decklists),
  `tests/registry/` (registry, deck coverage) and `tests/tooling/` (the `tools/` scripts). No test
  reads `data/` or the network. Tests that need card data use `tests/scryfall_fixtures.py`:
  hand-written records in Scryfall's bulk format, a few real cards (Llanowar Elves, Forest) plus
  invented cards whose names start with "Test" for edge cases, and placeholder rulings that are
  not real rulings. Fixture bulk files are gzipped with `mtime=0` so their bytes are reproducible.
  `tests/` has no `__init__.py`, so pytest imports test files by basename and basenames must be
  unique across folders (hence `test_coverage_tool.py` vs `test_deck_coverage.py`). pytest's
  `pythonpath = ["."]` makes the repo root importable, so tests import `tests.scryfall_fixtures`
  and the tools as `tools.coverage` (`tools/` is a package).
- **Why:** the real snapshot is large, gitignored and absent in CI, and a test must not change
  meaning when the snapshot changes. Invented names make it obvious which data is real. The
  fixtures once encoded a wrong assumption about Scryfall's format (plain JSON arrays) and the
  tests passed anyway; when the external format matters, check the fixtures against a real
  download.
- **Where:** `tests/`, `tests/scryfall_fixtures.py`, `tools/__init__.py`, `pyproject.toml`.

### 2026-10-18: Card registry: per-face definitions collected from `DEFINITIONS`
- **Decision:** `CardDefinition` holds only `name` for now; behavior fields arrive with the
  primitives. Definitions are registered under the exact Oracle name of each face, so a
  multi-faced card is implemented only when every face has a definition (registering
  `"Front // Back"` doesn't count). Each module in `resolve.cards.definitions` exports a
  `DEFINITIONS` sequence; `default_registry()` imports the modules in sorted name order and
  registers them. Registering a name twice is an error.
- **Why:** design.md §11 registers multi-faced cards per face. Collecting explicit lists instead
  of registering on import keeps the registry free of global state, so tests build their own
  registries, and sorted order keeps it deterministic. The coverage logic lives in the package
  (`resolve.cards.coverage`) rather than only in the tool, so `new_game` can reuse it to refuse
  unimplemented decks.
- **Rules:** 709 (split), 710 (flip), 712 (double-faced), 715 (adventurer), 722 (preparation).
- **Where:** `src/resolve/cards/registry.py`, `src/resolve/cards/coverage.py`.

### 2026-10-18: Card name matching is exact; ambiguous names are refused
- **Decision:** `CardDatabase.get` matches names exactly and case-sensitively. A multi-faced card
  can also be found by its front face's name, but never by a back face's name, and a card's full
  name always wins over another card's front-face alias. Objects that can't be in a deck
  (`NON_DECK_LAYOUTS`: tokens, emblems, art series, Jumpstart `front_card`s, `reversible_card`
  reprints, Planechase, Archenemy and Vanguard cards) are left out of the index. A name still
  shared by several cards raises `AmbiguousCardNameError`; a deck naming it is reported as
  "unknown".
- **Why:** decks are refused rather than approximated (CLAUDE.md), so near-matches are errors.
  Decklists usually name double-faced cards by their front face. Tokens share names with each
  other, and front cards and reversible cards share names with real cards (Savage Lands,
  Inferno). In the 2026-10-17 snapshot, 38 names remain ambiguous, all Un-set or playtest
  variants (for example Red Herring); none are in the target decks. If one is ever needed, prefer
  a deliberate rule (such as ignoring `set_type == "funny"`) over guessing.
- **Rules:** 201.2 (English names). Interchangeable names (201.3) are not treated as equal; that
  only matters for deck construction (903.5b) and belongs to deck validation (M7).
- **Where:** `src/resolve/data/cards.py` (`CardDatabase`, `NON_DECK_LAYOUTS`).

### 2026-10-18: Card data representation
- **Decision:** `CardData.faces` always has at least one `CardFace`; single-faced cards get one
  face built from the card's own fields. Faces without `colors` (split and adventurer cards) take
  the card's colors. Power, toughness, loyalty and defense are strings or `None`. `mana_value`
  is a float. Scryfall's `keywords` list is kept for reports only.
- **Why:** one shape for every card avoids special cases. Values like `*` and `1+*` (208.2)
  aren't numbers, and Scryfall reports fractional mana values for a few Un-cards. Card behavior
  must come from definitions built from primitives, never from Scryfall's keyword tags, which
  also include ability words and keyword actions.
- **Rules:** 109.3, 202.3, 208.2, 903.4.
- **Where:** `src/resolve/data/cards.py`.

### 2026-10-18: Decklist format and parsing rules
- **Decision:** a decklist has `Commander`, `Mainboard` and `Sideboard` sections; headers are
  matched case-insensitively and each may appear once. Card lines are `<count> <exact name>` with
  a positive integer count (`1x Name` is rejected). Every card line must follow a header. `#`
  starts a comment only at the beginning of a line, so `#` inside a name is kept. A card repeated
  within one section has its counts added. Errors give `deck:line`. Names are kept exactly as
  written. The parser does no deck validation.
- **Why:** strict parsing turns typos into errors instead of guesses. Deck legality (100 cards,
  singleton, color identity) belongs to deck validation in M7. The sideboard is out of scope for
  coverage (roadmap) and is only checked with `--include-sideboard`.
- **Rules:** 100.4 (sideboards), 903.3 (commander), 903.5a–c (Commander deck construction, not
  enforced here).
- **Where:** `src/resolve/data/decklist.py`, `decks/`.

### 2026-10-18: Snapshot drift on new machines is accepted
- **Decision:** a fresh checkout fetches Scryfall's current snapshot, not the pinned one. The
  fetch tool then rewrites the pinned date in `docs/rules/README.md` and adds a changelog row;
  the developer commits that to move the pin, or reverts it with
  `git checkout docs/rules/README.md`.
- **Why:** Scryfall serves only its current bulk files, so the pinned files can't be
  re-downloaded. The change shows up in `git diff`, and Oracle text rarely changes between
  snapshots. The user chose this over adding a strict date check or hosting a copy of the files.
- **Where:** `tools/fetch_scryfall.py`, `data/README.md`, `docs/rules/README.md`.

### 2026-10-18: Snapshot manifest and checksum checks
- **Decision:** `data/snapshot.json` records, for each bulk file, its publication time
  (`updated_at`), source, size and SHA-256. `load_card_database` refuses files whose SHA-256
  doesn't match (`verify=False` skips the check). The fetch tool downloads to `*.part` files and
  checks that each parses as the right bulk type before replacing anything; the Oracle-cards file
  must list each Oracle ID once, which tells it apart from Scryfall's other card files. The
  manifest is written last. An existing snapshot is replaced only with `--update`. Files
  downloaded by hand go in with `--import-files`, which reads the publication time from
  Scryfall's file names (`oracle-cards-YYYYMMDDHHMMSS.jsonl.gz`) or from `--updated-at`.
  The snapshot's date is the UTC date of the Oracle-cards file.
- **Why:** design.md §2 pins card data so a test never silently changes meaning; checksums catch
  edited, truncated or swapped files. The manual import exists because cloud sessions may not be
  allowed to reach Scryfall (`api.scryfall.com` and `data.scryfall.io` must be allowed in the
  environment's network settings).
- **Where:** `src/resolve/data/cards.py` (`SnapshotInfo`, `BulkFileInfo`,
  `load_card_database`), `tools/fetch_scryfall.py`.

### 2026-10-18: Scryfall bulk data is stored as gzipped JSON Lines
- **Decision:** the fetch tool downloads each entry's `jsonl_download_uri` and stores the file
  unchanged, as `data/oracle-cards.jsonl.gz` and `data/rulings.jsonl.gz`. The loader reads them
  line by line (`read_jsonl_gz`).
- **Why:** Scryfall's bulk-data index offers only gzip-compressed JSON Lines; the plain-JSON
  `download_uri` is gone. Keeping the file as served keeps it small (about 25 MB instead of over
  100 MB) and makes its SHA-256 the checksum of exactly what Scryfall published.
- **Where:** `src/resolve/data/cards.py`, `tools/fetch_scryfall.py`.

### 2026-10-18: Tooling: uv lockfile, pyright from a wheel, CI on two Pythons
**Superseded by 2026-10-18 (Windows first: the CI matrix and the encoding checks)** for the CI
matrix; the lockfile and pyright parts stand.
- **Decision:** `uv.lock` is committed and CI runs `uv sync --locked`, so a stale lockfile fails
  CI. Pyright is installed as `pyright[nodejs]`, which ships Node as a wheel. CI runs
  `ruff check`, `ruff format --check`, `pyright` (strict) and `pytest` on Python 3.12 (the
  minimum) and 3.13. The engine has no runtime dependencies; the fetch tool uses only the
  standard library (`urllib`).
- **Why:** plain `pyright` downloads Node at run time when none is installed, which can fail
  on restricted networks. Testing the minimum and a current version catches version-specific breakage.
- **Where:** `pyproject.toml`, `uv.lock`, `.github/workflows/ci.yml`.

### 2026-10-19: Tooling: updating the pinned CR and card data
- **Decision:**
  - `tools/rules_diff.py` matches rules by number, then pairs old and new rules under different
    numbers when their word-level similarity is at least 0.8 and beats the old rule's similarity
    to whatever now has its number (best pairs first, each rule once). Within a section any
    leftover pair is a candidate, so a subrule inserted mid-list is reported as renumbered
    rules plus one added rule; across sections only removed numbers match added numbers.
    Unnumbered paragraphs belong to the rule before them; the glossary is not compared.
  - Citations are matched by exact number, in `.py` files and in documents (`docs/**/*.md`
    except `docs/rules/`, `.claude/agents/*.md`), and separately for the parent of a flagged
    subrule. `704.5a/b` cites both rules.
  - A subrule has one or two letters (704.5z is followed by 704.5aa), so `is_rule_reference`
    accepts `"103.1ab"`; the old test listing it as invalid was wrong for the CR (it is now
    `"103.1abc"`). The grammar, sort key and parsing live in `resolve.citations` and
    `resolve.data.rules_text`; the tools and the citation test use them.
  - `tools/card_diff.py` compares the cards that have definitions plus every card in `decks/`
    (sideboards included), by Oracle ID when a card was renamed. The citation test scans `src/`,
    `tools/` and `tests/`, except a short list of files that cite invented numbers as test data.
- **Why:** CLAUDE.md rules 2 and 3: a CR update must be routine and loud, never silent drift.
- **Where:** `tools/rules_diff.py`, `tools/card_diff.py`, `src/resolve/citations.py`,
  `src/resolve/data/rules_text.py`, `tests/tooling/test_rule_citations.py`.
