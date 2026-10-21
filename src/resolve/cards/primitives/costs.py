"""Costs (118): what a player pays to activate an ability.

A cost is data: ``can_pay`` says whether it could be paid now (118.3: never without the
resources to pay it fully), and ``payment`` gives the events that pay it. A mana cost
(``ManaPaymentCost``) is the exception: it is paid through ``PayCosts`` (601.2g-h), which may
activate other mana abilities first (605.3a).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.data.mana_cost import ManaCost
from resolve.errors import EngineError
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
    its controller's most recent turn began (302.6, 602.5a); ``defaults.can_tap_for_cost`` decides.
    """

    def can_pay(self, state: GameState, source: ObjectId, player: PlayerId) -> bool:
        from resolve.rules import defaults

        obj = state.object(source)
        if obj.zone.kind is not ZoneKind.BATTLEFIELD or obj.tapped:
            return False
        return defaults.can_tap_for_cost(state, source)  # 302.6

    def payment(self, state: GameState, source: ObjectId, player: PlayerId) -> tuple[Event, ...]:
        return (PermanentTapped(obj=source, rules=("107.5", "701.26a")),)

    @property
    def text(self) -> str:
        return "{T}"


@dataclass(frozen=True)
class ManaPaymentCost(Cost):
    """A mana cost in an activation cost, such as Selesnya Signet's {1} (118.1, 602.2b).

    It is paid through ``PayCosts`` (601.2g-h): the player may activate other mana abilities while
    paying it (605.3a), but not the one being activated (605.3c). Whether it can be paid isn't
    known before the player has done so, so ``can_pay`` doesn't refuse it: a payment that turns
    out impossible makes the activation illegal, and it is reversed (118.3, 733.1). 903.4f costs
    (undefined qualities, unpayable) don't exist among mana costs yet.
    """

    mana: ManaCost

    def can_pay(self, state: GameState, source: ObjectId, player: PlayerId) -> bool:
        return True  # decided while paying (601.2h, 733.1)

    def payment(self, state: GameState, source: ObjectId, player: PlayerId) -> tuple[Event, ...]:
        raise EngineError("a mana cost is paid through PayCosts (601.2g-h), not as events")

    @property
    def text(self) -> str:
        return self.mana.text
