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
    703.4q). The player loses this mana (106.4). ``kept`` is the mana that stays because an effect
    says so (none yet); the pool must hold exactly ``mana`` and ``kept`` together."""

    player: PlayerId
    mana: tuple[Mana, ...]
    kept: tuple[Mana, ...] = ()

    def apply(self, state: GameState) -> None:
        pool = state.player(self.player).mana_pool
        if sorted(map(repr, pool)) != sorted(map(repr, (*self.mana, *self.kept))):
            raise EngineError(f"player {self.player}'s pool isn't {(*self.mana, *self.kept)}")
        pool[:] = self.kept
