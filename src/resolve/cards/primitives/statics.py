"""Static abilities of spells (113.6), read through the spell's characteristics.

So far: ``CantBeCountered``, "This spell can't be countered." (113.6g: it functions on the
stack), the prohibition of ``legality.allowed(CounterAction)``.
"""

from __future__ import annotations

from dataclasses import dataclass

from resolve.cards.primitives.base import Ability
from resolve.cards.primitives.refs import ThisObject

_THIS_OBJECT = ThisObject()


@dataclass(frozen=True)
class CantBeCountered(Ability):
    """ "This spell can't be countered." (113.6g, 101.2): a spell or ability that would counter it
    doesn't, though it may still target it (701.6a's "counter" is an instruction the "can't"
    overrides). ``scope`` is the spell itself; "[spells] you control can't be countered" (a
    static ability of a permanent, Destiny Spinner) is a continuous effect (M5)."""

    scope: ThisObject = _THIS_OBJECT

    @property
    def text(self) -> str:
        return "This spell can't be countered."
