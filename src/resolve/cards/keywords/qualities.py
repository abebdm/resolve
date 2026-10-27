"""Qualities: what protection and "hexproof from" are from (702.16a, 702.11d, design.md §17.11).

A quality is a predicate over the characteristics of the spell, or of the ability's source, that
would target (702.16b) or damage (702.16e) the object or player with the ability. Each one names
its typed words (``ColorWord``, ``SubtypeWord``), so a text-changing effect (M5) can rewrite
"protection from red" into "protection from blue" (612.2).

- ``ColorQuality``: a color (105.2).
- ``MulticoloredQuality`` and ``MonocoloredQuality``: two or more colors, exactly one (105.2b-c).
- ``CardTypeQuality``: a card type (702.16a: a permanent with that type, or a source not on the
  battlefield of that type; the characteristics read are the object's where it is).
- ``SubtypeQuality``: a subtype, in the same way (702.16a).
- ``Everything``: every object, whatever its characteristics (702.16j).

Room is left for a player as the quality (702.16k: "protection from [a player]", whose
"source" is judged by control and ownership, not characteristics) and for a card name
(702.16a: only if the ability says it is a name).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.cards.primitives.words import ColorWord, SubtypeWord
from resolve.data.types import CardType, Color
from resolve.values import Immutable

if TYPE_CHECKING:
    from resolve.effects.characteristics import Characteristics

COLOR_NAMES = {
    Color.WHITE: "white",
    Color.BLUE: "blue",
    Color.BLACK: "black",
    Color.RED: "red",
    Color.GREEN: "green",
}
"""The color words (105.1)."""

# Plurals of subtypes that don't add an "s" (for "protection from Elves").
_IRREGULAR_PLURALS = {
    "Dwarf": "Dwarves",
    "Elf": "Elves",
    "Wolf": "Wolves",
    "Werewolf": "Werewolves",
}


@dataclass(frozen=True)
class Quality(Immutable, ABC):
    """What a protection or "hexproof from" ability is from (702.16a, 702.11d)."""

    @abstractmethod
    def matches(self, characteristics: Characteristics) -> bool:
        """Whether an object with these characteristics has the quality."""

    @property
    @abstractmethod
    def text(self) -> str:
        """The quality as written after "from": ``"red"``, ``"artifacts"``, ``"everything"``."""


@dataclass(frozen=True)
class ColorQuality(Quality):
    """A color (105.2): an object of that color, whatever its other colors."""

    word: ColorWord

    def matches(self, characteristics: Characteristics) -> bool:
        return self.word.color in characteristics.colors

    @property
    def text(self) -> str:
        return COLOR_NAMES[self.word.color]


@dataclass(frozen=True)
class MulticoloredQuality(Quality):
    """Multicolored: two or more colors (105.2c)."""

    def matches(self, characteristics: Characteristics) -> bool:
        return len(characteristics.colors) >= 2

    @property
    def text(self) -> str:
        return "multicolored"


@dataclass(frozen=True)
class MonocoloredQuality(Quality):
    """Monocolored: exactly one color (105.2b)."""

    def matches(self, characteristics: Characteristics) -> bool:
        return len(characteristics.colors) == 1

    @property
    def text(self) -> str:
        return "monocolored"


@dataclass(frozen=True)
class CardTypeQuality(Quality):
    """A card type (702.16a): a permanent with that card type, or a source not on the battlefield
    of that type (an exception to 109.2)."""

    card_type: CardType

    def matches(self, characteristics: Characteristics) -> bool:
        return characteristics.is_a(self.card_type)

    @property
    def text(self) -> str:
        return self.card_type.value.lower() + "s"


@dataclass(frozen=True)
class SubtypeQuality(Quality):
    """A subtype (702.16a), in the same way as a card type."""

    word: SubtypeWord

    def matches(self, characteristics: Characteristics) -> bool:
        return self.word.name in characteristics.subtypes

    @property
    def text(self) -> str:
        name = self.word.name
        return _IRREGULAR_PLURALS.get(name, name + "s")


@dataclass(frozen=True)
class Everything(Quality):
    """Everything (702.16j): every object, regardless of its characteristic values."""

    def matches(self, characteristics: Characteristics) -> bool:
        return True

    @property
    def text(self) -> str:
        return "everything"


def each_color() -> tuple[ColorQuality, ...]:
    """ "Each color" (702.16h, 702.11g): one quality per color, in WUBRG order (105.1)."""
    return tuple(ColorQuality(ColorWord(color)) for color in Color)
