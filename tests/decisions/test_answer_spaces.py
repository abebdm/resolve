"""Answer spaces: enumerated and constrained, and their validation (design.md §6)."""

from __future__ import annotations

import pytest

from resolve.decisions.spaces import (
    Amounts,
    AnswerValue,
    ChooseNumber,
    ChooseOne,
    ChooseOrder,
    ChooseSubset,
    Distribute,
    Number,
    ObjectOption,
    Order,
    Pick,
    PickMany,
    PlayerOption,
)
from resolve.errors import InvalidAnswer
from resolve.state.ids import ObjectId, PlayerId

THREE = (ObjectOption(ObjectId(10)), ObjectOption(ObjectId(11)), PlayerOption(PlayerId(0)))


def accepts(space: ChooseOne | ChooseSubset | ChooseOrder | ChooseNumber | Distribute,
            value: AnswerValue) -> bool:  # fmt: skip
    try:
        space.validate(value)
    except InvalidAnswer:
        return False
    return True


# --- ChooseOne (enumerated) --------------------------------------------------------------------


def test_choose_one_accepts_each_index_and_nothing_else() -> None:
    space = ChooseOne(THREE)
    assert [accepts(space, Pick(i)) for i in range(-1, 4)] == [False, True, True, True, False]
    assert space.chosen(Pick(2)) == PlayerOption(PlayerId(0))


def test_choose_one_with_a_single_option() -> None:
    space = ChooseOne(THREE[:1])
    assert accepts(space, Pick(0))
    assert not accepts(space, Pick(1))


def test_choose_one_rejects_other_answer_types_and_non_integers() -> None:
    space = ChooseOne(THREE)
    assert not accepts(space, Number(0))
    assert not accepts(space, PickMany((0,)))
    assert not accepts(space, Pick(True))  # a bool isn't an index
    assert not accepts(space, Pick("0"))  # pyright: ignore[reportArgumentType] (deliberately the wrong type)


def test_choose_one_needs_options() -> None:
    with pytest.raises(ValueError, match="at least one option"):
        ChooseOne(())


# --- ChooseSubset ------------------------------------------------------------------------------


def test_choose_subset_bounds_the_number_of_choices() -> None:
    space = ChooseSubset(THREE, 1, 2)
    assert not accepts(space, PickMany(()))
    assert accepts(space, PickMany((1,)))
    assert accepts(space, PickMany((0, 2)))
    assert not accepts(space, PickMany((0, 1, 2)))
    assert space.chosen(PickMany((0, 2))) == (THREE[0], THREE[2])


def test_choose_subset_answers_are_canonical_sorted_and_unique() -> None:
    space = ChooseSubset(THREE, 0, 3)
    assert not accepts(space, PickMany((2, 0)))
    assert not accepts(space, PickMany((1, 1)))
    assert not accepts(space, PickMany((0, 3)))
    assert not accepts(space, PickMany((-1, 0)))
    assert not accepts(space, PickMany([0, 1]))  # pyright: ignore[reportArgumentType] (deliberately the wrong type)
    assert not accepts(space, Pick(0))


def test_choose_subset_of_nothing_with_minimum_zero() -> None:
    space = ChooseSubset((), 0, 0)
    assert accepts(space, PickMany(()))
    assert not accepts(space, PickMany((0,)))


@pytest.mark.parametrize(("minimum", "maximum"), [(-1, 1), (2, 1), (0, 4)])
def test_choose_subset_with_impossible_bounds_is_a_bug(minimum: int, maximum: int) -> None:
    with pytest.raises(ValueError, match="minimum"):
        ChooseSubset(THREE, minimum, maximum)


# --- ChooseOrder -------------------------------------------------------------------------------


def test_choose_order_needs_a_permutation() -> None:
    space = ChooseOrder(THREE)
    assert accepts(space, Order((2, 0, 1)))
    assert accepts(space, Order((0, 1, 2)))
    assert not accepts(space, Order((0, 1)))
    assert not accepts(space, Order((0, 0, 1)))
    assert not accepts(space, Order((0, 1, 2, 3)))
    assert not accepts(space, Order((1, 2, 3)))
    assert space.chosen(Order((2, 0, 1))) == (THREE[2], THREE[0], THREE[1])


def test_choose_order_of_one_option() -> None:
    assert accepts(ChooseOrder(THREE[:1]), Order((0,)))


def test_choose_order_needs_options() -> None:
    with pytest.raises(ValueError, match="at least one option"):
        ChooseOrder(())


# --- ChooseNumber ------------------------------------------------------------------------------


def test_choose_number_within_bounds() -> None:
    space = ChooseNumber(0, 5)
    assert [accepts(space, Number(n)) for n in (-1, 0, 5, 6)] == [False, True, True, False]
    assert not accepts(space, Number(True))
    assert not accepts(space, Number(2.0))  # pyright: ignore[reportArgumentType] (deliberately the wrong type)
    assert not accepts(space, Pick(2))


def test_choose_number_without_an_upper_bound() -> None:
    """X may be any number (107.3a); what can be paid is the asking task's check."""
    space = ChooseNumber(0)
    assert accepts(space, Number(10**9))
    assert not accepts(space, Number(-1))


def test_choose_number_with_a_single_value() -> None:
    assert accepts(ChooseNumber(3, 3), Number(3))
    with pytest.raises(ValueError, match="maximum"):
        ChooseNumber(3, 2)


# --- Distribute --------------------------------------------------------------------------------


def test_601_2d_each_target_receives_at_least_one() -> None:
    space = Distribute(THREE, total=4)
    assert accepts(space, Amounts((2, 1, 1)))
    assert not accepts(space, Amounts((4, 0, 0)))
    assert not accepts(space, Amounts((2, 1, 2)))  # sums to 5
    assert not accepts(space, Amounts((3, 1)))  # one amount missing
    assert not accepts(space, Amounts((1, 1, 1, 1)))
    assert not accepts(space, Number(4))


def test_distribute_with_minimum_zero_allows_empty_shares() -> None:
    space = Distribute(THREE[:2], total=3, minimum_each=0)
    assert accepts(space, Amounts((3, 0)))
    assert accepts(space, Amounts((0, 3)))
    assert not accepts(space, Amounts((4, -1)))


def test_distribute_that_cannot_be_satisfied_is_a_bug() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        Distribute(THREE, total=2)
    with pytest.raises(ValueError, match="recipient"):
        Distribute((), total=0)
    assert accepts(Distribute(THREE, total=3), Amounts((1, 1, 1)))
