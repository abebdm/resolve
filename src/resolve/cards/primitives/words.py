"""Typed words (612). STUB: M2.2 tests-first checkpoint."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from resolve.data.types import Color
from resolve.errors import NotImplementedRule
from resolve.values import Immutable


@dataclass(frozen=True)
class ColorWord(Immutable):
    """A color word used as a color (612.2)."""

    color: Color


@dataclass(frozen=True)
class LandTypeWord(Immutable):
    """A land type used as a land type (612.2)."""

    name: str


@dataclass(frozen=True)
class SubtypeWord(Immutable):
    """A creature type or other subtype used as one (612.2)."""

    name: str


@dataclass(frozen=True)
class NameRef(Immutable):
    """A card name; no text change can rewrite it (612.2)."""

    name: str


Word = ColorWord | LandTypeWord | SubtypeWord


def rewrite_words[T](value: T, mapping: Mapping[Word, Word]) -> T:
    """``value`` with each typed word in ``mapping`` replaced (612.1, 612.2)."""
    raise NotImplementedRule("612.2: rewrite_words")
