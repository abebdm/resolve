"""Events that move cards between a player's library and hand: drawing (121) and the parts of
the mulligan procedure (103.5).

Library objects keep their IDs through shuffles, so an event that would show another player a
library object's ID is logged with a redacted form for them (design.md §9).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from resolve.errors import EngineError
from resolve.events.base import Event
from resolve.state.game import move_object
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.zones import Zone

if TYPE_CHECKING:
    from resolve.state.game import GameState


@dataclass(frozen=True, kw_only=True)
class CardDrawn(Event):
    """``player`` draws a card: the top card of their library goes into their hand (121.1).

    Proposed with only the player. As applied it records the library object that was drawn
    (``drawn_from``) and the new object in the hand (``drawn``, 400.7). Drawing from an empty
    library draws nothing and is remembered for 704.5b (``empty_library``, 121.4).

    The drawing player sees the whole event; other players see the new hand object but not the
    library object (design.md §9), so they can count the hand but learn nothing else.
    """

    player: PlayerId
    drawn_from: ObjectId | None = None
    drawn: ObjectId | None = None
    empty_library: bool = False

    def visible_to(self, state: GameState) -> tuple[PlayerId, ...] | None:
        if not state.player(self.player).library:
            return None
        return (self.player,)

    def apply(self, state: GameState) -> Event:
        if self.drawn_from is not None or self.drawn is not None or self.empty_library:
            raise EngineError("a draw is proposed without its outcome")
        player = state.player(self.player)
        if not player.library:
            player.drew_from_empty_library = True  # 121.4
            rules = self.rules if "121.4" in self.rules else (*self.rules, "121.4")
            return replace(self, empty_library=True, rules=rules)
        top = player.library[-1]
        new = move_object(state, top, Zone.hand(self.player))
        return replace(self, drawn_from=top, drawn=new.id)

    def redacted(self) -> Event | None:
        return replace(self, drawn_from=None)


@dataclass(frozen=True, kw_only=True)
class HandShuffledIntoLibrary(Event):
    """``player`` shuffles the cards in their hand back into their library (103.5, 701.24a).

    ``cards`` are the hand objects, whose IDs every player knows (hands can be counted, 402.3).
    Each becomes a new library object (400.7), and the whole library is shuffled, so nobody
    knows where any library card is afterwards.
    """

    player: PlayerId
    cards: tuple[ObjectId, ...]

    def apply(self, state: GameState) -> None:
        player = state.player(self.player)
        if list(self.cards) != player.hand:
            raise EngineError(f"{self.cards} isn't player {self.player}'s hand")
        for obj in self.cards:
            move_object(state, obj, Zone.library(self.player))
        state.rng.shuffle(player.library)
        for obj in player.library:
            state.objects[obj].known_to = ()


@dataclass(frozen=True, kw_only=True)
class CardsPutOnBottom(Event):
    """``player`` puts ``cards`` from their hand on the bottom of their library (103.5).

    ``cards`` are listed from top to bottom: the last one ends up at the very bottom. Each
    becomes a new library object (400.7) that its owner still knows (they chose it). Other
    players see only how many cards went to the bottom (``count``), since the order of a library
    is hidden (401.2).
    """

    player: PlayerId
    cards: tuple[ObjectId, ...]
    count: int

    def visible_to(self, state: GameState) -> tuple[PlayerId, ...] | None:
        return (self.player,)

    def apply(self, state: GameState) -> None:
        player = state.player(self.player)
        if self.count != len(self.cards) or len(set(self.cards)) != len(self.cards):
            raise EngineError(f"put on bottom: {self.count} doesn't count {self.cards}")
        if any(obj not in player.hand for obj in self.cards):
            raise EngineError(f"{self.cards} aren't all in player {self.player}'s hand")
        for obj in self.cards:
            # Each card goes beneath the ones before it, so the last listed is the bottom card.
            new = move_object(state, obj, Zone.library(self.player), bottom=True)
            new.known_to = (self.player,)

    def redacted(self) -> Event | None:
        return replace(self, cards=())


@dataclass(frozen=True, kw_only=True)
class CardDiscarded(Event):
    """``player`` discards ``card`` from their hand: it goes to their graveyard (701.9a).

    It becomes a new object in the graveyard (400.7), recorded as applied (``discarded``).
    Discarding is public: the card is revealed as it goes to a public zone (400.2, 404.2).
    """

    player: PlayerId
    card: ObjectId
    discarded: ObjectId | None = None

    def apply(self, state: GameState) -> Event:
        if self.discarded is not None:
            raise EngineError("a discard is proposed without its outcome")
        if self.card not in state.player(self.player).hand:
            raise EngineError(f"object {self.card} isn't in player {self.player}'s hand")
        new = move_object(state, self.card, Zone.graveyard(self.player))
        return replace(self, discarded=new.id)
