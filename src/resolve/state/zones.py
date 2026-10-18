"""Zones (400).

There are seven zones (400.1). Library, hand and graveyard belong to one player; battlefield,
stack, exile and command are shared. The ante zone (407) isn't supported, and no card in scope
uses it.

Ordered zones are lists of ``ObjectId``s. In every pile (library, graveyard, stack) the **last**
element is the top. Hand, battlefield, exile and command zone have no meaningful order (400.5);
their lists are kept in arrival order so iteration is deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from resolve.state.ids import PlayerId
from resolve.values import Immutable


class ZoneKind(Enum):
    """One of the seven zones of 400.1."""

    LIBRARY = "library"
    HAND = "hand"
    GRAVEYARD = "graveyard"
    BATTLEFIELD = "battlefield"
    STACK = "stack"
    EXILE = "exile"
    COMMAND = "command"

    @property
    def is_public(self) -> bool:
        """Whether all players can see the cards' faces in this zone (400.2)."""
        return self not in (ZoneKind.LIBRARY, ZoneKind.HAND)

    @property
    def is_per_player(self) -> bool:
        """Whether each player has their own zone of this kind (400.1)."""
        return self in (ZoneKind.LIBRARY, ZoneKind.HAND, ZoneKind.GRAVEYARD)


@dataclass(frozen=True)
class Zone(Immutable):
    """A specific zone: a kind plus, for per-player zones, the player it belongs to."""

    kind: ZoneKind
    owner: PlayerId | None = None

    def __post_init__(self) -> None:
        if self.kind.is_per_player != (self.owner is not None):
            raise ValueError(
                f"the {self.kind.value} zone {'needs' if self.kind.is_per_player else 'has no'} "
                "owner"
            )

    @classmethod
    def library(cls, player: PlayerId) -> Zone:
        """``player``'s library (401)."""
        return cls(ZoneKind.LIBRARY, player)

    @classmethod
    def hand(cls, player: PlayerId) -> Zone:
        """``player``'s hand (402)."""
        return cls(ZoneKind.HAND, player)

    @classmethod
    def graveyard(cls, player: PlayerId) -> Zone:
        """``player``'s graveyard (404)."""
        return cls(ZoneKind.GRAVEYARD, player)

    def __str__(self) -> str:
        if self.owner is None:
            return self.kind.value
        return f"{self.kind.value} of player {self.owner}"


BATTLEFIELD = Zone(ZoneKind.BATTLEFIELD)
STACK = Zone(ZoneKind.STACK)
EXILE = Zone(ZoneKind.EXILE)
COMMAND = Zone(ZoneKind.COMMAND)
