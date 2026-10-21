"""Conditions: restrictions on when an ability may be activated (602.5).

So far: ``ControlsAtLeast``, Temple of the False God's "Activate only if you control five or more
lands."
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.data.types import CardType
from resolve.errors import NotImplementedRule
from resolve.state.ids import ObjectId, PlayerId
from resolve.values import Immutable

if TYPE_CHECKING:
    from resolve.state.game import GameState

_NUMBER_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")


@dataclass(frozen=True)
class ControlsAtLeast(Immutable):
    """ "Activate only if you control [count] or more [card type]s." (602.5, 602.1b)

    "You" is the player activating the ability (the source's controller, 602.2). The permanents
    counted are those that player controls with the card type now (205.2), the source included
    when it has the type (Temple of the False God counts itself).
    """

    count: int
    card_type: CardType

    def __post_init__(self) -> None:
        if self.count < 1:
            raise ValueError("ControlsAtLeast needs a count of at least 1")

    def met(self, state: GameState, source: ObjectId, player: PlayerId) -> bool:
        """Whether ``player`` controls at least ``count`` permanents of the card type now."""
        raise NotImplementedRule("602.5: activation conditions (M2.4 stub)")

    @property
    def text(self) -> str:
        """The restriction as printed, such as ``"Activate only if you control five or more
        lands."``."""
        number = _NUMBER_WORDS[self.count] if self.count < len(_NUMBER_WORDS) else str(self.count)
        return f"Activate only if you control {number} or more {self.card_type.value.lower()}s."
