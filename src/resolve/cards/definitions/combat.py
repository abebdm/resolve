"""Real cards whose rules text changes how creatures attack or block (the M3 plan's "combat-rules
cards", section 7). Their characteristics come from the card data."""

from __future__ import annotations

from resolve.cards.keywords.qualities import SubtypeQuality
from resolve.cards.primitives.combat import (
    AtMostCreatures,
    AttacksEachCombat,
    AttackTax,
    BlocksAnyNumber,
    CantAttackOrBlockAlone,
    CantBeBlocked,
    CantBeBlockedBy,
    MustBeBlockedByAll,
)
from resolve.cards.primitives.words import SubtypeWord
from resolve.cards.registry import CardDefinition
from resolve.data.mana_cost import parse_mana_cost

# This creature can block any number of creatures.
PALACE_GUARD = CardDefinition("Palace Guard", abilities=(BlocksAnyNumber(),))

# This creature can't be blocked.
PHANTOM_WARRIOR = CardDefinition("Phantom Warrior", abilities=(CantBeBlocked(),))

# This creature attacks each combat if able.
# This creature can't be blocked by Walls.
JUGGERNAUT = CardDefinition(
    "Juggernaut",
    abilities=(AttacksEachCombat(), CantBeBlockedBy(SubtypeQuality(SubtypeWord("Wall")))),
)

# All creatures able to block this creature do so.
PRIZED_UNICORN = CardDefinition("Prized Unicorn", abilities=(MustBeBlockedByAll(),))

# Creatures can't attack you unless their controller pays {2} for each creature they control
# that's attacking you.
GHOSTLY_PRISON = CardDefinition("Ghostly Prison", abilities=(AttackTax(parse_mana_cost("{2}")),))

# This creature can't attack or block alone.
MOGG_FLUNKIES = CardDefinition("Mogg Flunkies", abilities=(CantAttackOrBlockAlone(),))

# No more than one creature can attack each combat.
# No more than one creature can block each combat.
SILENT_ARBITER = CardDefinition(
    "Silent Arbiter",
    abilities=(AtMostCreatures(1, blocking=False), AtMostCreatures(1, blocking=True)),
)

DEFINITIONS = (
    PALACE_GUARD,
    PHANTOM_WARRIOR,
    JUGGERNAUT,
    PRIZED_UNICORN,
    GHOSTLY_PRISON,
    MOGG_FLUNKIES,
    SILENT_ARBITER,
)
