"""Creatures whose abilities make mana: Llanowar Elves, Avacyn's Pilgrim and Ixalli's Lorekeeper.

Their {T} abilities are creatures' {T} abilities, so summoning sickness applies (302.6).
"""

from __future__ import annotations

from resolve.cards.primitives.abilities import ActivatedManaAbility
from resolve.cards.primitives.costs import TapSelfCost
from resolve.cards.primitives.effects import AddMana, AddManaOfAnyColor
from resolve.cards.primitives.restrictions import SpendOnlyOnSubtype
from resolve.cards.primitives.words import SubtypeWord
from resolve.cards.registry import CardDefinition
from resolve.state.mana import ManaType

# {T}: Add {G}.
LLANOWAR_ELVES = CardDefinition(
    "Llanowar Elves", (ActivatedManaAbility((TapSelfCost(),), AddMana((ManaType.GREEN,))),)
)

# {T}: Add {W}.
AVACYNS_PILGRIM = CardDefinition(
    "Avacyn's Pilgrim", (ActivatedManaAbility((TapSelfCost(),), AddMana((ManaType.WHITE,))),)
)

# {T}: Add one mana of any color. Spend this mana only to cast a Dinosaur spell or activate an
# ability of a Dinosaur source.
IXALLIS_LOREKEEPER = CardDefinition(
    "Ixalli's Lorekeeper",
    (
        ActivatedManaAbility(
            (TapSelfCost(),),
            AddManaOfAnyColor(restriction=SpendOnlyOnSubtype(SubtypeWord("Dinosaur"))),
        ),
    ),
)

DEFINITIONS = (LLANOWAR_ELVES, AVACYNS_PILGRIM, IXALLIS_LOREKEEPER)
