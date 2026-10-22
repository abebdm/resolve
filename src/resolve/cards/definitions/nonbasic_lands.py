"""Nonbasic lands: Command Tower and Temple of the False God."""

from __future__ import annotations

from resolve.cards.primitives.abilities import ActivatedManaAbility
from resolve.cards.primitives.conditions import ControlsAtLeast
from resolve.cards.primitives.costs import TapSelfCost
from resolve.cards.primitives.effects import AddMana, AddManaOfAnyColor
from resolve.cards.registry import CardDefinition
from resolve.data.types import CardType
from resolve.state.mana import ManaType

# {T}: Add one mana of any color in your commander's color identity.
COMMAND_TOWER = CardDefinition(
    "Command Tower",
    (ActivatedManaAbility((TapSelfCost(),), AddManaOfAnyColor(commander_identity=True)),),
)

# {T}: Add {C}{C}. Activate only if you control five or more lands.
TEMPLE_OF_THE_FALSE_GOD = CardDefinition(
    "Temple of the False God",
    (
        ActivatedManaAbility(
            (TapSelfCost(),),
            AddMana((ManaType.COLORLESS, ManaType.COLORLESS)),
            activate_only_if=ControlsAtLeast(5, CardType.LAND),
        ),
    ),
)

DEFINITIONS = (COMMAND_TOWER, TEMPLE_OF_THE_FALSE_GOD)
