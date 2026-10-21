"""Typed words and rewriting them (612, design.md §17.10).

Every color word, land type and creature or other subtype in a card definition is a typed word,
not a bare string, so a text-changing effect (layer 3, M5) can find the words it changes:

- ``ColorWord``: a color word used as a color (Medallion's "green");
- ``LandTypeWord``: a land type used as a land type;
- ``SubtypeWord``: a creature type or other subtype used as one (Caller's "Dinosaur").

612.2: such an effect changes only words used in the right way, and can't change a card name even
when the name contains one of these words. A card name in a definition is a ``NameRef``, which
``rewrite_words`` never changes. (612.2a: a token-making spell's creature type is also the
token's name; it is written as a ``SubtypeWord``, since the effect changes it as a type.)

``rewrite_words(value, mapping)`` walks any Immutable value (a definition or a part of one) and
replaces each word that is a key of ``mapping``. A word changes into a word of the same kind
(a color word into a color word, 613.1c), so a mapping that crosses kinds is refused. Abilities
that other effects grant aren't part of the definition, so they aren't rewritten (612.3).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass, replace
from typing import Any, cast

from resolve.data.types import Color
from resolve.values import Immutable


@dataclass(frozen=True)
class ColorWord(Immutable):
    """A color word used as a color (612.2)."""

    color: Color


@dataclass(frozen=True)
class LandTypeWord(Immutable):
    """A land type used as a land type, such as "Forest" (612.2, 205.3i)."""

    name: str


@dataclass(frozen=True)
class SubtypeWord(Immutable):
    """A creature type or other subtype used as one, such as "Dinosaur" (612.2, 205.3)."""

    name: str


@dataclass(frozen=True)
class NameRef(Immutable):
    """A card name. No text change can rewrite it (612.2)."""

    name: str


Word = ColorWord | LandTypeWord | SubtypeWord
_WORD_KINDS = (ColorWord, LandTypeWord, SubtypeWord)


def rewrite_words[T](value: T, mapping: Mapping[Word, Word]) -> T:
    """``value`` with each typed word that is a key of ``mapping`` replaced by its image.

    Words are found inside dataclass fields and tuples at any depth; ``NameRef`` and everything
    that isn't a word (strings, numbers, enums) are left alone (612.2). ``value`` itself is
    returned when nothing changes, and is never modified (it is Immutable).

    Raises ``ValueError`` if a word is mapped to a word of another kind (613.1c).
    """
    for old, new in mapping.items():
        if type(old) is not type(new):
            raise ValueError(
                f"{old} can't become {new}: a word changes into a word of the same kind (612.2)"
            )
    return _rewrite(value, mapping)


def _rewrite[T](value: T, mapping: Mapping[Word, Word]) -> T:
    if isinstance(value, _WORD_KINDS):
        return mapping.get(value, value)  # pyright: ignore[reportReturnType]
    if isinstance(value, tuple):
        items = cast("tuple[Any, ...]", value)
        rewritten = tuple(_rewrite(item, mapping) for item in items)
        unchanged = all(new is old for new, old in zip(rewritten, items, strict=True))
        return cast("T", items if unchanged else rewritten)
    if is_dataclass(value) and not isinstance(value, type):
        changes: dict[str, Any] = {}
        for field in fields(value):
            if not field.init:
                continue  # derived in __post_init__
            old = getattr(value, field.name)
            new = _rewrite(old, mapping)
            if new is not old:
                changes[field.name] = new
        return replace(value, **changes) if changes else value
    return value
