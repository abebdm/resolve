"""Events about the game as a whole: starting it and ending it (103, 104)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from resolve.errors import EngineError
from resolve.events.base import Event
from resolve.state.game import GameResult, move_object, zone_list
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.zones import COMMAND

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
class CommanderPutIntoCommandZone(Event):
    """``player`` put their commander ``obj`` from their deck face up into the command zone.

    103.2c and 903.6. The commander becomes a new object in the command zone (400.7).
    """

    player: PlayerId
    obj: ObjectId

    def apply(self, state: GameState) -> None:
        old = state.object(self.obj)
        if old.owner != self.player or old.card not in state.player(self.player).commanders:
            raise EngineError(f"object {self.obj} isn't a commander of player {self.player}")
        move_object(state, self.obj, COMMAND)


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


@dataclass(frozen=True, kw_only=True)
class MulliganDeclared(Event):
    """``player`` declared whether they take a mulligan (103.5).

    Declarations are public: each player knows the earlier players' choices (101.4b).
    """

    player: PlayerId
    mulligan: bool

    def apply(self, state: GameState) -> None:
        return None


@dataclass(frozen=True, kw_only=True)
class PlayerLost(Event):
    """``player`` lost the game (104.3), and so leaves it (104.5).

    ``rules`` names how: a state-based action (704.5a, 704.5b) or a concession (104.3a). The
    loss also clears the player's record of drawing from an empty library (704.5b looks only
    at draws since the last check).
    """

    player: PlayerId

    def apply(self, state: GameState) -> None:
        player = state.player(self.player)
        if player.lost:
            raise EngineError(f"player {self.player} has already lost")
        player.lost = True
        player.drew_from_empty_library = False


@dataclass(frozen=True, kw_only=True)
class Conceded(Event):
    """``player`` conceded the game (104.3a), through ``resolve.engine.concede``.

    Unlike other events this records an input, like an answer: a replay concedes again where
    it finds one (design.md §12). The consequences follow as their own events: the player loses
    (``PlayerLost``) and leaves the game (``PlayerLeftGame``).
    """

    player: PlayerId

    def apply(self, state: GameState) -> None:
        state.player(self.player)  # validates the ID


@dataclass(frozen=True, kw_only=True)
class PlayerLeftGame(Event):
    """``player`` leaves the game (104.5, 800.4a): every object they own leaves the game.

    ``removed`` records those objects, as applied. A player who leaves also loses their unspent
    mana. Objects they control but don't own, and effects giving them control, can't exist yet:
    ``LeaveGame`` raises ``NotImplementedRule`` before proposing this event if they would.
    """

    player: PlayerId
    removed: tuple[ObjectId, ...] = ()

    def apply(self, state: GameState) -> Event:
        player = state.player(self.player)
        if player.left_game:
            raise EngineError(f"player {self.player} has already left the game")
        player.left_game = True
        player.mana_pool.clear()
        removed = tuple(
            obj for obj, game_object in state.objects.items() if game_object.owner == self.player
        )
        for obj in removed:
            zone_list(state, state.objects[obj].zone).remove(obj)
            del state.objects[obj]
        return replace(self, removed=removed)
