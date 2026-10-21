"""Artifacts whose abilities make mana: Sol Ring."""

from __future__ import annotations

from resolve.cards.primitives.abilities import ActivatedManaAbility
from resolve.cards.primitives.costs import TapSelfCost
from resolve.cards.primitives.effects import AddMana
from resolve.cards.registry import CardDefinition
from resolve.state.mana import ManaType

# {T}: Add {C}{C}.
SOL_RING = CardDefinition(
    "Sol Ring",
    (ActivatedManaAbility((TapSelfCost(),), AddMana((ManaType.COLORLESS, ManaType.COLORLESS))),),
)

DEFINITIONS = (SOL_RING,)
