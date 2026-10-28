"""Permanents whose static abilities reduce the cost of spells (601.2f, 118.7a): Emerald Medallion
and Kinjalli's Caller. Their characteristics come from the card data."""

from __future__ import annotations

from resolve.cards.keywords.qualities import ColorQuality, SubtypeQuality
from resolve.cards.primitives.cost_modifiers import SpellCostReduction
from resolve.cards.primitives.words import ColorWord, SubtypeWord
from resolve.cards.registry import CardDefinition
from resolve.data.types import Color

# Green spells you cast cost {1} less to cast.
EMERALD_MEDALLION = CardDefinition(
    "Emerald Medallion",
    abilities=(SpellCostReduction(ColorQuality(ColorWord(Color.GREEN))),),
)
# Dinosaur spells you cast cost {1} less to cast.
KINJALLIS_CALLER = CardDefinition(
    "Kinjalli's Caller",
    abilities=(SpellCostReduction(SubtypeQuality(SubtypeWord("Dinosaur"))),),
)

DEFINITIONS = (EMERALD_MEDALLION, KINJALLIS_CALLER)
