"""Events of mana pools: adding mana and losing unspent mana (106.4, 500.5)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.errors import EngineError
from resolve.events.base import Event
from resolve.state.ids import PlayerId
from resolve.state.mana import Mana

if TYPE_CHECKING:
    from resolve.state.game import GameState


@dataclass(frozen=True, kw_only=True)
class ManaAdded(Event):
    """``player`` adds ``mana`` to their mana pool (106.3, 106.4)."""

    player: PlayerId
    mana: tuple[Mana, ...]

    def apply(self, state: GameState) -> None:
        if not self.mana:
            raise EngineError("ManaAdded needs some mana")
        state.player(self.player).mana_pool.extend(self.mana)


@dataclass(frozen=True, kw_only=True)
class ManaPoolEmptied(Event):
    """``player``'s unspent ``mana`` empties from their pool as a step or phase ends (500.5,
    703.4q). The player loses this mana (106.4)."""

    player: PlayerId
    mana: tuple[Mana, ...]

    def apply(self, state: GameState) -> None:
        pool = state.player(self.player).mana_pool
        if tuple(pool) != self.mana:
            raise EngineError(f"player {self.player}'s pool isn't {self.mana}")
        pool.clear()
