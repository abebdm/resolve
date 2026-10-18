"""Events that move cards: drawing (121) and the mulligan procedure (103.5)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.errors import NotImplementedRule
from resolve.events.base import Event
from resolve.state.ids import ObjectId, PlayerId

if TYPE_CHECKING:
    from resolve.state.game import GameState


@dataclass(frozen=True, kw_only=True)
class CardDrawn(Event):
    """``player`` draws a card (121.1)."""

    player: PlayerId
    drawn_from: ObjectId | None = None
    drawn: ObjectId | None = None
    empty_library: bool = False

    def apply(self, state: GameState) -> None:
        raise NotImplementedRule("121.1: drawing a card")


@dataclass(frozen=True, kw_only=True)
class HandShuffledIntoLibrary(Event):
    """``player`` shuffles their hand into their library (103.5)."""

    player: PlayerId
    cards: tuple[ObjectId, ...]

    def apply(self, state: GameState) -> None:
        raise NotImplementedRule("103.5: shuffling a hand into a library")


@dataclass(frozen=True, kw_only=True)
class CardsPutOnBottom(Event):
    """``player`` puts cards from their hand on the bottom of their library (103.5)."""

    player: PlayerId
    cards: tuple[ObjectId, ...]
    count: int

    def apply(self, state: GameState) -> None:
        raise NotImplementedRule("103.5: putting cards on the bottom")
