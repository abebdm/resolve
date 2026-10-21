"""Computing an object's characteristics (109.3, design.md §8).

``characteristics(state, obj)`` is the single place the engine reads what an object *is*: its
name, mana cost, colors, mana value, types, abilities, power and toughness (printed numbers,
208.1; a star raises
``NotImplementedRule("208.2")`` when read). It starts from the card's printed face and will
apply continuous effects through the layer system (613) once they exist (M5). Nothing can
create a continuous effect yet, so for now the result is the printed face. Characteristics are
always computed, never stored on the object.

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
- omen and preparation cards: their front part (720.4, 722.4: outside an Omen spell on the stack
  an omen card has only its normal characteristics, and a preparation card has them in every
  zone). The layouts are ``omen``, ``prepare``, and Scryfall's ``adventure`` layout when the
  second face is an Omen (the data files omens that way), and the data may carry one face or
  two. Casting an omen card as an Omen (720.3) and casting a preparation card's alternative
  part (722.3) are cast variants, whose gaps M2.3 raises.

Mana cost, colors and mana value (202):

- the mana cost is the face's printed cost, ``None`` if it has none (202.3a, and not the same
  as ``{0}``);
- the colors are the face's colors in the card data (105.2, 202.2): Scryfall derives them from the
  mana cost and any color indicator (204.2), so a card whose colors are set otherwise (devoid)
  reads right too;
- the mana value is the cost's, with {X} as 0 (202.3e); M2.3 gives an object on the stack the X
  chosen for it. The back face of a nonmodal double-faced card is never read yet (712.8d), so
  202.3b needs nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.cards.primitives.abilities import BASIC_LAND_MANA, Ability, intrinsic_mana_ability
from resolve.data.cards import CardData
from resolve.data.mana_cost import ManaCost
from resolve.data.types import CardType, Color, Supertype
from resolve.errors import EngineError, NotImplementedRule
from resolve.state.ids import ObjectId
from resolve.state.zones import ZoneKind
from resolve.values import Immutable

if TYPE_CHECKING:
    from resolve.state.game import GameState

# Scryfall layouts of double-faced cards whose front face gives the characteristics (712.8a).
FRONT_FACE_LAYOUTS = ("transform", "modal_dfc")
# Layouts of omen and preparation cards (720, 722), whatever the number of faces in the data.
NORMAL_FACE_LAYOUTS = ("omen", "prepare")
# 205.3: the subtype of an omen's inset part; Scryfall's "adventure" layout also holds omens.
OMEN_SUBTYPE = "Omen"


@dataclass(frozen=True)
class Characteristics(Immutable):
    """An object's characteristics as currently computed (109.3)."""

    name: str
    supertypes: tuple[Supertype, ...]
    card_types: tuple[CardType, ...]
    subtypes: tuple[str, ...]
    abilities: tuple[Ability, ...] = ()
    power_text: str | None = None
    toughness_text: str | None = None
    mana_cost: ManaCost | None = None
    colors: tuple[Color, ...] = ()
    mana_value: int = 0

    def is_a(self, card_type: CardType) -> bool:
        """Whether the object has this card type (205.2)."""
        return card_type in self.card_types

    @property
    def power(self) -> int | None:
        """The power (208.1, 302.4c), or ``None`` if the object has none."""
        return _number(self.power_text)

    @property
    def toughness(self) -> int | None:
        """The toughness (208.1, 302.4c), or ``None`` if the object has none."""
        return _number(self.toughness_text)


def _number(text: str | None) -> int | None:
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        # 208.2: a star (or "1+*") is set by an ability or effect, which can't exist yet.
        raise NotImplementedRule("208.2: power or toughness that isn't a fixed number") from None


def characteristics(state: GameState, obj: ObjectId) -> Characteristics:
    """The current characteristics of ``obj`` (109.3; layers arrive in M5)."""
    game_object = state.object(obj)
    card = state.card_of(game_object)
    index = _face_index(card.data)
    face = card.data.faces[index]
    types = face.types
    if types is None or face.mana_cost_problem is not None:
        # A deck can't contain such a card (DeckCard refuses it), so this is a bug.
        raise EngineError(f"{face.name!r} has an unreadable type line or mana cost in a game")
    abilities: list[Ability] = list(card.definitions[index].abilities)
    if CardType.LAND in types.card_types:
        # 305.6: each basic land type gives the land its intrinsic mana ability.
        abilities += [intrinsic_mana_ability(t) for t in types.subtypes if t in BASIC_LAND_MANA]
    # 208.3: a noncreature permanent has no power or toughness, even if some is printed.
    has_numbers = (
        CardType.CREATURE in types.card_types or game_object.zone.kind is not ZoneKind.BATTLEFIELD
    )
    return Characteristics(
        name=face.name,
        supertypes=types.supertypes,
        card_types=types.card_types,
        subtypes=types.subtypes,
        abilities=tuple(abilities),
        power_text=face.power if has_numbers else None,
        toughness_text=face.toughness if has_numbers else None,
        mana_cost=face.cost,
        colors=tuple(color for color in Color if color.value in face.colors),
        mana_value=0 if face.cost is None else face.cost.mana_value(),
    )


def _face_index(data: CardData) -> int:
    if data.layout in NORMAL_FACE_LAYOUTS or _is_omen(data):
        return 0  # 720.4, 722.4
    if not data.is_multi_faced:
        return 0
    if data.layout in FRONT_FACE_LAYOUTS:
        return 0  # 712.8a, 712.8c, 712.8d
    raise NotImplementedRule(
        "109.3: the characteristics of multi-faced cards other than double-faced cards"
    )


def _is_omen(data: CardData) -> bool:
    """Whether the card is an omen card (720.1): its second part has the Omen subtype."""
    return any(
        face.types is not None and OMEN_SUBTYPE in face.types.subtypes for face in data.faces[1:]
    )
