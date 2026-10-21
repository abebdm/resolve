"""Events that change permanents: playing a land, tapping and untapping, damage removal, and
permanents leaving for the graveyard (701.8, 704.5f, 704.5g)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from resolve.errors import EngineError
from resolve.events.base import Event
from resolve.state.game import move_object
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.zones import BATTLEFIELD, Zone, ZoneKind

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

    def redo(self, state: GameState) -> None:
        self.apply(state)  # 733.1


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


def _to_graveyard(state: GameState, obj: ObjectId) -> ObjectId:
    _permanent(state, obj)
    owner = state.objects[obj].owner
    return move_object(state, obj, Zone.graveyard(owner)).id


@dataclass(frozen=True, kw_only=True)
class PermanentDestroyed(Event):
    """The permanent ``obj`` is destroyed: it moves to its owner's graveyard (701.8a), as a new
    object (400.7, recorded as ``moved``). Lethal damage (704.5g) destroys; 701.8b."""

    obj: ObjectId
    moved: ObjectId | None = None

    def apply(self, state: GameState) -> Event:
        if self.moved is not None:
            raise EngineError("a destruction is proposed without its outcome")
        return replace(self, moved=_to_graveyard(state, self.obj))


@dataclass(frozen=True, kw_only=True)
class PutIntoGraveyard(Event):
    """The permanent ``obj`` is put into its owner's graveyard without being destroyed
    (701.8b), as for a creature with 0 or less toughness (704.5f). ``moved`` is the new object
    (400.7)."""

    obj: ObjectId
    moved: ObjectId | None = None

    def apply(self, state: GameState) -> Event:
        if self.moved is not None:
            raise EngineError("a move is proposed without its outcome")
        return replace(self, moved=_to_graveyard(state, self.obj))


@dataclass(frozen=True, kw_only=True)
class DamageRemoved(Event):
    """All damage marked on the permanents ``objs`` is removed, at the same time (514.2)."""

    objs: tuple[ObjectId, ...]

    def apply(self, state: GameState) -> None:
        for obj in self.objs:
            _permanent(state, obj)
        for obj in self.objs:
            state.objects[obj].damage = 0
