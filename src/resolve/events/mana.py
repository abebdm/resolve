"""Events of mana pools: adding mana and losing unspent mana (106.4, 500.5)."""

from __future__ import annotations

from dataclasses import dataclass, replace
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

    def redo(self, state: GameState) -> None:
        self.apply(state)  # the same units again (733.1)


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


@dataclass(frozen=True, kw_only=True)
class ManaSpent(Event):
    """``player`` spends ``mana`` from their pool to pay a cost (601.2h, 118.3a): it is removed.
    As applied, ``left`` is the mana still in the pool, which the player announces (118.3a,
    106.4a)."""

    player: PlayerId
    mana: tuple[Mana, ...]
    left: tuple[Mana, ...] | None = None

    def apply(self, state: GameState) -> Event:
        if self.left is not None:
            raise EngineError("mana spending is proposed without its outcome")
        pool = state.player(self.player).mana_pool
        remaining = list(pool)
        for unit in self.mana:
            if unit not in remaining:
                raise EngineError(f"player {self.player}'s pool has no {unit} to spend")
            remaining.remove(unit)
        pool[:] = remaining
        return replace(self, left=tuple(remaining))
