"""RandomAgent: uniformly random answers inside every answer space (design.md §6, §14)."""

from __future__ import annotations

from collections import Counter

import pytest

from resolve.agents.random_agent import DEFAULT_UNBOUNDED_SPAN, RandomAgent
from resolve.decisions.spaces import (
    Amounts,
    AnswerSpace,
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
]

SAMPLES = 2000


@pytest.mark.parametrize("space", SPACES, ids=repr)
def test_every_random_answer_is_inside_the_space(space: AnswerSpace) -> None:
    agent = RandomAgent(seed=7)
    for _ in range(200):
        space.validate(agent.random_value(space))  # raises InvalidAnswer if it isn't


def test_choose_one_picks_every_option_about_equally_often() -> None:
    agent = RandomAgent(seed=1)
    counts = Counter(agent.random_value(ChooseOne(OPTIONS)) for _ in range(SAMPLES))
    assert set(counts) == {Pick(i) for i in range(4)}
    assert all(abs(count - SAMPLES / 4) < SAMPLES * 0.05 for count in counts.values())


def test_choose_subset_reaches_every_size_and_every_subset() -> None:
    """Sizes 0..4 are equally likely; 2**4 = 16 subsets in all."""
    agent = RandomAgent(seed=2)
    answers = [agent.random_value(ChooseSubset(OPTIONS, 0, 4)) for _ in range(SAMPLES)]
    assert len(set(answers)) == 16
    sizes = Counter(len(answer.indices) for answer in answers if isinstance(answer, PickMany))
    assert sorted(sizes) == [0, 1, 2, 3, 4]
    assert all(abs(count - SAMPLES / 5) < SAMPLES * 0.05 for count in sizes.values())


def test_choose_subset_of_a_fixed_size_picks_each_subset_about_equally_often() -> None:
    """C(4, 2) = 6 subsets of size 2."""
    agent = RandomAgent(seed=3)
    counts = Counter(agent.random_value(ChooseSubset(OPTIONS, 2, 2)) for _ in range(SAMPLES))
    assert len(counts) == 6
    assert all(abs(count - SAMPLES / 6) < SAMPLES * 0.05 for count in counts.values())


def test_choose_order_reaches_every_permutation() -> None:
    """4! = 24 permutations, about equally often."""
    agent = RandomAgent(seed=4)
    counts = Counter(agent.random_value(ChooseOrder(OPTIONS)) for _ in range(SAMPLES * 3))
    assert len(counts) == 24
    assert all(abs(count - SAMPLES * 3 / 24) < SAMPLES * 3 * 0.02 for count in counts.values())
    assert all(isinstance(answer, Order) for answer in counts)


def test_choose_number_reaches_both_bounds() -> None:
    agent = RandomAgent(seed=5)
    values = {agent.random_value(ChooseNumber(-3, 3)) for _ in range(500)}
    assert values == {Number(n) for n in range(-3, 4)}


def test_an_unbounded_number_is_capped_at_minimum_plus_the_span() -> None:
    agent = RandomAgent(seed=6, unbounded_span=3)
    values = {agent.random_value(ChooseNumber(5)) for _ in range(500)}
    assert values == {Number(5), Number(6), Number(7), Number(8)}
    assert DEFAULT_UNBOUNDED_SPAN == 20


def test_distribute_reaches_every_division_about_equally_often() -> None:
    """7 among 3 with at least 1 each: C(6, 2) = 15 divisions (stars and bars)."""
    agent = RandomAgent(seed=8)
    counts = Counter(agent.random_value(Distribute(OPTIONS[:3], 7)) for _ in range(SAMPLES * 3))
    assert len(counts) == 15
    assert Amounts((5, 1, 1)) in counts and Amounts((1, 1, 5)) in counts
    assert all(abs(count - SAMPLES * 3 / 15) < SAMPLES * 3 * 0.03 for count in counts.values())


def test_distribute_with_no_spare_gives_each_recipient_the_minimum() -> None:
    agent = RandomAgent(seed=9)
    assert agent.random_value(Distribute(OPTIONS[:3], 3)) == Amounts((1, 1, 1))
    assert agent.random_value(Distribute(OPTIONS[:1], 4)) == Amounts((4,))
    assert agent.random_value(Distribute(OPTIONS[:2], 0, minimum_each=0)) == Amounts((0, 0))


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
