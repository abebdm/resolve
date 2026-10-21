"""Mana costs and mana symbols (107.4, 202). STUB: M2.2 tests-first checkpoint."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from resolve.data.types import Color
from resolve.errors import NotImplementedRule
from resolve.values import Immutable


class ManaCostError(ValueError):
    """A mana cost that doesn't follow 107.4."""


class SymbolKind(Enum):
    """The kinds of mana symbol of 107.4."""

    COLORED = "colored"
    COLORLESS = "colorless"
    GENERIC = "generic"
    VARIABLE = "variable"
    HYBRID = "hybrid"
    MONOCOLORED_HYBRID = "monocolored hybrid"
    COLORLESS_HYBRID = "colorless hybrid"
    PHYREXIAN = "Phyrexian"
    HYBRID_PHYREXIAN = "hybrid Phyrexian"
    SNOW = "snow"


@dataclass(frozen=True)
class ManaSymbol(Immutable):
    """One mana symbol."""

    kind: SymbolKind
    colors: tuple[Color, ...] = ()
    number: int = 0

    @property
    def text(self) -> str:
        """The symbol as printed, such as ``"{2/W}"``."""
        raise NotImplementedRule("107.4: ManaSymbol.text")

    def mana_value(self, x: int = 0) -> int:
        """What the symbol adds to a mana value (202.3)."""
        raise NotImplementedRule("202.3: ManaSymbol.mana_value")


@dataclass(frozen=True)
class ManaCost(Immutable):
    """A mana cost: its symbols in printed order (202.1)."""

    symbols: tuple[ManaSymbol, ...]

    @property
    def text(self) -> str:
        """The cost as printed, such as ``"{3}{R}"``."""
        raise NotImplementedRule("107.4: ManaCost.text")

    @property
    def colors(self) -> tuple[Color, ...]:
        """The colors of the symbols in the cost (202.2), in WUBRG order."""
        raise NotImplementedRule("202.2: ManaCost.colors")

    def mana_value(self, x: int = 0) -> int:
        """The mana value of an object with this cost (202.3)."""
        raise NotImplementedRule("202.3: ManaCost.mana_value")


def parse_mana_cost(text: str) -> ManaCost:
    """Parse Scryfall's text for a mana cost; ``ManaCostError`` if it doesn't follow 107.4."""
    raise NotImplementedRule("107.4: parse_mana_cost")
