"""Real cards whose only rules text is one keyword (chosen in the M2 plan): each is the example
card of its keyword (docs/primitives.md). Their characteristics come from the card data."""

from __future__ import annotations

from resolve.cards.keywords import (
    CardTypeQuality,
    ColorQuality,
    Flash,
    Hexproof,
    Indestructible,
    Protection,
    Shroud,
)
from resolve.cards.primitives.effects import CounterSpell
from resolve.cards.primitives.refs import TargetRef
from resolve.cards.primitives.spells import Mode, SpellAbility
from resolve.cards.primitives.targets import SpellFilter, TargetSpec
from resolve.cards.primitives.words import ColorWord
from resolve.cards.registry import CardDefinition
from resolve.data.types import CardType, Color

# Flash
ASHCOAT_BEAR = CardDefinition("Ashcoat Bear", abilities=(Flash(),))
# Hexproof
GLADECOVER_SCOUT = CardDefinition("Gladecover Scout", abilities=(Hexproof(),))
# Shroud
HUMBLE_BUDOKA = CardDefinition("Humble Budoka", abilities=(Shroud(),))
# Indestructible
DARKSTEEL_RELIC = CardDefinition("Darksteel Relic", abilities=(Indestructible(),))
DARKSTEEL_MYR = CardDefinition("Darksteel Myr", abilities=(Indestructible(),))
# Protection from red
REPENTANT_BLACKSMITH = CardDefinition(
    "Repentant Blacksmith", abilities=(Protection(ColorQuality(ColorWord(Color.RED))),)
)
# Protection from artifacts
NACATL_SAVAGE = CardDefinition(
    "Nacatl Savage", abilities=(Protection(CardTypeQuality(CardType.ARTIFACT)),)
)
# Counter target spell.
CANCEL = CardDefinition(
    "Cancel",
    spell=SpellAbility(
        (Mode((TargetSpec(spells=SpellFilter()),), (CounterSpell((TargetRef(0),)),)),)
    ),
)

# Haste, Vigilance, Defender (M3.2)
RAGING_GOBLIN = CardDefinition("Raging Goblin")
ALABORN_GRENADIER = CardDefinition("Alaborn Grenadier")
WALL_OF_STONE = CardDefinition("Wall of Stone")

DEFINITIONS = (
    ASHCOAT_BEAR,
    GLADECOVER_SCOUT,
    HUMBLE_BUDOKA,
    DARKSTEEL_RELIC,
    DARKSTEEL_MYR,
    REPENTANT_BLACKSMITH,
    NACATL_SAVAGE,
    CANCEL,
    RAGING_GOBLIN,
    ALABORN_GRENADIER,
    WALL_OF_STONE,
)
