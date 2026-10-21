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

## Effects

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
- **Example:** none yet in a definition (a mana Medallion's "green" will be `ColorWord(Color.GREEN)`); the
  unit tests in `tests/rules/test_612_typed_words.py`.

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
(`ManaCostError`). Paying a cost is M2.3's `TotalCost` and `PayCosts`.
- **Rules:** 107.4, 202.1-202.3, 202.3e-g.
- **Example:** `parse_mana_cost("{2/W}{2/W}").mana_value() == 4` (Test Hybrid in the tests).

## Targets and filters

*None yet.*

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

*None yet.*

## Replacement and prevention effects

*None yet.*

## Keywords (`resolve.cards.keywords`)

*None yet.*
