"""RandomAgent: uniformly random answers inside every answer space (design.md §6, §14)."""

from __future__ import annotations

from collections import Counter

import pytest

from resolve.agents.random_agent import DEFAULT_UNBOUNDED_SPAN, RandomAgent
from resolve.decisions.spaces import (
    Amounts,
    AnswerSpace,
    ChooseCounts,
    ChooseNumber,
    ChooseOne,
    ChooseOrder,
    ChooseSubset,
    Distribute,
    Number,
    Order,
    Pick,
    PickMany,
    PlayerOption,
)
from resolve.engine.api import view_for
from resolve.state.ids import PlayerId
from resolve.state.rng import Rng
from tests.game_fixtures import request_of, start

OPTIONS = tuple(PlayerOption(PlayerId(p)) for p in range(4))
SPACES: list[AnswerSpace] = [
    ChooseOne(OPTIONS),
    ChooseOne(OPTIONS[:1]),
    ChooseSubset(OPTIONS, 0, 4),
    ChooseSubset(OPTIONS, 2, 2),
    ChooseSubset(OPTIONS, 0, 0),
    ChooseSubset((), 0, 0),
    ChooseOrder(OPTIONS),
    ChooseOrder(OPTIONS[:1]),
    ChooseNumber(0, 0),
    ChooseNumber(-3, 3),
    ChooseNumber(5),
    Distribute(OPTIONS[:3], 7),
    Distribute(OPTIONS[:3], 3),
    Distribute(OPTIONS[:1], 4),
    Distribute(OPTIONS[:2], 5, minimum_each=0),
    Distribute(OPTIONS[:2], 0, minimum_each=0),
    ChooseCounts(OPTIONS[:3], (2, 2, 2), 3),
    ChooseCounts(OPTIONS[:2], (2, 1), 2),
    ChooseCounts(OPTIONS[:2], (2, 1), 0),
    ChooseCounts(OPTIONS[:1], (5,), 5),
]

SAMPLES = 2000

# Critical values of the chi-square distribution at p = 0.001, by degrees of freedom (standard
# tables). A uniform sampler exceeds them one time in a thousand; the seeds are fixed, so the
# tests are deterministic, and a biased sampler (see the naive-shuffle test) exceeds them by far.
CHI_SQUARE_0_001 = {3: 16.266, 4: 18.467, 5: 20.515, 6: 22.458, 14: 36.123, 23: 49.728}


def chi_square(counts: Counter[object], categories: int) -> float:
    """Pearson's chi-square statistic of ``counts`` against a uniform distribution."""
    total = sum(counts.values())
    expected = total / categories
    observed = list(counts.values()) + [0] * (categories - len(counts))
    return sum((count - expected) ** 2 / expected for count in observed)


def assert_uniform(counts: Counter[object], categories: int) -> None:
    assert len(counts) == categories, f"only {len(counts)} of {categories} outcomes reached"
    statistic = chi_square(counts, categories)
    assert statistic < CHI_SQUARE_0_001[categories - 1], f"chi-square {statistic:.1f}"


@pytest.mark.parametrize("space", SPACES, ids=repr)
def test_every_random_answer_is_inside_the_space(space: AnswerSpace) -> None:
    agent = RandomAgent(seed=7)
    for _ in range(200):
        space.validate(agent.random_value(space))  # raises InvalidAnswer if it isn't


def test_choose_one_is_uniform_over_the_options() -> None:
    agent = RandomAgent(seed=1)
    counts = Counter[object](agent.random_value(ChooseOne(OPTIONS)) for _ in range(SAMPLES))
    assert set(counts) == {Pick(i) for i in range(4)}
    assert_uniform(counts, 4)


def test_choose_subset_is_uniform_over_sizes_and_reaches_every_subset() -> None:
    """Sizes 0..4 are equally likely; 2**4 = 16 subsets in all."""
    agent = RandomAgent(seed=2)
    answers = [agent.random_value(ChooseSubset(OPTIONS, 0, 4)) for _ in range(SAMPLES)]
    assert len(set(answers)) == 16
    sizes = Counter[object](
        len(answer.indices) for answer in answers if isinstance(answer, PickMany)
    )
    assert sorted(sizes) == [0, 1, 2, 3, 4]  # pyright: ignore[reportArgumentType]
    assert_uniform(sizes, 5)


def test_choose_subset_of_a_fixed_size_is_uniform_over_subsets() -> None:
    """C(4, 2) = 6 subsets of size 2."""
    agent = RandomAgent(seed=3)
    counts = Counter[object](
        agent.random_value(ChooseSubset(OPTIONS, 2, 2)) for _ in range(SAMPLES)
    )
    assert_uniform(counts, 6)


