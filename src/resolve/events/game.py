"""Events about the game as a whole: starting it and ending it (103, 104)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.errors import EngineError
from resolve.events.base import Event
from resolve.state.game import GameResult
from resolve.state.ids import PlayerId

if TYPE_CHECKING:
    from resolve.state.game import GameState


@dataclass(frozen=True, kw_only=True)
class StartingPlayerChosen(Event):
    """``chooser`` chose ``starting_player`` to take the first turn (103.1)."""

    chooser: PlayerId
    starting_player: PlayerId

    def apply(self, state: GameState) -> None:
        if state.starting_player is not None:
            raise EngineError("the starting player has already been chosen")
        state.player(self.starting_player)  # validates the ID
        state.starting_player = self.starting_player


@dataclass(frozen=True, kw_only=True)
class LibraryShuffled(Event):
    """``player``'s library was shuffled into a random order (701.24a).

    Afterwards no player knows the order of its cards, so any knowledge of where a card is in the
    library is forgotten.
    """

    player: PlayerId

    def apply(self, state: GameState) -> None:
        library = state.player(self.player).library
        state.rng.shuffle(library)
        for obj in library:
            state.objects[obj].known_to = ()


@dataclass(frozen=True, kw_only=True)
class GameEnded(Event):
    """The game ended (104.1) with these winners; none means a draw (104.4a)."""

    winners: tuple[PlayerId, ...]

    def apply(self, state: GameState) -> None:
        if state.result is not None:
            raise EngineError("the game is already over")
        for winner in self.winners:
            state.player(winner)  # validates the ID
        state.result = GameResult(tuple(sorted(dict.fromkeys(self.winners))))
