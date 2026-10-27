"""Instants and sorceries that remove permanents: Swords to Plowshares, Chandra's Ignition,
Decimate and Fiery Confluence."""

from __future__ import annotations

from resolve.cards.primitives.effects import DealDamage, Destroy, Exile, GainLife
from resolve.cards.primitives.refs import ControllerOf, EachCreature, EachOpponent, TargetRef
from resolve.cards.primitives.spells import Mode, ModeChoice, SpellAbility
from resolve.cards.primitives.targets import target
from resolve.cards.primitives.values import Fixed, PowerOf
from resolve.cards.registry import CardDefinition
from resolve.data.types import CardType

_IT = TargetRef(0)

# Exile target creature. Its controller gains life equal to its power.
SWORDS_TO_PLOWSHARES = CardDefinition(
    "Swords to Plowshares",
    spell=SpellAbility(
        (
            Mode(
                (target(CardType.CREATURE),),
                (Exile((_IT,)), GainLife(ControllerOf(_IT), PowerOf(_IT))),
            ),
        )
    ),
)

# Target creature you control deals damage equal to its power to each other creature and each
# opponent.
CHANDRAS_IGNITION = CardDefinition(
    "Chandra's Ignition",
    spell=SpellAbility(
        (
            Mode(
                (target(CardType.CREATURE, you_control=True),),
                (
                    DealDamage(
                        PowerOf(_IT), (EachCreature(except_=_IT), EachOpponent()), source=_IT
                    ),
                ),
            ),
        )
    ),
)

# Destroy target artifact, target creature, target enchantment, and target land. (You can't cast
# this spell unless you have legal choices for all its targets.)
DECIMATE = CardDefinition(
    "Decimate",
    spell=SpellAbility(
        (
            Mode(
                (
                    target(CardType.ARTIFACT),
                    target(CardType.CREATURE),
                    target(CardType.ENCHANTMENT),
                    target(CardType.LAND),
                ),
                (Destroy(tuple(TargetRef(i) for i in range(4))),),
            ),
        )
    ),
)

# Choose three. You may choose the same mode more than once.
# • Fiery Confluence deals 1 damage to each creature.
# • Fiery Confluence deals 2 damage to each opponent.
# • Destroy target artifact.
FIERY_CONFLUENCE = CardDefinition(
    "Fiery Confluence",
    spell=SpellAbility(
        (
            Mode((), (DealDamage(Fixed(1), (EachCreature(),)),)),
            Mode((), (DealDamage(Fixed(2), (EachOpponent(),)),)),
            Mode((target(CardType.ARTIFACT),), (Destroy((_IT,)),)),
        ),
        ModeChoice(3, 3, repeatable=True),
    ),
)

DEFINITIONS = (SWORDS_TO_PLOWSHARES, CHANDRAS_IGNITION, DECIMATE, FIERY_CONFLUENCE)
