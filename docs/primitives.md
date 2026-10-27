# Primitives catalog

Every building block available for writing card definitions: effects, targets and filters,
triggers, conditions, costs, durations, static abilities, replacement effects and keywords.

**Before writing a new primitive, search this file.** Reuse or extend an existing primitive rather
than adding a near-duplicate under another name. Every new or changed primitive is recorded here in
the same PR (CLAUDE.md, "Documentation requirements").

## Entry format

```markdown
### `PrimitiveName` (`resolve.cards.primitives.module`)
What it does, in one line.
- **Rules:** CR numbers it implements.
- **Parameters:** the important ones, briefly.
- **Example:** a card that uses it, with the relevant line of its definition.
```

---

## Abilities

### `Ability` (`resolve.cards.primitives.base`)
The base class of every ability a definition lists; it has a `text`.
- **Rules:** 113.
- **Example:** see `ActivatedManaAbility`.

### `ActivatedManaAbility` (`resolve.cards.primitives.abilities`)
An activated mana ability: pay `cost`, then `effect` adds mana; it doesn't use the stack.
- **Rules:** 605.1a, 605.3a, 605.3b, 605.3c, 602.2 (only the controller activates), 602.2b,
  602.5, 118.3.
- **Parameters:** `cost: tuple[Cost, ...]` (at most one `ManaPaymentCost`), `effect: AddMana |
  AddManaOfAnyColor`, `activate_only_if: ControlsAtLeast | None`. `mana_cost` gives the mana
  part, if any.
- **Example:** Sol Ring (`resolve.cards.definitions.mana_rocks`):
  `ActivatedManaAbility((TapSelfCost(),), AddMana((ManaType.COLORLESS, ManaType.COLORLESS)))`.
  It can be activated while its controller pays a cost (601.2g, `resolve.engine.payment`).
  Selesnya Signet: `ActivatedManaAbility((ManaPaymentCost(parse_mana_cost("{1}")),
  TapSelfCost()), AddMana((ManaType.GREEN, ManaType.WHITE)))`. Temple of the False God:
  `ActivatedManaAbility((TapSelfCost(),), AddMana((C, C)), activate_only_if=ControlsAtLeast(5,
  CardType.LAND))`. `resolve.engine.mana.ActivateManaAbility` runs it.

### `intrinsic_mana_ability(land_type)` (`resolve.cards.primitives.abilities`)
The "{T}: Add [mana symbol]" a land has for each basic land type. Never put it in a definition:
`characteristics` adds it to every land with the type.
- **Rules:** 305.6.
- **Example:** Forest (`resolve.cards.definitions.basic_lands`), whose definition has no
  abilities.

### `SpellAbility`, `Mode`, `ModeChoice` (`resolve.cards.primitives.spells`)
An instant's or sorcery's spell ability, in `CardDefinition.spell`: one `Mode` (its instances of
"target" and its effects, in the order written) or, for a modal spell, several with a
`ModeChoice`. The engine reads it as `characteristics(...).spell_ability`. `text` is written from
the primitives (a modal spell's: the instruction to choose, then a bulleted line per mode).
`ModeChoice.combinations(legal)` lists every choice of modes among the legal ones (700.2a), each
once, its modes in printed order with a repeated mode listed that many times (700.2d; a minimum
of 0 is a 700.2 gap);
`SpellAbility.chosen(modes)` gives the modes a record's `modes` follow (its one mode if it isn't
modal), `instances(modes)` their instances of "target" in turn (601.2c, 700.2c).
- **Rules:** 113.3a, 115.1a, 601.2b, 601.2c, 608.2c; 700.2, 700.2a, 700.2c, 700.2d
  (`ModeChoice(minimum, maximum, repeatable)`).
- **Parameters:** `Mode(targets: tuple[TargetSpec, ...], effects: tuple[Effect, ...], cost=None)`
  (`cost`: room for spree); `SpellAbility(modes, choose: ModeChoice | None = None)`.
- **Examples:** Swords to Plowshares (`resolve.cards.definitions.removal`):
  `SpellAbility((Mode((target(CardType.CREATURE),), (Exile((TargetRef(0),)),
  GainLife(ControllerOf(TargetRef(0)), PowerOf(TargetRef(0))))),))`. Fiery Confluence (same
  module): three modes and `ModeChoice(3, 3, repeatable=True)`; `TargetRef(0)` in its third mode
  is that mode's own target.

