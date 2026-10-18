"""Costs (118): what a player pays to activate an ability.

A cost is data: ``can_pay`` says whether it could be paid now (118.3: never without the
resources to pay it fully), and ``payment`` gives the events that pay it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.data.types import CardType
from resolve.errors import NotImplementedRule
from resolve.events.permanents import PermanentTapped
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.zones import ZoneKind
from resolve.values import Immutable

if TYPE_CHECKING:
    from resolve.events.base import Event
    from resolve.state.game import GameState


@dataclass(frozen=True)
class Cost(Immutable, ABC):
    """A cost an ability's controller pays (118.1)."""

    @abstractmethod
    def can_pay(self, state: GameState, source: ObjectId, player: PlayerId) -> bool:
        """Whether ``player`` could pay this cost for ``source`` right now (118.3)."""

    @abstractmethod
    def payment(self, state: GameState, source: ObjectId, player: PlayerId) -> tuple[Event, ...]:
        """The events that pay this cost."""

    @property
    @abstractmethod
    def text(self) -> str:
        """The cost as printed, such as ``"{T}"``."""


@dataclass(frozen=True)
class TapSelfCost(Cost):
    """{T}: tap this permanent (107.5). An already tapped permanent can't pay it (118.3).

    A creature's {T} ability also needs the creature to have been controlled continuously since
    its controller's most recent turn began (302.6, 602.5a); that isn't tracked yet, so a {T}
    cost on a creature raises ``NotImplementedRule``.
    """

    def can_pay(self, state: GameState, source: ObjectId, player: PlayerId) -> bool:
        from resolve.effects.characteristics import characteristics

        obj = state.object(source)
        if obj.zone.kind is not ZoneKind.BATTLEFIELD or obj.tapped:
            return False
        if characteristics(state, source).is_a(CardType.CREATURE):
            raise NotImplementedRule("302.6: the {T} abilities of creatures (summoning sickness)")
        return True

    def payment(self, state: GameState, source: ObjectId, player: PlayerId) -> tuple[Event, ...]:
        return (PermanentTapped(obj=source, rules=("107.5", "701.26a")),)

    @property
    def text(self) -> str:
        return "{T}"
