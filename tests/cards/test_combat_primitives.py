"""The primitives of M3.4, tested on their own: the evasion keywords and reach (702.9, 702.13,
702.14, 702.17, 702.36, 702.111), landwalk's quality (``LandTypeQuality``, 702.14a), a player as
the quality of protection (``PlayerQuality``, 702.16k: tested in tests/rules/
test_702_16_protection.py), and the combat statics ``CantBeBlocked`` and
``PowerBlockRestriction`` (509.1b).

Their effect on blocks is tested with their rules: tests/rules/test_702_9_flying_and_reach.py,
test_702_111_menace.py, test_702_13_14_36_retired_evasion.py and test_509_1b_restrictions.py.
"""

from __future__ import annotations

import copy
import pickle

from resolve.cards.keywords import (
    CardTypeQuality,
    Fear,
    Flying,
    Intimidate,
    LandTypeQuality,
    Landwalk,
    Menace,
    PlayerQuality,
    Protection,
    Reach,
)
from resolve.cards.primitives.combat import CantBeBlocked, PowerBlockRestriction
from resolve.cards.primitives.words import LandTypeWord, rewrite_words
from resolve.data.types import CardType
from resolve.effects.characteristics import Characteristics
from resolve.state.ids import PlayerId

SWAMP, ISLAND = LandTypeWord("Swamp"), LandTypeWord("Island")


def land(*subtypes: str, types: tuple[CardType, ...] = (CardType.LAND,)) -> Characteristics:
    return Characteristics("Test", (), types, subtypes)


def test_the_abilities_text() -> None:
    assert [a.text for a in (Flying(), Reach(), Menace(), Intimidate(), Fear())] == [
        "Flying", "Reach", "Menace", "Intimidate", "Fear",
    ]  # fmt: skip
    assert Landwalk(LandTypeQuality(SWAMP)).text == "Swampwalk"
    assert Landwalk(LandTypeQuality(LandTypeWord("Forest"))).text == "Forestwalk"
    assert Landwalk(CardTypeQuality(CardType.ARTIFACT)).text == "Artifact landwalk"
    assert CantBeBlocked().text == "This creature can't be blocked."
    assert PowerBlockRestriction().text == (
        "Creatures with power less than this creature's power can't block creatures you control."
    )


def test_702_14a_a_land_type_quality_matches_lands_of_that_type() -> None:
    """Swamp matches a land with the subtype Swamp (a basic Swamp, or a nonbasic like a dual
    land with Swamp among its types) and not an Island."""
    swamp = LandTypeQuality(SWAMP)
    assert swamp.matches(land("Swamp"))
    assert swamp.matches(land("Island", "Swamp"))
    assert not swamp.matches(land("Island"))
    assert not swamp.matches(land())
    assert swamp.text == "Swamps" and swamp.adjective == "Swamp"


def test_612_2_a_text_change_rewrites_swampwalk_into_islandwalk() -> None:
    """Landwalk's land type is a typed word (612.2): changing "Swamp" to "Island" makes swampwalk
    islandwalk."""
    rewritten = rewrite_words(Landwalk(LandTypeQuality(SWAMP)), {SWAMP: ISLAND})
    assert rewritten == Landwalk(LandTypeQuality(ISLAND))
    assert rewritten.text == "Islandwalk"


def test_a_quality_of_characteristics_judges_a_source_by_them_alone() -> None:
    """``matches_source`` is ``matches`` for every quality but a player's: control and
    ownership don't matter."""
    swamp = LandTypeQuality(SWAMP)
    assert swamp.matches_source(land("Swamp"), PlayerId(0), PlayerId(1))
    assert not swamp.matches_source(land("Island"), None, PlayerId(0))


def test_the_values_are_pure_data() -> None:
    values = (
        Flying(),
        Reach(),
        Menace(),
        Intimidate(),
        Fear(),
        Landwalk(LandTypeQuality(SWAMP)),
        Protection(PlayerQuality(PlayerId(2))),
        CantBeBlocked(),
        PowerBlockRestriction(),
    )
    assert copy.deepcopy(values) == values
    assert pickle.loads(pickle.dumps(values)) == values