## Effects

Spells' effects are `Effect` values (`resolve.cards.primitives.base`): `tasks(state, context)`
gives the engine tasks that apply the effect now, with its references and values evaluated as it
applies (608.2h, `resolve.effects.evaluation`); nothing when there is nothing to do.
`describe(phrasing)` writes its text. `ResolveSpell` applies them one at a time, in order
(608.2c). Mana abilities' effects (`AddMana`, `AddManaOfAnyColor`) give events directly.

### `DealDamage` (`resolve.cards.primitives.effects`)
"[Source] deals [amount] damage to [recipients]": one `DamageDealt` to every recipient at once,
each object or player once; only creatures, planeswalkers and battles (120.1a) and players still in
the game. 0 (or less, 107.1b) deals nothing (120.8). The event's `apply` gives the results (120.3a
life loss, 120.3e marked damage; 120.3c and 120.3h raise until counters exist, M4); infect, wither,
lifelink and deathtouch plug in there.
- **Rules:** 120.1, 120.1a, 120.2b, 120.3, 120.4b, 120.8, 107.1b, 113.7a.
- **Parameters:** `amount: Value`, `to: tuple[TargetRef | EachCreature | EachOpponent, ...]`,
  `source: ObjectRef = ThisObject()` (the object that deals the damage: the spell, or "target
  creature you control").
- **Example:** Chandra's Ignition: `DealDamage(PowerOf(TargetRef(0)), (EachCreature(except_=
  TargetRef(0)), EachOpponent()), source=TargetRef(0))`; Test Shock (tests):
  `DealDamage(Fixed(2), (TargetRef(0),))` with `ANY_TARGET`.

### `Destroy` (`resolve.cards.primitives.effects`)
"Destroy [objects]": every permanent referred to, once each, that `legality.allowed(DestroyAction)`
permits (indestructible refuses), to its owner's graveyard at once.
- **Rules:** 701.8a, 702.12b.
- **Parameters:** `objects: tuple[ObjectRef, ...]`.
- **Example:** Decimate: `Destroy(tuple(TargetRef(i) for i in range(4)))`; Test Shatter (tests).

### `Exile` (`resolve.cards.primitives.effects`)
"Exile [objects]": every object referred to moves to exile from wherever it is, at once, as a new
object (`ObjectExiled`).
- **Rules:** 701.13a, 406.3, 400.7.
- **Parameters:** `objects: tuple[ObjectRef, ...]`.
- **Example:** Swords to Plowshares: `Exile((TargetRef(0),))`.

### `GainLife` (`resolve.cards.primitives.effects`)
"[Player] gains [amount] life": each player referred to (still in the game) gains it
(`LifeGained`); 0 or less is no event.
- **Rules:** 119.3, 119.10, 107.1b.
- **Parameters:** `player: PlayerRef`, `amount: Value`.
- **Example:** Swords to Plowshares: `GainLife(ControllerOf(TargetRef(0)), PowerOf(TargetRef(0)))`.

### `DrawCards` (`resolve.cards.primitives.effects`)
"[Player] draws [count] cards": each player referred to draws, one card at a time (the engine's
`DrawCards` task).
- **Rules:** 121.1, 121.2, 107.1b.
- **Parameters:** `count: Value = Fixed(1)`, `player: PlayerRef = You()`.
- **Example:** Test Ponder (tests): `DrawCards()`, "Draw a card."

### `CounterSpell` (`resolve.cards.primitives.effects`)
"Counter [spells]": each spell referred to that is still on the stack and that
`legality.allowed(CounterAction)` permits ("can't be countered" refuses, 101.2) is countered
(`SpellCountered`): to its owner's graveyard as a new object, through the event pipeline, never
`resolved_spell_destination`; no refund (701.6b).
- **Rules:** 701.6a, 701.6b, 113.6g, 101.2.
- **Parameters:** `spells: tuple[ObjectRef, ...]`.
- **Example:** Cancel: `CounterSpell((TargetRef(0),))` with `TargetSpec(spells=SpellFilter())`.

### `ReturnToHand` (`resolve.cards.primitives.effects`)
"Return [permanent] to its owner's hand": each permanent referred to moves to its owner's hand
as a new object (`ReturnedToHand`), all at once.
- **Rules:** 400.3, 400.7.
- **Parameters:** `objects: tuple[ObjectRef, ...]` (the text is written for one).
- **Example:** Cryptic Command: `ReturnToHand((TargetRef(0),))`.

### `TapAll` (`resolve.cards.primitives.effects`)
"Tap all [creatures]": every untapped creature of the group when it applies becomes tapped
(`PermanentTapped` each, at once); already tapped ones are left alone. Not targeted.
- **Rules:** 701.26a, 115.10, 608.2h.
- **Parameters:** `group: EachCreature` (with `controlled_by` and `except_`).
- **Example:** Cryptic Command: `TapAll(EachCreature(controlled_by=EachOpponent()))`, "Tap all
  creatures your opponents control."

### `AddMana` (`resolve.cards.primitives.effects`)
"Add [mana]": the controller adds these mana units, with the ability's object as their source.
- **Rules:** 106.3, 106.4.
- **Parameters:** `mana: tuple[ManaType, ...]` (at least one).
- **Example:** `AddMana((ManaType.GREEN,))` in the Forest's intrinsic ability;
  `AddMana((ManaType.COLORLESS, ManaType.COLORLESS))` in Sol Ring's.

### `AddManaOfAnyColor` (`resolve.cards.primitives.effects`)
"Add one mana of any color", the color chosen as the ability resolves (`CHOOSE_COLOR`, asked only
with two or more colors); optionally only colors of the controller's commanders' combined color
identity, and optionally with a spending restriction on the mana. No color to choose (no
commander, or a colorless one) adds no mana.
- **Rules:** 106.1a, 106.3, 106.5, 106.6, 605.3b, 903.4, 903.4f.
- **Parameters:** `commander_identity: bool`, `restriction: ManaRestriction | None`. `colors(...)`
  lists the choosable colors in WUBRG order; `events(..., color)`.
- **Example:** Command Tower and Arcane Signet: `AddManaOfAnyColor(commander_identity=True)`;
  Ixalli's Lorekeeper: `AddManaOfAnyColor(restriction=SpendOnlyOnSubtype(SubtypeWord("Dinosaur")))`.
  The identity comes from `resolve.rules.commander.commander_color_identity`.

## Mana restrictions (106.6)

### `ManaRestriction` (`resolve.state.mana`)
The base class of restrictions on spending mana: `allows(state, purpose)` and `text`. A `Mana`
unit carries one (`Mana.restriction`); a payment names its purpose, `ForSpell(spell)` or
`ForAbility(source, ability)`, and `PayCosts` won't spend a unit its restriction forbids.
- **Rules:** 106.6, 601.2h.

### `SpendOnlyOnSubtype` (`resolve.cards.primitives.restrictions`)
"Spend this mana only to cast a [subtype] spell or activate an ability of a [subtype] source": a
spell with the subtype, or an ability of any object with it (in any zone).
- **Rules:** 106.6, 205.3.
- **Parameters:** `subtype: SubtypeWord`.
- **Example:** Ixalli's Lorekeeper: `SpendOnlyOnSubtype(SubtypeWord("Dinosaur"))`.

## Typed words (`resolve.cards.primitives.words`)

### `ColorWord`, `LandTypeWord`, `SubtypeWord`, `NameRef` (`resolve.cards.primitives.words`)
Words in a definition, typed so a text-changing effect can find the ones it changes. A color
word used as a color, a land type used as a land type and a creature or other subtype used as
one are rewritable; a card name (`NameRef`) never is.
- **Rules:** 612.2, 612.2a, 205.3.
- **Parameters:** `ColorWord(color)`, `LandTypeWord(name)`, `SubtypeWord(name)`, `NameRef(name)`.
- **Example:** Emerald Medallion's "green", `ColorQuality(ColorWord(Color.GREEN))`; Kinjalli's
  Caller's `SubtypeWord("Dinosaur")`; the unit tests in `tests/rules/test_612_typed_words.py`.

### `rewrite_words(value, mapping)` (`resolve.cards.primitives.words`)
Walks an Immutable value (dataclass fields and tuples, at any depth) and replaces each typed word
that is a key of `mapping`; returns the value itself when nothing changes. A mapping between
different kinds of word raises `ValueError`.
- **Rules:** 612.2, 612.3 (only the definition's own words are walked), 613.1c.
- **Example:** M5's Mind Bend (`rewrite_words(definition, {ColorWord(WHITE): ColorWord(BLUE)})`).

## Costs: mana (`resolve.data.mana_cost`)

### `ManaSymbol`, `ManaCost`, `parse_mana_cost(text)` (`resolve.data.mana_cost`)
A mana cost as data: every symbol of 107.4 (colored, {C}, generic, {X}, hybrid, monocolored and
colorless hybrid, Phyrexian, hybrid Phyrexian, snow) in printed order, with `text`, `colors`
(202.2, WUBRG order) and `mana_value(x=0)` (202.3). `CardFace.cost` holds the parsed cost, `None`
for no mana cost (202.3a, not the same as `{0}`) or a cost that doesn't follow 107.4
(`ManaCostError`). `has_x`; `with_x(x)` is the cost with the announced value in place of each
{X}, its generic amounts added up into one symbol (the total cost of 601.2f, which `PayCosts`
pays). `generic` is the generic amount; `with_generic(n)` the cost with `n` generic mana in place
of its generic symbols (cost modifiers, 601.2f: `{0}` when nothing is left; refused below 0 or
with an unannounced {X}). Paying a cost is M2.3's `PayCosts`.
- **Rules:** 107.3a, 107.4, 107.4b, 202.1-202.3, 202.3e-g, 601.2f.
- **Example:** `parse_mana_cost("{2/W}{2/W}").mana_value() == 4` (Test Hybrid in the tests);
  `parse_mana_cost("{X}{R}").with_x(3) == parse_mana_cost("{3}{R}")` (Test Blaze).

## Targets and filters

### `TargetSpec`, `ANY_TARGET`, `target(*card_types, you_control=False)` (`resolve.cards.primitives.targets`)
One instance of the word "target": the permanents (`objects: ObjectFilter`), players (`players:
PlayerFilter`) and spells (`spells: SpellFilter`) it may choose, and how many (`minimum` to
`maximum`, distinct). Legality is only ever decided by `resolve.rules.targeting.target_problem`.
- **Rules:** 115.1, 115.2 (permanents unless it says otherwise), 115.3, 115.4 (`ANY_TARGET`:
  creature, planeswalker or battle, or player), 115.6 (`minimum=0`), 601.2c.
- **Example:** Decimate: `(target(CardType.ARTIFACT), target(CardType.CREATURE),
  target(CardType.ENCHANTMENT), target(CardType.LAND))`; Chandra's Ignition:
  `target(CardType.CREATURE, you_control=True)`.

### `ObjectFilter`, `PlayerFilter`, `SpellFilter` (`resolve.cards.primitives.targets`)
What a target may be: a permanent with at least one of `card_types` (none: any), controlled by
the spell's controller if `controller=You()`; a player, or only an opponent
(`opponents_only=True`); a spell on the stack. `matches(state, x, you)`; `text`.
- **Rules:** 115.1, 115.2, 109.5, 102.2.
- **Example:** `ObjectFilter((CardType.CREATURE,), You())` ("creature you control").

### References: `ThisObject`, `TargetRef`, `You`, `ControllerOf`, `EachCreature`, `EachOpponent` (`resolve.cards.primitives.refs`)
What a definition points at, resolved by `resolve.effects.evaluation` as the effect applies:
the spell itself (201.5); the legal targets of instance `index` (608.2b); its controller (109.5);
an object's controller, from last known information if it left (608.2h); every creature on the
battlefield but `except_` ("each other creature"), and only those `controlled_by` controls if
given (`You()`: "creatures you control"; `EachOpponent()`: "creatures your opponents control");
each opponent still in the game (800.4a).
- **Rules:** 201.5, 109.5, 108.4, 115.10, 608.2b, 608.2h, 800.4a.
- **Example:** Swords to Plowshares's `ControllerOf(TargetRef(0))`.

### Values: `Fixed`, `PowerOf`, `X` (`resolve.cards.primitives.values`)
Numbers as expressions, evaluated by `resolve.effects.evaluation.evaluate` when the effect applies:
a printed number (never negative); an object's power (last known if it left; nothing for an
illegal target); `X()`, the value announced for the spell as it was cast (from its record,
`CastChoices.x`, or its last known information; X only in the text, 107.3f, is a gap). Counts and
"greatest power" (M2.10) join them.
- **Rules:** 107.1b, 107.3a, 107.3i, 208.1, 608.2h, 608.2b.
- **Example:** `PowerOf(TargetRef(0))` in Swords to Plowshares and Chandra's Ignition;
  `DealDamage(X(), (TargetRef(0),))` in Test Blaze (`tests/game_fixtures.py`).

## Triggers

*None yet.*

## Conditions

### `ControlsAtLeast` (`resolve.cards.primitives.conditions`)
"Activate only if you control [count] or more [card type]s": the activating player controls at
least that many permanents with the card type, the source included.
- **Rules:** 602.5, 602.2.
- **Parameters:** `count: int` (at least 1), `card_type: CardType`.
- **Example:** Temple of the False God: `activate_only_if=ControlsAtLeast(5, CardType.LAND)`.

## Costs

### `Cost` (`resolve.cards.primitives.costs`)
The base class of costs: `can_pay(state, source, player)` (118.3) and `payment(...)`, the events
that pay it.
- **Rules:** 118.1, 118.3.

### `TapSelfCost` (`resolve.cards.primitives.costs`)
{T}: tap this permanent. A tapped permanent, or an object off the battlefield, can't pay it; nor
can a creature with summoning sickness (`defaults.can_tap_for_cost`).
- **Rules:** 107.5, 118.3, 701.26a, 302.6, 602.5a.
- **Example:** the cost of the Forest's intrinsic ability; Llanowar Elves'.

### `ManaPaymentCost` (`resolve.cards.primitives.costs`)
A mana cost in an activation cost, paid through `PayCosts` (other mana abilities may be activated
while paying it, not this one); an impossible payment reverses the activation. `can_pay` doesn't
refuse it, since the payment is only known once made.
- **Rules:** 602.2b, 601.2g-h, 605.3a, 605.3c, 118.3, 733.1.
- **Parameters:** `mana: ManaCost`.
- **Example:** Selesnya Signet: `ManaPaymentCost(parse_mana_cost("{1}"))`.

## Durations

*None yet.*

## Static abilities and continuous effects

### `CantBeCountered` (`resolve.cards.primitives.statics`)
"This spell can't be countered.": a static ability of a spell, functioning on the stack; it is
the prohibition of `legality.allowed(CounterAction)`. The spell can still be targeted, and a
spell that would counter it still resolves (101.2). `scope` is `ThisObject()`; "[spells] you
control can't be countered" from a permanent is a continuous effect (M5).
- **Rules:** 113.6g, 101.2.
- **Example:** Test Stubborn Spell (tests): `abilities=(CantBeCountered(),)`.

### `SpellCostReduction(spells, amount=1)` (`resolve.cards.primitives.cost_modifiers`)
"[Quality] spells you cast cost {N} less to cast.": a static ability of a permanent (113.6: it
functions only on the battlefield). For a spell its controller casts with the quality `spells`
(a `Quality` of `resolve.cards.keywords`, judged on the spell's characteristics on the stack),
`modifier(state, source, spell, caster)` gives `ReduceGeneric(amount)`; otherwise `None`. Its
text uses the quality's `adjective` ("Green spells", "Dinosaur spells").
- **Rules:** 601.2f, 118.7a, 113.6, 205.3, 202.3 (the mana value isn't changed).
- **Parameters:** `spells: Quality`, `amount: int` (generic mana).
- **Example:** Emerald Medallion: `SpellCostReduction(ColorQuality(ColorWord(Color.GREEN)))`;
  Kinjalli's Caller: `SpellCostReduction(SubtypeQuality(SubtypeWord("Dinosaur")))`.

### `SpellCostModifier`, `CostModifier`, `ModifierStep`, `ReduceGeneric` (`resolve.cards.primitives.cost_modifiers`)
The 601.2f pipeline's parts. A `SpellCostModifier` is a static ability whose `modifier(...)`
gives the `CostModifier` it applies to a spell being cast, or `None`. A `CostModifier` is data
with a `step` (`ModifierStep.INCREASE`, `REDUCTION`, `TOTAL`: additional costs and increases,
then reductions, then effects on the total) and `apply(cost) -> cost`. `ReduceGeneric(amount)`
reduces only the generic part, never below nothing (118.7a). `resolve.rules.costs` gathers the
modifiers of the permanents on the battlefield (`spell_cost_modifiers`) and applies them in
order (`spell_total_cost`), which `CastSpell`'s `TOTAL` stage locks in.
- **Rules:** 601.2f, 601.8, 118.7, 118.7a, 113.6.
- **Example:** `ReduceGeneric(1).apply(parse_mana_cost("{1}{G}")) == parse_mana_cost("{G}")`;
  the test-only increase `IncreaseGeneric` and Test Thorn's `SpellCostIncrease`
  (`tests/game_fixtures.py`).

## Replacement and prevention effects

*None yet.*

## Keywords (`resolve.cards.keywords`)

Keyword abilities are `Ability` values in a definition's `abilities`, read only through computed
characteristics (`has_keyword(chars, Kind)`, `keywords(chars, Kind)`) or, for a player,
`defaults.player_abilities`, so M5's grants need no change. "From A and from B" and "from each
[characteristic]" are separate abilities (702.16g-h, 702.11f-g); redundant instances count once.

### `Flash` (`resolve.cards.keywords.evergreen`)
"You may play this card any time you could cast an instant": read by `defaults.may_cast_now`,
from whatever zone a permission allows (it adds no zone).
- **Rules:** 702.8a, 702.8b, 117.1a, 304.1.
- **Example:** Ashcoat Bear: `CardDefinition("Ashcoat Bear", abilities=(Flash(),))`.

### `Hexproof(quality=None)` (`resolve.cards.keywords.evergreen`)
Can't be the target of spells or abilities its controller's (a player's: their) opponents
control; with a `quality`, only [quality] spells and abilities from [quality] sources. A
prohibition of `legality.allowed(TargetAction)` (`targeting.target_problem`). Works on the
battlefield only (113.6), so a hexproof creature spell can be countered. "Hexproof from" on a
player raises `NotImplementedRule("702.11d")` (the CR defines it for permanents).
- **Rules:** 702.11b, 702.11c, 702.11d, 702.11h, 608.2b.
- **Example:** Gladecover Scout: `Hexproof()`; Test Redproof Bear (tests): `Hexproof(ColorQuality(ColorWord(Color.RED)))`.

### `Shroud` (`resolve.cards.keywords.evergreen`)
Can't be the target of spells or abilities, its controller's included.
- **Rules:** 702.18a, 702.18b.
- **Example:** Humble Budoka: `Shroud()`.

### `Indestructible` (`resolve.cards.keywords.evergreen`)
Can't be destroyed: the prohibition of `legality.allowed(DestroyAction)`, used by `Destroy` and by
704.5g (lethal damage). 704.5f, exile and sacrifice are unaffected.
- **Rules:** 702.12b, 702.12c, 704.5g.
- **Example:** Darksteel Relic, Darksteel Myr: `Indestructible()`.

### `Protection(quality)`, `protection_from_each_color()` (`resolve.cards.keywords.evergreen`)
Can't be targeted by spells with the quality or abilities from sources with it, whoever controls
them; from `Everything()`, by nothing. Targeting is a prohibition of
`legality.allowed(TargetAction)`; damage prevention (702.16e) raises `NotImplementedRule` in
`DamageDealt.apply` until M6; blocking (702.16f) is M3, Auras and Equipment (702.16c-d) M4.
`protection_from_each_color()` is five abilities, one per color.
- **Rules:** 702.16a, 702.16b, 702.16e (gap), 702.16h, 702.16j, 702.16m.
- **Example:** Repentant Blacksmith: `Protection(ColorQuality(ColorWord(Color.RED)))`; Nacatl
  Savage: `Protection(CardTypeQuality(CardType.ARTIFACT))`; Test Prismatic Knight (tests):
  `abilities=protection_from_each_color()`.

### Qualities: `ColorQuality`, `MulticoloredQuality`, `MonocoloredQuality`, `CardTypeQuality`, `SubtypeQuality`, `Everything`, `each_color()` (`resolve.cards.keywords.qualities`)
What protection and "hexproof from" are from: `matches(characteristics)` over the targeting
spell's characteristics or an ability's source's (113.7a), `text` ("red", "artifacts",
"Elves") and `adjective`, the form before a noun ("green", "artifact", "Elf"; empty for
`Everything`), which `SpellCostReduction` uses. Colors and subtypes are typed words (612.2). Room is kept for a player (702.16k) and a
name (702.16a).
- **Rules:** 702.16a, 702.16j, 105.2b, 105.2c, 702.16h (`each_color`).
- **Example:** Nacatl Savage's `CardTypeQuality(CardType.ARTIFACT)`; Test Multiproof Knight
  (tests): `MulticoloredQuality()`; Emerald Medallion's "green spells".
