"""Spells that draw cards: Rishkar's Expertise."""

from __future__ import annotations

from resolve.cards.primitives.effects import DrawCards, MayCastFromHand
from resolve.cards.primitives.refs import EachCreature, You
from resolve.cards.primitives.spells import Mode, SpellAbility
from resolve.cards.primitives.values import Fixed, GreatestPower
from resolve.cards.registry import CardDefinition

# Draw cards equal to the greatest power among creatures you control.
# You may cast a spell with mana value 5 or less from your hand without paying its mana cost.
RISHKARS_EXPERTISE = CardDefinition(
    "Rishkar's Expertise",
    spell=SpellAbility(
        (
            Mode(
                (),
                (
                    DrawCards(GreatestPower(EachCreature(controlled_by=You()))),
                    MayCastFromHand(Fixed(5)),
                ),
                paragraphs=(1,),
            ),
        )
    ),
)

DEFINITIONS = (RISHKARS_EXPERTISE,)
