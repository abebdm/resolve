"""Real cards whose rules text changes how creatures attack or block (the M3 plan's "combat-rules
cards", section 7). Their characteristics come from the card data."""

from __future__ import annotations

from resolve.cards.primitives.combat import BlocksAnyNumber
from resolve.cards.registry import CardDefinition

# This creature can block any number of creatures.
PALACE_GUARD = CardDefinition("Palace Guard", abilities=(BlocksAnyNumber(),))

DEFINITIONS = (PALACE_GUARD,)
