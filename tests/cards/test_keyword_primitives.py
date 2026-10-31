"""The primitives of M2.8, tested on their own: qualities (702.16a), the keyword abilities' text,
``CantBeCountered``, the text of ``CounterSpell``, ``ReturnToHand`` and ``TapAll``, and groups
with a controller (``EachCreature.controlled_by``).

Their effect on the game is tested with their rules (tests/rules/test_702_*.py,
test_701_6_counter.py) and cards (test_cryptic_command.py)."""

from __future__ import annotations

import copy
import pickle

import pytest

from resolve.cards.keywords import (
    CardTypeQuality,
    ColorQuality,
    Defender,
    Everything,
    Flash,
    Haste,
    Hexproof,
    Indestructible,
    MonocoloredQuality,
    MulticoloredQuality,
    Protection,
    Quality,
    Shroud,
    SubtypeQuality,
    Vigilance,
    each_color,
    has_keyword,
    keywords,
    protection_from_each_color,
)
from resolve.cards.primitives.effects import CounterSpell, ReturnToHand, TapAll
from resolve.cards.primitives.refs import EachCreature, EachOpponent, Phrasing, TargetRef, You
from resolve.cards.primitives.statics import CantBeCountered
from resolve.cards.primitives.targets import ObjectFilter, SpellFilter, TargetSpec
from resolve.cards.primitives.words import ColorWord, SubtypeWord, rewrite_words
from resolve.data.types import CardType, Color
from resolve.effects import evaluation
from resolve.effects.characteristics import Characteristics
from resolve.effects.evaluation import Context, Timing
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.turn import Phase
from tests.scenario import Scenario

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)
W, U, R = Color.WHITE, Color.BLUE, Color.RED


def chars(
    *colors: Color,
    types: tuple[CardType, ...] = (CardType.INSTANT,),
    subtypes: tuple[str, ...] = (),
) -> Characteristics:
    return Characteristics("Test", (), types, subtypes, colors=colors)


@pytest.mark.parametrize(
    ("quality", "matching", "other"),
    [
        (ColorQuality(ColorWord(R)), chars(R, W), chars(W)),  # 105.2: of that color
        (MulticoloredQuality(), chars(R, W), chars(R)),  # 105.2c: two or more colors
        (MonocoloredQuality(), chars(U), chars()),  # 105.2b: exactly one; colorless isn't
        (MonocoloredQuality(), chars(U), chars(U, W)),
        (CardTypeQuality(CardType.ARTIFACT), chars(types=(CardType.ARTIFACT,)), chars(R)),
        (
            SubtypeQuality(SubtypeWord("Dragon")),
            chars(R, types=(CardType.CREATURE,), subtypes=("Dragon",)),
            chars(R, types=(CardType.CREATURE,), subtypes=("Elf",)),
        ),
    ],
)
def test_702_16a_a_quality_matches_what_has_it(
    quality: Quality, matching: Characteristics, other: Characteristics
) -> None:
    assert quality.matches(matching)
    assert not quality.matches(other)


def test_702_16j_everything_matches_every_object() -> None:
    for characteristics_ in (chars(), chars(R), chars(types=(CardType.LAND,))):
        assert Everything().matches(characteristics_)


def test_the_abilities_text() -> None:
    red = ColorQuality(ColorWord(R))
    assert [a.text for a in (Flash(), Shroud(), Indestructible(), Hexproof())] == [
        "Flash", "Shroud", "Indestructible", "Hexproof",
    ]  # fmt: skip
    assert [a.text for a in (Haste(), Vigilance(), Defender())] == [
        "Haste", "Vigilance", "Defender",
    ]  # fmt: skip
    assert Hexproof(red).text == "Hexproof from red"
    assert Protection(red).text == "Protection from red"
    assert Protection(CardTypeQuality(CardType.ARTIFACT)).text == "Protection from artifacts"
    assert Protection(MulticoloredQuality()).text == "Protection from multicolored"
    assert Protection(MonocoloredQuality()).text == "Protection from monocolored"
    assert Protection(Everything()).text == "Protection from everything"
    assert Protection(SubtypeQuality(SubtypeWord("Elf"))).text == "Protection from Elves"
    assert Protection(SubtypeQuality(SubtypeWord("Dragon"))).text == "Protection from Dragons"
    assert CantBeCountered().text == "This spell can't be countered."


def test_702_16h_each_color_is_five_qualities_in_wubrg_order() -> None:
    assert [q.word.color for q in each_color()] == list(Color)
    assert len(protection_from_each_color()) == 5


def test_612_a_quality_is_a_typed_word_a_text_change_rewrites() -> None:
    """Protection from red becomes protection from blue under a color-word change (612.2)."""
    red, blue = ColorWord(R), ColorWord(U)
    assert rewrite_words(Protection(ColorQuality(red)), {red: blue}) == Protection(
        ColorQuality(blue)
    )


def test_keyword_values_are_pure_data() -> None:
    values = (
        *protection_from_each_color(),
        Hexproof(MulticoloredQuality()),
        CantBeCountered(),
        TapAll(EachCreature(controlled_by=EachOpponent())),
    )
    assert copy.deepcopy(values) == values
    assert pickle.loads(pickle.dumps(values)) == values


def test_has_keyword_and_keywords() -> None:
    red = Protection(ColorQuality(ColorWord(R)))
    with_abilities = Characteristics("Test", (), (CardType.CREATURE,), (), (Flash(), red, Flash()))
    assert has_keyword(with_abilities, Flash) and not has_keyword(with_abilities, Shroud)
    assert keywords(with_abilities, Flash) == (Flash(), Flash())
    assert keywords(with_abilities, Protection) == (red,)


def test_the_effects_text() -> None:
    spell, permanent = TargetSpec(spells=SpellFilter()), TargetSpec(objects=ObjectFilter())
    it = TargetRef(0)
    assert CounterSpell((it,)).describe(Phrasing((spell,))) == "counter target spell"
    assert (
        ReturnToHand((it,)).describe(Phrasing((permanent,)))
        == "return target permanent to its owner's hand"
    )
    tap = {
        None: "tap all creatures",
        You(): "tap all creatures you control",
        EachOpponent(): "tap all creatures your opponents control",
    }
    for group, text in tap.items():
        assert TapAll(EachCreature(controlled_by=group)).describe(Phrasing(())) == text


def test_608_2h_a_group_with_a_controller() -> None:
    """In three players, "creatures you control" (``You``) is P1's creatures for P1's spell, and
    "creatures your opponents control" (``EachOpponent``, 102.2) P0's and P2's, in battlefield
    order; noncreatures are never in the group."""
    scenario = Scenario(3)
    (bears,) = scenario.battlefield(P0, ["Grizzly Bears"])
    lions, _ = scenario.battlefield(P1, ["Savannah Lions", "Sol Ring"])
    (giant,) = scenario.battlefield(P2, ["Hill Giant"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    context = Context(Timing.RESOLUTION, ObjectId(999), P1)
    mine = EachCreature(controlled_by=You())
    theirs = EachCreature(controlled_by=EachOpponent())
    assert evaluation.each_creature(state, mine, context) == (lions,)
    assert evaluation.each_creature(state, theirs, context) == (bears, giant)
    assert evaluation.each_creature(state, EachCreature(), context) == (bears, lions, giant)
