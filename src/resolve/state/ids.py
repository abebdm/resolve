"""Identifiers for players, objects and physical cards (design.md §4, §8).

All three are plain ``int``s at run time, so they pickle and compare cheaply; ``NewType`` keeps
pyright from mixing them up.

- ``PlayerId``: the player's seat, ``0`` to ``n - 1`` in seating (clockwise) order. It never
  changes, even after the player leaves the game (800.4).
- ``ObjectId``: one game object (109.1). Allocated from ``GameState.next_object_id``, starting at
  1, and never reused. An object that changes zones becomes a new object with a new ID (400.7).
- ``CardId``: one physical card, stable across zone changes. It identifies a commander (903.3)
  and supports the "find the card" exceptions of 400.7. Tokens, copies and abilities have none.
"""

from __future__ import annotations

from typing import NewType

PlayerId = NewType("PlayerId", int)
ObjectId = NewType("ObjectId", int)
CardId = NewType("CardId", int)
