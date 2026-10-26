"""Mana costs and mana symbols (107.4, 202).

A mana cost is the string of mana symbols printed in a card's top right (202.1), for example
``"{3}{R}"``. ``parse_mana_cost`` turns Scryfall's text into a ``ManaCost``: a tuple of
``ManaSymbol`` values in printed order. Every kind of symbol 107.4 lists is represented:

| Kind                  | Symbols                | Represents                              |
|-----------------------|------------------------|-----------------------------------------|
| ``COLORED``           | ``{W}{U}{B}{R}{G}``    | one mana of that color (107.4a)         |
| ``COLORLESS``         | ``{C}``                | one colorless mana (107.4c)             |
| ``GENERIC``           | ``{0}{1}{2}...``       | that much generic mana (107.4b, d)      |
| ``VARIABLE``          | ``{X}``                | generic mana, X chosen (107.3, 107.4b)  |
| ``HYBRID``            | ``{W/U}``, 9 more      | either color (107.4e)                   |
| ``MONOCOLORED_HYBRID``| ``{2/W}`` to ``{2/G}`` | one mana of the color or 2 generic      |
| ``COLORLESS_HYBRID``  | ``{C/W}`` to ``{C/G}`` | one mana of the color or one {C}        |
| ``PHYREXIAN``         | ``{W/P}`` to ``{G/P}`` | one mana of the color or 2 life (107.4f)|
| ``HYBRID_PHYREXIAN``  | ``{W/U/P}``, 9 more    | one mana of either color or 2 life      |
| ``SNOW``              | ``{S}``                | one mana from a snow source (107.4h)    |

107.4 groups ``{C/W}`` ... ``{C/G}`` with the monocolored hybrid symbols; here they have their own
kind because the alternative is one colorless mana rather than generic mana.

The symbols only describe the cost. How each is paid (hybrid and Phyrexian choices, snow) is the
payment's business (601.2f-h; M2.3 for the mana part, M9 for hybrid, Phyrexian and snow).

A cost that doesn't follow 107.4 raises ``ManaCostError``. The card data contains a few such
costs (Un-set half-mana symbols and the like); loading them is fine, and only using such a card in
a game is refused (``CardFace.cost`` is then ``None``; docs/decisions.md).

``None`` is also the cost of a card with no mana cost (a land, a back face; 202.3a), which is not
the same as a cost of ``{0}``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from resolve.data.types import Color
from resolve.values import Immutable

# 107.4: the hybrid symbols, as the CR lists them (the order within a symbol is part of it).
HYBRID_PAIRS = (
    (Color.WHITE, Color.BLUE),
    (Color.WHITE, Color.BLACK),
    (Color.BLUE, Color.BLACK),
    (Color.BLUE, Color.RED),
    (Color.BLACK, Color.RED),
    (Color.BLACK, Color.GREEN),
    (Color.RED, Color.GREEN),
    (Color.RED, Color.WHITE),
    (Color.GREEN, Color.WHITE),
    (Color.GREEN, Color.BLUE),
)
# 107.4e: the generic alternative of a monocolored hybrid symbol such as {2/W}.
MONOCOLORED_HYBRID_GENERIC = 2

_COLORS = {color.value: color for color in Color}
_HYBRIDS = {f"{a.value}/{b.value}": (a, b) for a, b in HYBRID_PAIRS}
_COST = re.compile(r"(?:\{[^{}]*\})+")
_SYMBOL = re.compile(r"\{([^{}]*)\}")
_NUMBER = re.compile(r"0|[1-9][0-9]*")


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
    """One mana symbol (107.4).

    ``colors`` are the colors the symbol is (202.2a, 202.2d; 107.4e: a hybrid symbol is all of
    its components' colors, and so is a Phyrexian symbol, 107.4f); none for generic, {X}, {C}
    and {S}. ``number`` is the amount of a generic symbol, and the generic alternative of a
    monocolored hybrid symbol (2 in ``{2/W}``; 1 for the colorless alternative of ``{C/W}``).
    """

    kind: SymbolKind
    colors: tuple[Color, ...] = ()
    number: int = 0

    @property
    def text(self) -> str:
        """The symbol as printed, such as ``"{2/W}"``."""
        letters = [color.value for color in self.colors]
        match self.kind:
            case SymbolKind.COLORED:
                body = letters[0]
            case SymbolKind.COLORLESS:
                body = "C"
            case SymbolKind.GENERIC:
                body = str(self.number)
            case SymbolKind.VARIABLE:
                body = "X"
            case SymbolKind.HYBRID:
                body = "/".join(letters)
            case SymbolKind.MONOCOLORED_HYBRID:
                body = f"{self.number}/{letters[0]}"
            case SymbolKind.COLORLESS_HYBRID:
                body = f"C/{letters[0]}"
            case SymbolKind.PHYREXIAN | SymbolKind.HYBRID_PHYREXIAN:
                body = "/".join([*letters, "P"])
            case SymbolKind.SNOW:
                body = "S"
        return "{" + body + "}"

    def mana_value(self, x: int = 0) -> int:
        """What the symbol adds to a mana value (202.3): its amount of mana, a hybrid symbol's
        largest component (202.3f), 1 for a Phyrexian symbol (202.3g) and ``x`` for {X} (202.3e:
        0 unless the object is on the stack)."""
        match self.kind:
            case SymbolKind.GENERIC | SymbolKind.MONOCOLORED_HYBRID:
                return self.number
            case SymbolKind.VARIABLE:
                return x
            case _:
                return 1


@dataclass(frozen=True)
class ManaCost(Immutable):
    """A mana cost: its symbols in printed order (202.1). It always has at least one symbol."""

    symbols: tuple[ManaSymbol, ...]

    def __post_init__(self) -> None:
        if not self.symbols:
            raise ValueError("a mana cost has at least one symbol (202.3a: no cost is None)")

    @property
    def text(self) -> str:
        """The cost as printed, such as ``"{3}{R}"``."""
        return "".join(symbol.text for symbol in self.symbols)

    @property
    def colors(self) -> tuple[Color, ...]:
        """The colors of the symbols in the cost (202.2), once each, in WUBRG order (105.1)."""
        present = {color for symbol in self.symbols for color in symbol.colors}
        return tuple(color for color in Color if color in present)

    def mana_value(self, x: int = 0) -> int:
        """The mana value of an object with this cost (202.3): the total amount of mana in it,
        with ``x`` for each {X} (202.3e)."""
        return sum(symbol.mana_value(x) for symbol in self.symbols)

    @property
    def has_x(self) -> bool:
        """Whether the cost has an {X} (107.3a)."""
        return any(symbol.kind is SymbolKind.VARIABLE for symbol in self.symbols)

    def with_x(self, x: int) -> ManaCost:
        """This cost with the announced value ``x`` in place of each {X} (107.3a, 601.2f)."""
        raise NotImplementedError("107.3a")


def parse_mana_cost(text: str) -> ManaCost:
    """Parse Scryfall's text for a mana cost; ``ManaCostError`` if it doesn't follow 107.4.

    Empty text is refused: a card with no mana cost has no ``ManaCost`` at all (202.3a).
    """
    if not _COST.fullmatch(text):
        raise ManaCostError(f"{text!r} is not a string of mana symbols (107.4)")
    return ManaCost(tuple(_parse_symbol(body) for body in _SYMBOL.findall(text)))


def _parse_symbol(body: str) -> ManaSymbol:
    if body in _COLORS:
        return ManaSymbol(SymbolKind.COLORED, (_COLORS[body],))
    if _NUMBER.fullmatch(body):
        return ManaSymbol(SymbolKind.GENERIC, (), int(body))
    simple = {"C": SymbolKind.COLORLESS, "X": SymbolKind.VARIABLE, "S": SymbolKind.SNOW}
    if body in simple:
        return ManaSymbol(simple[body])
    parts = body.split("/")
    if len(parts) == 2:
        first, second = parts
        if first == str(MONOCOLORED_HYBRID_GENERIC) and second in _COLORS:
            return ManaSymbol(
                SymbolKind.MONOCOLORED_HYBRID, (_COLORS[second],), MONOCOLORED_HYBRID_GENERIC
            )
        if first == "C" and second in _COLORS:
            return ManaSymbol(SymbolKind.COLORLESS_HYBRID, (_COLORS[second],), 1)
        if second == "P" and first in _COLORS:
            return ManaSymbol(SymbolKind.PHYREXIAN, (_COLORS[first],))
        if body in _HYBRIDS:
            return ManaSymbol(SymbolKind.HYBRID, _HYBRIDS[body])
    elif len(parts) == 3 and parts[2] == "P" and "/".join(parts[:2]) in _HYBRIDS:
        return ManaSymbol(SymbolKind.HYBRID_PHYREXIAN, _HYBRIDS["/".join(parts[:2])])
    raise ManaCostError(f"{{{body}}} is not a mana symbol (107.4)")
