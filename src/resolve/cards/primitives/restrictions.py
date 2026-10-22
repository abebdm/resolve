"""Restrictions on spending mana (106.6), attached to the mana an ability adds.

So far: ``SpendOnlyOnSubtype``, Ixalli's Lorekeeper's "Spend this mana only to cast a Dinosaur
spell or activate an ability of a Dinosaur source."
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.cards.primitives.words import SubtypeWord
from resolve.state.mana import ForAbility, ForSpell, ManaRestriction, PaymentPurpose

if TYPE_CHECKING:
    from resolve.state.game import GameState


@dataclass(frozen=True)
class SpendOnlyOnSubtype(ManaRestriction):
    """106.6: "Spend this mana only to cast a [subtype] spell or activate an ability of a [subtype]
    source."

    A [subtype] spell is a spell with that subtype (205.3); a [subtype] source is any object with
    it, wherever it is (Ixalli's Lorekeeper's ruling: a Dinosaur card in a hand or graveyard
    counts). Both are judged by the object's current characteristics as the mana is spent.
    """

    subtype: SubtypeWord

    def allows(self, state: GameState, purpose: PaymentPurpose) -> bool:
        from resolve.effects.characteristics import characteristics

        match purpose:
            case ForSpell(spell=obj) | ForAbility(source=obj):
                return self.subtype.name in characteristics(state, obj).subtypes

    @property
    def text(self) -> str:
        name = self.subtype.name
        return (
            f"Spend this mana only to cast {_article(name)} {name} spell or activate an ability "
            f"of {_article(name)} {name} source."
        )


def _article(word: str) -> str:
    return "an" if word[0].lower() in "aeiou" else "a"
