"""Computing an object's characteristics (109.3, design.md §8).

``characteristics(state, obj)`` is the single place the engine reads what an object *is*: its
name, types and abilities. It starts from the card's printed face and will apply continuous effects
through the layer system (613) once they exist (M5). Nothing can create a continuous effect
yet, so for now the result is the printed face. Characteristics are always computed, never
stored on the object.

Abilities are the face's printed abilities (its card definition), then the abilities rules give
it: a land with a basic land type has "{T}: Add [mana symbol]" for each one (305.6), in type-line
order.

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

from resolve.cards.primitives.abilities import BASIC_LAND_MANA, Ability, intrinsic_mana_ability
from resolve.data.cards import CardData
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
    abilities: tuple[Ability, ...] = ()

    def is_a(self, card_type: CardType) -> bool:
        """Whether the object has this card type (205.2)."""
        return card_type in self.card_types


def characteristics(state: GameState, obj: ObjectId) -> Characteristics:
    """The current characteristics of ``obj`` (109.3; layers arrive in M5)."""
    card = state.card_of(state.object(obj))
    index = _face_index(card.data)
    face = card.data.faces[index]
    types = face.types
    if types is None:
        # A deck can't contain such a card (DeckCard refuses it), so this is a bug.
        raise EngineError(f"{face.name!r} has an unreadable type line in a game")
    abilities: list[Ability] = list(card.definitions[index].abilities)
    if CardType.LAND in types.card_types:
        # 305.6: each basic land type gives the land its intrinsic mana ability.
        abilities += [intrinsic_mana_ability(t) for t in types.subtypes if t in BASIC_LAND_MANA]
    return Characteristics(
        name=face.name,
        supertypes=types.supertypes,
        card_types=types.card_types,
        subtypes=types.subtypes,
        abilities=tuple(abilities),
    )


def _face_index(data: CardData) -> int:
    if not data.is_multi_faced:
        return 0
    if data.layout in FRONT_FACE_LAYOUTS:
        return 0  # 712.8a, 712.8c, 712.8d
    raise NotImplementedRule(
        "109.3: the characteristics of multi-faced cards other than double-faced cards"
    )
