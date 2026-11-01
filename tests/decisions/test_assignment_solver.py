"""The ``ChooseAssignment`` solver (``resolve.decisions.assignment``) and the constraint
``NoneOrAtLeast`` (design.md §17.8, §17.18; M3.4).

``NoneOrAtLeast(choice, minimum)``: the choice is picked by no item or by at least ``minimum``
items (menace, 702.111b: none or two or more blockers). A declaration that breaks a constraint
is illegal (509.1b), so ``ChooseAssignment.validate`` refuses it without the game state, and
``random_legal`` never draws one.
"""

from __future__ import annotations

import pytest

from resolve.decisions.assignment import broken_constraints, random_legal
from resolve.decisions.spaces import (
    Assignment,
    ChooseAssignment,
    NoneOrAtLeast,
    ObjectOption,
    Option,
)
from resolve.errors import InvalidAnswer
from resolve.state.ids import ObjectId
from resolve.state.rng import Rng

ITEMS = tuple(ObjectOption(ObjectId(i)) for i in range(10, 16))
ATTACKERS = tuple(ObjectOption(ObjectId(i)) for i in range(1, 6))
X, Y = ATTACKERS[0], ATTACKERS[1]


def menace_space(items: int, *, maximum: int = 1) -> ChooseAssignment:
    """``items`` blockers, each able to block X and Y (at most ``maximum``), X with menace."""
    return ChooseAssignment(
        ITEMS[:items], ((X, Y),) * items, (maximum,) * items, (NoneOrAtLeast(X, 2),)
    )


def test_none_or_at_least_needs_a_minimum_of_two() -> None:
    """With a minimum of 1 or less the constraint would restrict nothing (every count is "none
    or at least 1"), so building one is an engine bug and raises ``ValueError``."""
    with pytest.raises(ValueError):
        NoneOrAtLeast(X, 1)
    with pytest.raises(ValueError):
        NoneOrAtLeast(X, 0)


def test_validate_refuses_one_pick_of_a_none_or_at_least_two_choice() -> None:
    """X picked by one item is refused; by none, two or three is accepted. Y has no constraint:
    picked by one item it is accepted."""
    space = menace_space(3)
    with pytest.raises(InvalidAnswer):
        space.validate(Assignment(((0,), (), ())))
    with pytest.raises(InvalidAnswer):
        space.validate(Assignment(((), (1,), (0,))))
    for picks in (((), (), ()), ((0,), (0,), ()), ((0,), (0,), (0,)), ((1,), (), ())):
        space.validate(Assignment(picks))


def test_broken_constraints_lists_each_broken_one_in_order() -> None:
    space = ChooseAssignment(
        ITEMS[:3], ((X, Y),) * 3, (2, 2, 2), (NoneOrAtLeast(X, 2), NoneOrAtLeast(Y, 3))
    )
    assert broken_constraints(space, ((0, 1), (), ())) == space.constraints
    assert broken_constraints(space, ((0, 1), (0, 1), ())) == (NoneOrAtLeast(Y, 3),)
    assert broken_constraints(space, ((0, 1), (0, 1), (1,))) == ()
    assert broken_constraints(space, ((), (), ())) == ()


def test_a_constraint_counts_items_by_choice_value_not_index() -> None:
    """X is choice 0 of the first item and choice 1 of the second: picked by both, it is picked
    by two items."""
    space = ChooseAssignment(ITEMS[:2], ((X, Y), (Y, X)), (1, 1), (NoneOrAtLeast(X, 2),))
    space.validate(Assignment(((0,), (1,))))
    with pytest.raises(InvalidAnswer):
        space.validate(Assignment(((0,), (0,))))


def _random_space(rng: Rng) -> ChooseAssignment:
    """A random declaration: 1 to 6 items, each with a random subset of the attackers as its
    choices and a random maximum, and a random set of attackers with menace-like minimums of 2
    or 3."""
    count = 1 + rng.randbelow(len(ITEMS))
    choices: list[tuple[Option, ...]] = []
    maxima: list[int] = []
    for _ in range(count):
        own = tuple(a for a in ATTACKERS if rng.randbelow(3))
        choices.append(own)
        maxima.append(rng.randbelow(len(own) + 1))
    constraints = tuple(
        NoneOrAtLeast(a, 2 + rng.randbelow(2)) for a in ATTACKERS if rng.randbelow(2)
    )
    return ChooseAssignment(ITEMS[:count], tuple(choices), tuple(maxima), constraints)


def test_random_legal_always_satisfies_the_constraints() -> None:
    """Over 400 random boards and 25 draws each, every answer ``random_legal`` gives validates
    (the space's own check: shape, maxima and every constraint)."""
    boards = Rng.from_seed(2026)
    for seed in range(400):
        space = _random_space(boards)
        rng = Rng.from_seed(seed)
        for _ in range(25):
            space.validate(random_legal(space, rng))


def test_random_legal_reaches_blocks_by_several_creatures() -> None:
    """With three blockers and X needing two, the draws include X blocked by two and by three,
    and X unblocked, never X blocked by one: the solver repairs a draw both ways."""
    space = menace_space(3)
    rng = Rng.from_seed(7)
    counts = set[int]()
    for _ in range(300):
        picks = random_legal(space, rng).picks
        counts.add(sum(0 in p for p in picks))
    assert counts == {0, 2, 3}


def test_random_legal_with_no_way_to_fill_clears_the_choice() -> None:
    """Two blockers, X needs three: X is never picked, but Y still is."""
    space = ChooseAssignment(ITEMS[:2], ((X, Y),) * 2, (1, 1), (NoneOrAtLeast(X, 3),))
    rng = Rng.from_seed(8)
    answers = [random_legal(space, rng).picks for _ in range(200)]
    assert all(0 not in p for picks in answers for p in picks)
    assert any(1 in p for picks in answers for p in picks)


def test_random_legal_is_reproducible_from_the_seed() -> None:
    space = menace_space(4, maximum=2)
    first = [random_legal(space, Rng.from_seed(5)) for _ in range(3)]
    again = [random_legal(space, Rng.from_seed(5)) for _ in range(3)]
    assert first == again
