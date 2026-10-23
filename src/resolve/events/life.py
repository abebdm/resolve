"""Life (119): gaining life."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.errors import EngineError
from resolve.events.base import Event
from resolve.state.ids import PlayerId

if TYPE_CHECKING:
    from resolve.state.game import GameState


@dataclass(frozen=True, kw_only=True)
class LifeGained(Event):
    """``player`` gains ``amount`` life, at least 1 (119.3; gaining 0 is no event, 119.10).
    Public."""

    player: PlayerId
    amount: int

    def apply(self, state: GameState) -> None:
        if self.amount < 1:
            raise EngineError("a life gain event gains at least 1 life (119.10)")
        player = state.player(self.player)
        if player.left_game:
            raise EngineError(f"player {self.player} has left the game (800.4a)")
        player.life += self.amount
