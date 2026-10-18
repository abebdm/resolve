"""Events that change permanents: playing a land onto the battlefield, tapping and untapping."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from resolve.errors import EngineError
from resolve.events.base import Event
from resolve.state.game import move_object
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.zones import BATTLEFIELD, ZoneKind

if TYPE_CHECKING:
    from resolve.state.game import GameState


@dataclass(frozen=True, kw_only=True)
class LandPlayed(Event):
    """``player`` plays the land card ``card`` from their hand (305.1, a special action 116.2a).

    It goes onto the battlefield under their control (305.1), untapped (110.5b), as a new object
    (400.7, recorded as ``played``), and counts as their land played this turn (305.2).
    """

    player: PlayerId
    card: ObjectId
    played: ObjectId | None = None

    def apply(self, state: GameState) -> Event:
        if self.played is not None:
            raise EngineError("a land play is proposed without its outcome")
        if self.card not in state.player(self.player).hand:
            raise EngineError(f"object {self.card} isn't in player {self.player}'s hand")
        turn = state.turn
        if turn is None or turn.active_player != self.player:
            raise EngineError(f"player {self.player} can't play a land outside their turn")
        new = move_object(state, self.card, BATTLEFIELD, controller=self.player)
        turn.lands_played += 1
        return replace(self, played=new.id)


def _permanent(state: GameState, obj: ObjectId) -> None:
    if state.object(obj).zone.kind is not ZoneKind.BATTLEFIELD:
        raise EngineError(f"object {obj} isn't a permanent (110.5d)")


@dataclass(frozen=True, kw_only=True)
class PermanentTapped(Event):
    """The permanent ``obj`` becomes tapped (701.26a). Only an untapped one can be."""

    obj: ObjectId

    def apply(self, state: GameState) -> None:
        _permanent(state, self.obj)
        permanent = state.objects[self.obj]
        if permanent.tapped:
            raise EngineError(f"object {self.obj} is already tapped (701.26a)")
        permanent.tapped = True


@dataclass(frozen=True, kw_only=True)
class PermanentsUntapped(Event):
    """The permanents ``objs`` untap, all at the same time (701.26b, 502.3)."""

    objs: tuple[ObjectId, ...]

    def apply(self, state: GameState) -> None:
        for obj in self.objs:
            _permanent(state, obj)
            if not state.objects[obj].tapped:
                raise EngineError(f"object {obj} isn't tapped (701.26b)")
        for obj in self.objs:
            state.objects[obj].tapped = False
