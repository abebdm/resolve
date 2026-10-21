"""Artifacts whose abilities make mana: Sol Ring, Arcane Signet and Selesnya Signet."""

from __future__ import annotations

from resolve.cards.primitives.abilities import ActivatedManaAbility
from resolve.cards.primitives.costs import ManaPaymentCost, TapSelfCost
from resolve.cards.primitives.effects import AddMana, AddManaOfAnyColor
from resolve.cards.registry import CardDefinition
from resolve.data.mana_cost import parse_mana_cost
from resolve.state.mana import ManaType

# {T}: Add {C}{C}.
SOL_RING = CardDefinition(
    "Sol Ring",
    (ActivatedManaAbility((TapSelfCost(),), AddMana((ManaType.COLORLESS, ManaType.COLORLESS))),),
)

# {T}: Add one mana of any color in your commander's color identity.
ARCANE_SIGNET = CardDefinition(
    "Arcane Signet",
    (ActivatedManaAbility((TapSelfCost(),), AddManaOfAnyColor(commander_identity=True)),),
)

# {1}, {T}: Add {G}{W}.
SELESNYA_SIGNET = CardDefinition(
    "Selesnya Signet",
    (
        ActivatedManaAbility(
            (ManaPaymentCost(parse_mana_cost("{1}")), TapSelfCost()),
            AddMana((ManaType.GREEN, ManaType.WHITE)),
        ),
    ),
)

DEFINITIONS = (SOL_RING, ARCANE_SIGNET, SELESNYA_SIGNET)
