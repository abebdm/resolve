"""Type lines: supertypes, card types and subtypes (205).

A type line reads ``[supertypes] card types [— subtypes]``, for example
``"Legendary Creature — Elf Druid"`` or ``"Basic Land — Forest"``. ``parse_type_line`` turns
Scryfall's printed text into a ``TypeLine``.

- Supertypes are basic, legendary, ongoing, snow and world (205.4a).
- Card types are those of 205.2a; an object can have several (205.2b).
- Subtypes follow the long dash. Each word is one subtype (205.3b), except that creature types
  may be two words ("Time Lord", the only one in 205.3m) and a plane's subtype is the whole
  phrase after the dash (205.3b, 205.3n).

Text that doesn't follow this shape raises ``TypeLineError``. The card data contains a few such
type lines (Un-set cards with joke types); loading them is fine, and only using such a card in a
game is refused (``CardFace.types`` is then ``None``; docs/decisions.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from resolve.values import Immutable

# 205.3b: the long dash separating card types from subtypes.
DASH = "—"
# 205.3m: the only creature type of two words.
TWO_WORD_SUBTYPES = ("Time Lord",)


class TypeLineError(ValueError):
    """A type line doesn't follow 205's shape."""


class Supertype(Enum):
    """The supertypes (205.4a)."""

    BASIC = "Basic"
    LEGENDARY = "Legendary"
    ONGOING = "Ongoing"
    SNOW = "Snow"
    WORLD = "World"


class Color(Enum):
    """The five colors (105.1, 202.2a), by their mana symbols, in the order 105.1 lists them."""

    WHITE = "W"
    BLUE = "U"
    BLACK = "B"
    RED = "R"
    GREEN = "G"


class CardType(Enum):
    """The card types (205.2a)."""

    ARTIFACT = "Artifact"
    BATTLE = "Battle"
    CONSPIRACY = "Conspiracy"
    CREATURE = "Creature"
    DUNGEON = "Dungeon"
    ENCHANTMENT = "Enchantment"
    INSTANT = "Instant"
    KINDRED = "Kindred"
    LAND = "Land"
    PHENOMENON = "Phenomenon"
    PLANE = "Plane"
    PLANESWALKER = "Planeswalker"
    SCHEME = "Scheme"
    SORCERY = "Sorcery"
    VANGUARD = "Vanguard"


_SUPERTYPES = {supertype.value: supertype for supertype in Supertype}
_CARD_TYPES = {card_type.value: card_type for card_type in CardType}


@dataclass(frozen=True)
class TypeLine(Immutable):
    """A parsed type line, in printed order."""

    supertypes: tuple[Supertype, ...]
    card_types: tuple[CardType, ...]
    subtypes: tuple[str, ...] = ()


def parse_type_line(text: str) -> TypeLine:
    """Parse one face's type line; ``TypeLineError`` if it doesn't follow 205."""
    before, dash, after = text.partition(DASH)
    words = before.split()
    supertypes: list[Supertype] = []
    while words and words[0] in _SUPERTYPES:
        supertypes.append(_SUPERTYPES[words.pop(0)])
    if not words:
        raise TypeLineError(f"no card type in {text!r} (205.2a)")
    unknown = [word for word in words if word not in _CARD_TYPES]
    if unknown:
        raise TypeLineError(f"{', '.join(map(repr, unknown))} in {text!r} isn't a card type")
    card_types = tuple(_CARD_TYPES[word] for word in words)
    subtypes: tuple[str, ...] = ()
    if dash:
        subtypes = _subtypes(after.strip(), card_types)
        if not subtypes:
            raise TypeLineError(f"nothing follows the dash in {text!r} (205.3b)")
    return TypeLine(tuple(supertypes), card_types, subtypes)


def _subtypes(text: str, card_types: tuple[CardType, ...]) -> tuple[str, ...]:
    if CardType.PLANE in card_types:
        return (text,) if text else ()
    words = text.split()
    subtypes: list[str] = []
    while words:
        pair = " ".join(words[:2])
        if pair in TWO_WORD_SUBTYPES:
            subtypes.append(pair)
            del words[:2]
        else:
            subtypes.append(words.pop(0))
    return tuple(subtypes)


def try_parse_type_line(text: str) -> TypeLine | None:
    """``parse_type_line``, or ``None`` for a type line that doesn't follow 205."""
    try:
        return parse_type_line(text)
    except TypeLineError:
        return None
