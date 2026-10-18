"""Computing an object's characteristics (109.3, design.md §8).

``characteristics(state, obj)`` is the single place the engine reads what an object *is*: its
name and types. It starts from the card's printed face and will apply continuous effects
through the layer system (613) once they exist (M5). Nothing can create a continuous effect
yet, so for now the result is the printed face. Characteristics are always computed, never
stored on the object.

Which face counts:

- a single-faced card: its only face;
- a transforming or modal double-faced card: its front face. Outside the battlefield and the
  stack it has only the characteristics of its front face (712.8a); on the stack it is cast
  front face up (712.8c), and nothing can turn a permanent's back face up yet (712.8d);
- other multi-faced cards (split, flip, adventurer, meld, ...): ``NotImplementedRule``, since
  each has its own rules for combined or alternative characteristics (709.4, 710.1, 715.4,
  712.4).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.data.cards import CardFace
from resolve.data.types import CardType, Supertype
from resolve.errors import EngineError, NotImplementedRule
from resolve.state.ids import ObjectId
from resolve.values import Immutable

if TYPE_CHECKING:
    from resolve.state.game import GameState

# Scryfall layouts of double-faced cards whose front face gives the characteristics (712.8a).
FRONT_FACE_LAYOUTS = ("transform", "modal_dfc")


@dataclass(frozen=True)
class Characteristics(Immutable):
    """An object's characteristics as currently computed (109.3)."""

    name: str
    supertypes: tuple[Supertype, ...]
    card_types: tuple[CardType, ...]
    subtypes: tuple[str, ...]

    def is_a(self, card_type: CardType) -> bool:
        """Whether the object has this card type (205.2)."""
        return card_type in self.card_types


def characteristics(state: GameState, obj: ObjectId) -> Characteristics:
    """The current characteristics of ``obj`` (109.3; layers arrive in M5)."""
    face = _face(state, obj)
    types = face.types
    if types is None:
        # A deck can't contain such a card (DeckCard refuses it), so this is a bug.
        raise EngineError(f"{face.name!r} has an unreadable type line in a game")
    return Characteristics(
        name=face.name,
        supertypes=types.supertypes,
        card_types=types.card_types,
        subtypes=types.subtypes,
    )


def _face(state: GameState, obj: ObjectId) -> CardFace:
    card = state.card_of(state.object(obj))
    data = card.data
    if not data.is_multi_faced:
        return data.faces[0]
    if data.layout in FRONT_FACE_LAYOUTS:
        return data.faces[0]  # 712.8a, 712.8c, 712.8d
    raise NotImplementedRule(
        f"109.3: the characteristics of a card with the {data.layout!r} layout ({data.name})"
    )
