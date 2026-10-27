"""The total cost of a spell (601.2f, 118.7, design.md §17.6).

``spell_total_cost(state, spell, caster, base)`` is the one place 601.2f's cost modifiers plug
in. ``base`` is the mana cost or alternative cost, with X's announced value (601.2b, 107.3a).
The modifiers come from ``spell_cost_modifiers`` and are applied in 601.2f's order
(``ModifierStep``):

1. additional costs and cost increases (the commander tax, M7);
2. cost reductions (Emerald Medallion, Kinjalli's Caller), never below {0};
3. effects that directly affect the total cost.

The result is locked in: ``CastSpell`` keeps it, and later changes to the modifiers have no
effect on it (601.2f, 601.8).

Within a step the modifiers are applied in battlefield order. 601.2f lets the player choose the
order of reductions; generic reductions (the only kind so far, ``ReduceGeneric``) give the same
total in any order, so nothing is asked. A reduction for which the order matters (118.7b-e:
colored, colorless or hybrid amounts) needs that choice first, with its first card.

Modifiers come from the static abilities of permanents on the battlefield (113.6: a permanent's
abilities function only there); abilities that function elsewhere ("This spell costs {1} less
to cast", 113.6b, Ghalta: M4) are added with their first card. Activated abilities' costs (602.2b)
use the same pipeline from M4.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from resolve.cards.primitives.cost_modifiers import CostModifier, ModifierStep, SpellCostModifier
from resolve.effects.characteristics import characteristics

if TYPE_CHECKING:
    from resolve.data.mana_cost import ManaCost
    from resolve.state.game import GameState
    from resolve.state.ids import ObjectId, PlayerId


def spell_cost_modifiers(
    state: GameState, spell: ObjectId, caster: PlayerId
) -> tuple[CostModifier, ...]:
    """The modifiers that apply to the cost of ``spell``, which ``caster`` is casting (601.2f):
    those of every permanent's ``SpellCostModifier`` abilities (113.6), in battlefield order."""
    found: list[CostModifier] = []
    for source in state.battlefield:
        for ability in characteristics(state, source).abilities:
            if isinstance(ability, SpellCostModifier):
                modifier = ability.modifier(state, source, spell, caster)
                if modifier is not None:
                    found.append(modifier)
    return tuple(found)


def spell_total_cost(
    state: GameState, spell: ObjectId, caster: PlayerId, base: ManaCost
) -> ManaCost:
    """The total cost of ``spell`` (601.2f): ``base`` (the mana cost or alternative cost, X's
    value in it), plus increases, minus reductions, then the effects on the total."""
    modifiers = spell_cost_modifiers(state, spell, caster)
    total = base
    for step in ModifierStep:
        for modifier in modifiers:
            if modifier.step is step:
                total = modifier.apply(total)
    return total