def test_choose_order_is_uniform_over_permutations() -> None:
    """4! = 24 permutations."""
    agent = RandomAgent(seed=4)
    counts = Counter[object](agent.random_value(ChooseOrder(OPTIONS)) for _ in range(SAMPLES * 3))
    assert all(isinstance(answer, Order) for answer in counts)
    assert_uniform(counts, 24)


def test_the_uniformity_check_catches_a_naive_shuffle() -> None:
    """The classic bug: swapping each position with *any* position gives 4**4 = 256 equally
    likely swap sequences for 24 permutations, so some permutations come up almost twice as
    often as others. The chi-square check must reject that."""
    rng = Rng.from_seed(4)
    counts: Counter[object] = Counter()
    for _ in range(SAMPLES * 3):
        items = list(range(4))
        for i in range(4):
            j = rng.randbelow(4)
            items[i], items[j] = items[j], items[i]
        counts[tuple(items)] += 1
    assert len(counts) == 24
    assert chi_square(counts, 24) > CHI_SQUARE_0_001[23]


def test_choose_number_is_uniform_over_the_range() -> None:
    agent = RandomAgent(seed=5)
    counts = Counter[object](agent.random_value(ChooseNumber(-3, 3)) for _ in range(SAMPLES))
    assert set(counts) == {Number(n) for n in range(-3, 4)}
    assert_uniform(counts, 7)


def test_an_unbounded_number_is_capped_at_minimum_plus_the_span() -> None:
    agent = RandomAgent(seed=6, unbounded_span=3)
    values = {agent.random_value(ChooseNumber(5)) for _ in range(500)}
    assert values == {Number(5), Number(6), Number(7), Number(8)}
    assert DEFAULT_UNBOUNDED_SPAN == 20


def test_distribute_is_uniform_over_divisions() -> None:
    """7 among 3 with at least 1 each: C(6, 2) = 15 divisions (stars and bars)."""
    agent = RandomAgent(seed=8)
    counts = Counter[object](
        agent.random_value(Distribute(OPTIONS[:3], 7)) for _ in range(SAMPLES * 3)
    )
    assert Amounts((5, 1, 1)) in counts and Amounts((1, 1, 5)) in counts
    assert_uniform(counts, 15)


def test_distribute_with_no_spare_gives_each_recipient_the_minimum() -> None:
    agent = RandomAgent(seed=9)
    assert agent.random_value(Distribute(OPTIONS[:3], 3)) == Amounts((1, 1, 1))
    assert agent.random_value(Distribute(OPTIONS[:1], 4)) == Amounts((4,))
    assert agent.random_value(Distribute(OPTIONS[:2], 0, minimum_each=0)) == Amounts((0, 0))


def test_choose_counts_is_uniform_over_the_valid_answers() -> None:
    """3 among three kinds of unit with at most 2 of each: 10 divisions minus the 3 that give
    one kind all 3 = 7 answers."""
    agent = RandomAgent(seed=10)
    space = ChooseCounts(OPTIONS[:3], (2, 2, 2), 3)
    counts = Counter[object](agent.random_value(space) for _ in range(SAMPLES * 3))
    assert set(counts) == {
        Amounts(a)
        for a in [(2, 1, 0), (2, 0, 1), (1, 2, 0), (0, 2, 1), (1, 0, 2), (0, 1, 2), (1, 1, 1)]
    }
    assert_uniform(counts, 7)


def test_choose_counts_respects_the_maxima() -> None:
    agent = RandomAgent(seed=13)
    space = ChooseCounts(OPTIONS[:2], (2, 1), 2)
    assert {agent.random_value(space) for _ in range(200)} == {Amounts((2, 0)), Amounts((1, 1))}


def test_choose_counts_with_one_answer_gives_it() -> None:
    agent = RandomAgent(seed=14)
    assert agent.random_value(ChooseCounts(OPTIONS[:2], (2, 1), 0)) == Amounts((0, 0))
    assert agent.random_value(ChooseCounts(OPTIONS[:1], (5,), 5)) == Amounts((5,))
    assert agent.random_value(ChooseCounts(OPTIONS[:2], (1, 1), 2)) == Amounts((1, 1))


def test_the_same_seed_gives_the_same_answers() -> None:
    first, second, other = RandomAgent(11), RandomAgent(11), RandomAgent(12)
    run = [first.random_value(space) for space in SPACES * 5]
    assert run == [second.random_value(space) for space in SPACES * 5]
    assert run != [other.random_value(space) for space in SPACES * 5]


def test_decide_answers_the_request_for_its_player() -> None:
    state = start(3)
    request = request_of(state)
    answer = RandomAgent(1).decide(view_for(state, request.player), request)
    assert answer.request_id == request.id
    assert answer.player == request.player
    request.space.validate(answer.value)


def test_a_negative_span_is_refused() -> None:
    with pytest.raises(ValueError, match="unbounded_span"):
        RandomAgent(1, unbounded_span=-1)
