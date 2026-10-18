"""Game state as pure data.

GameState, players, objects, zones, IDs and GameConfig (design.md §4, §10).
"""

from resolve.state.config import CommanderRules, GameConfig
from resolve.state.game import Card, GameObject, GameResult, GameState, Player
from resolve.state.ids import CardId, ObjectId, PlayerId
from resolve.state.rng import Rng
from resolve.state.zones import Zone, ZoneKind

__all__ = [
    "Card",
    "CardId",
    "CommanderRules",
    "GameConfig",
    "GameObject",
    "GameResult",
    "GameState",
    "ObjectId",
    "Player",
    "PlayerId",
    "Rng",
    "Zone",
    "ZoneKind",
]
