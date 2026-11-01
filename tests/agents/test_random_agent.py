"""RandomAgent: uniformly random answers inside every answer space (design.md §6, §14)."""

from __future__ import annotations

from collections import Counter

import pytest

from resolve.agents.random_agent import DEFAULT_UNBOUNDED_SPAN, RandomAgent
from resolve.decisions.spaces import (
    Amounts,
    AmountsEach,
    AnswerSpace,
    Assignment,
    ChooseAssignment,
    ChooseCounts,
    ChooseNumber,
    ChooseOne,
    ChooseOrder,
    ChooseSubset,
    Distribute,
    DistributeEach,
    NoneOrAtLeast,
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
    ChooseAssignment(OPTIONS[:2], (OPTIONS[2:], OPTIONS[2:]), (1, 1)),
    ChooseAssignment(OPTIONS[:3], (OPTIONS, (), OPTIONS[:2]), (4, 0, 1)),
    ChooseAssignment(OPTIONS[:1], ((),), (0,)),
    DistributeEach(OPTIONS[:1], (Distribute(OPTIONS[:3], 7, minimum_each=0),)),
    DistributeEach(
        OPTIONS[:2],
        (Distribute(OPTIONS[:2], 0, minimum_each=0), Distribute(OPTIONS[2:], 5, minimum_each=0)),
    ),
]

SAMPLES = 2000

# Critical values of the chi-square distribution at p = 0.001, by degrees of freedom (standard
# tables). A uniform sampler exceeds them one time in a thousand; the seeds are fixed, so the
# tests are deterministic, and a biased sampler (see the naive-shuffle test) exceeds them by far.
CHI_SQUARE_0_001 = {
    2: 13.816,
    8: 26.124,
    3: 16.266,
    4: 18.467,
    5: 20.515,
    6: 22.458,
    14: 36.123,
    23: 49.728,
}


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


def test_random_agent_answers_inside_both_spaces() -> None:
    """Over many seeds, every answer to ``ChooseAssignment`` and ``DistributeEach`` validates
    (the combat spaces, design.md 17.18)."""
    combat = [s for s in SPACES if isinstance(s, ChooseAssignment | DistributeEach)]
    assert len(combat) == 5
    for seed in range(50):
        agent = RandomAgent(seed)
        for space in combat:
            for _ in range(20):
                space.validate(agent.random_value(space))


def test_random_agent_obeys_a_declarations_constraints() -> None:
    """Menace (702.111b) as a ``NoneOrAtLeast`` constraint: four blockers, each able to block
    one of two attackers, the first needing two blockers. Over many seeds the agent's answers
    (``random_legal``) always validate, and some do block the first attacker."""
    blocked = 0
    space = ChooseAssignment(
        OPTIONS[:4], ((OPTIONS[0], OPTIONS[1]),) * 4, (1,) * 4, (NoneOrAtLeast(OPTIONS[0], 2),)
    )
    for seed in range(100):
        value = RandomAgent(seed).random_value(space)
        space.validate(value)
        assert isinstance(value, Assignment)
        blocked += any(0 in picks for picks in value.picks)
    assert blocked > 0


def test_choose_assignment_picks_each_item_like_a_subset() -> None:
    """Each item, as ``ChooseSubset`` from 0 to its maximum: a size uniformly in range, then each
    subset of that size equally likely. Three choices, at most two: sizes 0, 1 and 2 equally
    often, and the three single picks and three pairs each equally often."""
    agent = RandomAgent(seed=15)
    space = ChooseAssignment(OPTIONS[:1], (OPTIONS[:3],), (2,))
    answers = [agent.random_value(space) for _ in range(SAMPLES * 3)]
    picks = [a.picks[0] for a in answers if isinstance(a, Assignment)]
    assert len(picks) == len(answers)
    assert_uniform(Counter[object](len(p) for p in picks), 3)
    assert_uniform(Counter[object](p for p in picks if len(p) == 1), 3)
    assert_uniform(Counter[object](p for p in picks if len(p) == 2), 3)


def test_choose_assignment_picks_the_items_independently() -> None:
    """Two items, two choices each, at most one: each item's three answers reached with every
    answer of the other (nine in all)."""
    agent = RandomAgent(seed=16)
    space = ChooseAssignment(OPTIONS[:2], (OPTIONS[2:], OPTIONS[2:]), (1, 1))
    seen = {agent.random_value(space) for _ in range(SAMPLES)}
    assert len(seen) == 9


def test_distribute_each_is_uniform_over_the_answers() -> None:
    """Two parts, each 2 between two recipients with minimum 0: 3 x 3 = 9 answers."""
    agent = RandomAgent(seed=17)
    part = Distribute(OPTIONS[:2], 2, minimum_each=0)
    space = DistributeEach(OPTIONS[2:], (part, part))
    counts = Counter[object](agent.random_value(space) for _ in range(SAMPLES * 3))
    assert AmountsEach((Amounts((2, 0)), Amounts((0, 2)))) in counts
    assert_uniform(counts, 9)


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
