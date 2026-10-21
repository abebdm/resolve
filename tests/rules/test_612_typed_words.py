"""612.2: typed words, and ``rewrite_words``, the walk a text-changing effect (M5) will use.

From the pinned CR:

- 612.2: a text-changing effect changes only words used in the correct way: a color word as a
  color word, a land type as a land type, a creature type as a creature type. It can't change a
  card name, even one containing such a word. Hence ``NameRef`` is never rewritten.
- 612.2a: a token-making spell's creature type is both a type and the token's name; it is
  written as a ``SubtypeWord``, so a change applies.
- 612.3: abilities granted by other effects aren't rewritten: a rewrite changes only the value
  it is given.
- A color word changes to a color word, a land type to a land type (613.1c): a mapping between
  different kinds of word is a bug.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from resolve.cards.primitives.words import (
    ColorWord,
    LandTypeWord,
    NameRef,
    SubtypeWord,
    Word,
    rewrite_words,
)
from resolve.data.types import Color
from resolve.values import Immutable
from tests.state.test_immutability import type_problems

WHITE, BLUE = ColorWord(Color.WHITE), ColorWord(Color.BLUE)
FOREST, ISLAND = LandTypeWord("Forest"), LandTypeWord("Island")
DINOSAUR, ELF = SubtypeWord("Dinosaur"), SubtypeWord("Elf")


@dataclass(frozen=True)
class Leaf(Immutable):
    color: ColorWord
    land: LandTypeWord | None = None


@dataclass(frozen=True)
class Spell(Immutable):
    """A made-up definition fragment with words nested in fields and tuples."""

    name: NameRef
    leaves: tuple[Leaf, ...]
    creature: SubtypeWord
    amount: int = 0
    note: str = "white forest"  # plain text isn't a typed word


def spell() -> Spell:
    return Spell(
        NameRef("Forest Dinosaur"),
        (Leaf(WHITE, FOREST), Leaf(BLUE)),
        DINOSAUR,
        amount=3,
    )


def test_612_2_rewrite_words_changes_typed_words_but_not_names() -> None:
    mapping: dict[Word, Word] = {WHITE: BLUE, FOREST: ISLAND, DINOSAUR: ELF}
    assert rewrite_words(spell(), mapping) == Spell(
        NameRef("Forest Dinosaur"),  # 612.2: the name contains two mapped words and is unchanged
        (Leaf(BLUE, ISLAND), Leaf(BLUE)),
        ELF,
        amount=3,
    )


def test_612_2_a_word_is_changed_only_as_the_kind_it_is_used_as() -> None:
    """A mapping of the land type Forest doesn't touch the creature type "Forest" (a made-up
    one) and vice versa: the kinds are different words."""
    fake = SubtypeWord("Forest")
    value = (FOREST, fake)
    assert rewrite_words(value, {FOREST: ISLAND}) == (ISLAND, fake)
    assert rewrite_words(value, {fake: ELF}) == (FOREST, ELF)


def test_612_2_a_name_is_never_rewritten_whatever_the_mapping() -> None:
    names = (NameRef("Blue Elemental"), NameRef("Plains Walker"))
    assert rewrite_words(names, {BLUE: WHITE, LandTypeWord("Plains"): ISLAND}) == names


def test_rewrite_words_with_no_matching_word_returns_the_value_itself() -> None:
    value = spell()
    assert rewrite_words(value, {ColorWord(Color.RED): BLUE}) is value
    assert rewrite_words(value, {}) is value


def test_rewrite_words_leaves_the_original_unchanged() -> None:
    value = spell()
    rewrite_words(value, {WHITE: BLUE})
    assert value == spell()


def test_rewrite_words_reaches_a_bare_word_and_a_tuple() -> None:
    assert rewrite_words(WHITE, {WHITE: BLUE}) == BLUE
    assert rewrite_words((WHITE, (FOREST,)), {WHITE: BLUE, FOREST: ISLAND}) == (BLUE, (ISLAND,))
    assert rewrite_words((), {WHITE: BLUE}) == ()


def test_a_mapping_between_different_kinds_of_word_is_refused() -> None:
    with pytest.raises(ValueError, match="same kind"):
        rewrite_words(spell(), {WHITE: ISLAND})
    with pytest.raises(ValueError, match="same kind"):
        rewrite_words(spell(), {DINOSAUR: FOREST})


def test_a_word_maps_to_the_same_word_is_a_no_change() -> None:
    value = spell()
    assert rewrite_words(value, {WHITE: WHITE}) == value


@pytest.mark.parametrize(
    "annotation",
    [list[ColorWord], dict[str, ColorWord], set[SubtypeWord], frozenset[LandTypeWord]],
)
def test_a_definition_cant_hide_words_in_a_collection_the_walk_skips(annotation: object) -> None:
    """``rewrite_words`` walks dataclass fields and tuples. Immutable values may hold nothing
    else (lists, dicts and sets are refused by the immutability check), so no word in a
    definition is out of its reach."""
    assert type_problems(annotation)
    assert not type_problems(tuple[ColorWord, ...])
