"""The five basic lands: Plains, Island, Swamp, Mountain and Forest.

Their Oracle text is only reminder text ("({T}: Add {G}.)"), which isn't rules text: each has no
printed abilities. The mana ability comes from the basic land type (305.6), which
``resolve.effects.characteristics`` adds to any land with that type.
"""

from __future__ import annotations

from resolve.cards.registry import CardDefinition

PLAINS = CardDefinition("Plains")
ISLAND = CardDefinition("Island")
SWAMP = CardDefinition("Swamp")
MOUNTAIN = CardDefinition("Mountain")
FOREST = CardDefinition("Forest")

DEFINITIONS = (PLAINS, ISLAND, SWAMP, MOUNTAIN, FOREST)
