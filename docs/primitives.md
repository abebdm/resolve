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
