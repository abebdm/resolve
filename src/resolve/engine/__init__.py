"""The task-queue engine.

Public API, turn structure, priority, casting, resolution and combat (design.md §3, §5).
"""

from resolve.engine.api import new_game, pending_decision, submit, view_for
from resolve.engine.deck import Deck, DeckCard, build_deck
from resolve.engine.view import PlayerView

__all__ = [
    "Deck",
    "DeckCard",
    "PlayerView",
    "build_deck",
    "new_game",
    "pending_decision",
    "submit",
    "view_for",
]
