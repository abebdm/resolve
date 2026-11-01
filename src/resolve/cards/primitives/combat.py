"""Static abilities of creatures that change how they attack or block (506-509; design.md §17.18),
read through the creature's computed characteristics, so granted ones (M5) need no change.

So far: ``BlocksAnyNumber``, "This creature can block any number of creatures." (Palace Guard),
read by ``defaults.blocks_allowed`` (509.1a). The rest of the M3 plan's list (``CantBeBlocked``,
``AttacksEachCombat``, ``MustBeBlockedByAll``, ...) arrives with its cards in M3.4 and M3.5.
"""

from __future__ import annotations

from dataclasses import dataclass

from resolve.cards.primitives.base import Ability
from resolve.cards.primitives.refs import ThisObject

_THIS_OBJECT = ThisObject()


@dataclass(frozen=True)
class BlocksAnyNumber(Ability):
    """ "This creature can block any number of creatures." (509.1a): it may block any number of
    the creatures attacking its controller, instead of one. ``defaults.blocks_allowed`` reads it
    (``None``: no limit); 509.1a's other conditions (untapped, attacking that player) still
    apply. Several instances are redundant."""

    scope: ThisObject = _THIS_OBJECT

    @property
    def text(self) -> str:
        return "This creature can block any number of creatures."
