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
- **Rules:** 605.1a, 605.3a, 605.3b, 602.2 (only the controller activates), 118.3.
- **Parameters:** `cost: tuple[Cost, ...]`, `effect: AddMana`.
- **Example:** Llanowar Elves (not implemented yet):
  `ActivatedManaAbility((TapSelfCost(),), AddMana((ManaType.GREEN,)))`.

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
- **Example:** `AddMana((ManaType.GREEN,))` in the Forest's intrinsic ability.

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

*None yet.*

## Costs

### `Cost` (`resolve.cards.primitives.costs`)
The base class of costs: `can_pay(state, source, player)` (118.3) and `payment(...)`, the events
that pay it.
- **Rules:** 118.1, 118.3.

### `TapSelfCost` (`resolve.cards.primitives.costs`)
{T}: tap this permanent. A tapped permanent, or an object off the battlefield, can't pay it. On
a creature it raises `NotImplementedRule("302.6")` until summoning sickness is tracked.
- **Rules:** 107.5, 118.3, 701.26a, 302.6.
- **Example:** the cost of the Forest's intrinsic ability.

## Durations

*None yet.*

## Static abilities and continuous effects

*None yet.*

## Replacement and prevention effects

*None yet.*

## Keywords (`resolve.cards.keywords`)

*None yet.*
