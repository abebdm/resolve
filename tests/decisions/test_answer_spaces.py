"""Answer spaces: enumerated and constrained, and their validation (design.md §6)."""

from __future__ import annotations

import pytest

from resolve.decisions.spaces import (
    Amounts,
    AnswerSpace,
    AnswerValue,
    ChooseCounts,
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


def accepts(space: AnswerSpace, value: AnswerValue) -> bool:
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


# --- ChooseCounts ------------------------------------------------------------------------------


def test_601_2h_choose_counts_gives_each_option_up_to_its_maximum() -> None:
    """Pay 2 from two kinds of unit (two of the first, one of the second): (2, 0) and (1, 1)."""
    space = ChooseCounts(THREE[:2], maxima=(2, 1), total=2)
    assert accepts(space, Amounts((2, 0)))
    assert accepts(space, Amounts((1, 1)))
    assert not accepts(space, Amounts((0, 2)))  # more than the second's maximum
    assert not accepts(space, Amounts((1, 0)))  # adds up to 1, not 2
    assert not accepts(space, Amounts((2, 1)))  # adds up to 3
    assert not accepts(space, Amounts((2,)))  # wrong length
    assert not accepts(space, Amounts((1, 1, 0)))
    assert not accepts(space, Amounts((3, -1)))  # negative
    assert not accepts(space, Number(2))  # wrong kind of answer


def test_choose_counts_accepts_only_integers() -> None:
    space = ChooseCounts(THREE[:2], maxima=(2, 1), total=2)
    assert not accepts(space, Amounts((1.0, 1.0)))  # pyright: ignore[reportArgumentType]
    assert not accepts(space, Amounts((True, True)))  # a bool isn't an amount


def test_choose_counts_with_a_total_of_zero_accepts_only_all_zeros() -> None:
    space = ChooseCounts(THREE[:2], maxima=(2, 1), total=0)
    assert accepts(space, Amounts((0, 0)))
    assert not accepts(space, Amounts((1, 0)))


def test_choose_counts_that_cannot_be_satisfied_is_a_bug() -> None:
    with pytest.raises(ValueError, match="total"):
        ChooseCounts(THREE[:2], maxima=(1, 1), total=3)  # sum(maxima) < total
    with pytest.raises(ValueError, match="option"):
        ChooseCounts((), maxima=(), total=0)
    with pytest.raises(ValueError, match="maxima"):
        ChooseCounts(THREE[:2], maxima=(1,), total=1)  # one maximum per option
    with pytest.raises(ValueError, match="negative"):
        ChooseCounts(THREE[:2], maxima=(2, -1), total=1)
    with pytest.raises(ValueError, match="negative"):
        ChooseCounts(THREE[:2], maxima=(2, 1), total=-1)
    assert accepts(ChooseCounts(THREE[:2], maxima=(1, 1), total=2), Amounts((1, 1)))


def test_choose_counts_has_one_valid_answer_per_outcome() -> None:
    """Per-unit options would give several answers for one outcome (design.md 17.7); counts
    don't: the same units are the same tuple."""
    space = ChooseCounts(THREE, maxima=(2, 2, 2), total=3)
    valid = [
        Amounts((a, b, c)) for a in range(3) for b in range(3) for c in range(3)
        if accepts(space, Amounts((a, b, c)))
    ]  # fmt: skip
    assert len(valid) == len(set(valid)) == 7  # compositions of 3 into 3 parts each at most 2


def test_choose_counts_rejects_an_amount_for_an_option_with_maximum_zero() -> None:
    space = ChooseCounts(THREE[:2], maxima=(0, 2), total=1)
    assert accepts(space, Amounts((0, 1)))
    assert not accepts(space, Amounts((1, 0)))


def test_choose_counts_survives_copy_and_pickle() -> None:
    import copy
    import pickle

    space = ChooseCounts(THREE[:2], maxima=(2, 1), total=2)
    assert pickle.loads(pickle.dumps(space)) == space
    assert copy.deepcopy(space) == space
