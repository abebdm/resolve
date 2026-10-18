"""Format parameters for one game (design.md §10).

The number of players isn't a setting: it is the number of decks passed to ``new_game`` (100.1).
The CR has one mulligan procedure (103.5, with 103.5c applying automatically to multiplayer
games), so there is no mulligan setting either. Deck-construction rules (100.2a, 903.5) arrive
in M7 together with their enforcement.
"""

from __future__ import annotations

from dataclasses import dataclass

from resolve.values import Immutable


@dataclass(frozen=True)
class CommanderRules(Immutable):
    """The Commander rules (903) and their parameters.

    ``damage_threshold`` is the combat damage from a single commander that makes a player lose
    (903.10a).
    """

    damage_threshold: int = 21

    def __post_init__(self) -> None:
        if self.damage_threshold < 1:
            raise ValueError(f"damage_threshold must be at least 1, got {self.damage_threshold}")


@dataclass(frozen=True)
class GameConfig(Immutable):
    """The parameters of one game.

    - ``starting_life``: each player's starting life total (103.4; 40 in Commander, 103.4c).
    - ``starting_hand_size``: the number of cards in an opening hand (103.5).
    - ``commander``: the Commander rules, or ``None`` for a game without them.
    """

    starting_life: int = 20
    starting_hand_size: int = 7
    commander: CommanderRules | None = None

    def __post_init__(self) -> None:
        if self.starting_life < 1:
            raise ValueError(f"starting_life must be at least 1, got {self.starting_life}")
        if self.starting_hand_size < 0:
            raise ValueError(f"starting_hand_size can't be negative: {self.starting_hand_size}")

    @classmethod
    def standard(cls) -> GameConfig:
        """A regular game: 20 life (103.4), seven-card hands (103.5)."""
        return cls()

    @classmethod
    def commander_game(cls) -> GameConfig:
        """A Commander game: 40 life (103.4c, 903.7) and the Commander rules (903)."""
        return cls(starting_life=40, commander=CommanderRules())
