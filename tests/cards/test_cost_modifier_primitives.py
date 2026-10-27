"""The cost-modifier primitives of M2.9, tested on their own: ``ReduceGeneric`` (118.7a),
``SpellCostReduction`` (601.2f) and its text, and the adjective form of qualities.

Their effect on casting is tested with their rules (tests/rules/test_601_2f_cost_modifiers.py)
and cards (test_emerald_medallion_and_kinjallis_caller.py)."""

from __future__ import annotations

import copy
import pickle

import pytest

from resolve.cards.keywords import (
    CardTypeQuality,
    ColorQuality,
    Everything,
    MonocoloredQuality,
    MulticoloredQuality,
    Quality,
    SubtypeQuality,
)
from resolve.cards.primitives.cost_modifiers import (
    ModifierStep,
    ReduceGeneric,
    SpellCostReduction,
)
from resolve.cards.primitives.words import ColorWord, SubtypeWord, rewrite_words
from resolve.data.mana_cost import parse_mana_cost
from resolve.data.types import CardType, Color
from resolve.state.ids import PlayerId
from resolve.state.turn import Phase
from tests.scenario import Scenario

P0, P1 = PlayerId(0), PlayerId(1)
GREEN = ColorQuality(ColorWord(Color.GREEN))
DINOSAUR = SubtypeQuality(SubtypeWord("Dinosaur"))


@pytest.mark.parametrize(
    ("cost", "amount", "total"),
    [
        ("{1}{G}", 1, "{G}"),
        ("{3}{R}", 1, "{2}{R}"),
        ("{G}", 1, "{G}"),  # 118.7a: colored mana isn't reduced
        ("{1}{C}", 2, "{C}"),  # 118.7a: nor colorless mana; the generic part stops at nothing
        ("{2}", 3, "{0}"),  # 601.2f, 118.7: reduced to nothing, it is {0}
        ("{0}", 1, "{0}"),
        ("{4}{U}{U}", 2, "{2}{U}{U}"),
    ],
)
def test_118_7a_reduce_generic_reduces_only_the_generic_part(
    cost: str, amount: int, total: str
) -> None:
    assert ReduceGeneric(amount).apply(parse_mana_cost(cost)) == parse_mana_cost(total)


def test_601_2f_a_reduction_is_applied_after_increases() -> None:
    assert ReduceGeneric(1).step is ModifierStep.REDUCTION
    assert ModifierStep.INCREASE.value < ModifierStep.REDUCTION.value < ModifierStep.TOTAL.value


@pytest.mark.parametrize(
    ("ability", "text"),
    [
        (SpellCostReduction(GREEN), "Green spells you cast cost {1} less to cast."),
        (SpellCostReduction(DINOSAUR), "Dinosaur spells you cast cost {1} less to cast."),
        (
            SpellCostReduction(CardTypeQuality(CardType.ARTIFACT), 2),
            "Artifact spells you cast cost {2} less to cast.",
        ),
        (SpellCostReduction(Everything()), "Spells you cast cost {1} less to cast."),
    ],
)
def test_the_reductions_text(ability: SpellCostReduction, text: str) -> None:
    assert ability.text == text


@pytest.mark.parametrize(
    ("quality", "adjective"),
    [
        (GREEN, "green"),
        (MulticoloredQuality(), "multicolored"),
        (MonocoloredQuality(), "monocolored"),
        (CardTypeQuality(CardType.ARTIFACT), "artifact"),
        (SubtypeQuality(SubtypeWord("Elf")), "Elf"),  # not "Elves": an adjective
        (Everything(), ""),
    ],
)
def test_a_quality_as_an_adjective(quality: Quality, adjective: str) -> None:
    assert quality.adjective == adjective


def test_601_2f_the_reduction_applies_to_its_controllers_spells_with_the_quality() -> None:
    """A green spell P0 casts gets ``ReduceGeneric(1)`` from P0's Medallion ability; a red one,
    and a green spell P1 casts, get nothing."""
    scenario = Scenario(2)
    (medallion,) = scenario.battlefield(P0, ["Emerald Medallion"])
    bears, giant = scenario.stack(P0, ["Grizzly Bears", "Hill Giant"])
    (other,) = scenario.stack(P1, ["Grizzly Bears"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    ability = SpellCostReduction(GREEN)
    assert ability.modifier(state, medallion, bears, P0) == ReduceGeneric(1)
    assert ability.modifier(state, medallion, giant, P0) is None
    assert ability.modifier(state, medallion, other, P1) is None
    assert SpellCostReduction(GREEN, 2).modifier(state, medallion, bears, P0) == ReduceGeneric(2)


def test_612_the_reductions_quality_is_a_typed_word() -> None:
    """A text-changing effect (M5) can make "green spells" "blue spells" (612.2)."""
    changed = rewrite_words(
        SpellCostReduction(GREEN), {ColorWord(Color.GREEN): ColorWord(Color.BLUE)}
    )
    assert changed == SpellCostReduction(ColorQuality(ColorWord(Color.BLUE)))
    assert changed.text == "Blue spells you cast cost {1} less to cast."


def test_cost_modifiers_are_pure_data() -> None:
    for value in (ReduceGeneric(1), SpellCostReduction(DINOSAUR)):
        assert copy.deepcopy(value) == value
        assert pickle.loads(pickle.dumps(value)) == value
