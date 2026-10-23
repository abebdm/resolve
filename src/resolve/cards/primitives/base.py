"""The base classes of primitives, kept free of engine imports so card definitions can name
them without import cycles."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.values import Immutable

if TYPE_CHECKING:
    from resolve.cards.primitives.refs import Phrasing
    from resolve.effects.evaluation import Context
    from resolve.state.game import GameState
    from resolve.tasks import Task


@dataclass(frozen=True)
class Ability(Immutable, ABC):
    """An ability of an object (113)."""

    @property
    @abstractmethod
    def text(self) -> str:
        """The ability's rules text, such as ``"{T}: Add {G}."``."""


@dataclass(frozen=True)
class Effect(Immutable, ABC):
    """What part of a spell or ability does as it resolves (609.1): one instruction, applied in
    the order written (608.2c).

    ``tasks`` gives the engine tasks that apply it, worked out when it applies, with the values
    and references it needs evaluated then (608.2h); an effect that does nothing (no legal
    target left, 0 life to gain) gives none.
    """

    @abstractmethod
    def tasks(self, state: GameState, context: Context) -> tuple[Task, ...]:
        """The tasks that apply this effect now, for the spell or ability ``context`` names."""

    @abstractmethod
    def describe(self, phrasing: Phrasing) -> str:
        """The instruction as written, without its final period."""
