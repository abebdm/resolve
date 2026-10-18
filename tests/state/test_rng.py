"""The engine's own PRNG (design.md §12): fixed algorithm, fixed outputs, uniform shuffles.

Golden values come from the reference C implementations of splitmix64 and xoshiro256**
(Blackman and Vigna), compiled once; splitmix64's sequence for seed 0 is also the widely published
one. If these change, every recorded replay changes meaning.
"""

from __future__ import annotations

import copy
import pickle
from collections import Counter
from itertools import permutations

import pytest

from resolve.state.rng import Rng, splitmix64


def test_splitmix64_matches_the_reference_sequence() -> None:
    state, outputs = 0, []
    for _ in range(4):
        state, value = splitmix64(state)
        outputs.append(value)
    assert outputs == [
        0xE220A8397B1DCDAF,
        0x6E789E6AA1B965F4,
        0x06C45D188009454F,
        0xF88BB8A8724C81EC,
    ]


@pytest.mark.parametrize(
    ("seed", "expected"),
    [
        (0, [0x99EC5F36CB75F2B4, 0xBF6E1F784956452A, 0x1A5F849D4933E6E0, 0x6AA594F1262D2D2C]),
        (42, [0x15780B2E0C2EC716, 0x6104D9866D113A7E, 0xAE17533239E499A1, 0xECB8AD4703B360A1]),
        (
            2**64 - 1,
            [0x8F5520D52A7EAD08, 0xC476A018CAA1802D, 0x81DE31C0D260469E, 0xBF658D7E065F3C2F],
        ),
    ],
)
def test_xoshiro256starstar_matches_the_reference_outputs(seed: int, expected: list[int]) -> None:
    rng = Rng.from_seed(seed)
    assert [rng.next_u64() for _ in range(4)] == expected


@pytest.mark.parametrize("seed", [-1, 2**64, True])
def test_seeds_must_be_64_bit_unsigned_integers(seed: int) -> None:
    with pytest.raises(ValueError, match="seed"):
        Rng.from_seed(seed)


def test_randbelow_stays_in_range_and_covers_it() -> None:
    rng = Rng.from_seed(5)
    values = [rng.randbelow(6) for _ in range(600)]
    assert set(values) == set(range(6))
    assert Rng.from_seed(5).randbelow(1) == 0
    assert 0 <= Rng.from_seed(5).randbelow(2**64) < 2**64


@pytest.mark.parametrize("bound", [0, -3, 2**64 + 1, True])
def test_randbelow_rejects_bad_bounds(bound: int) -> None:
    with pytest.raises(ValueError, match="randbelow"):
        Rng.from_seed(1).randbelow(bound)


def test_shuffle_is_a_permutation_and_every_order_occurs() -> None:
    """701.24a: a shuffle randomizes the order; Fisher-Yates makes every order equally likely."""
    counts: Counter[tuple[int, ...]] = Counter()
    for seed in range(1200):
        items = [1, 2, 3]
        Rng.from_seed(seed).shuffle(items)
        counts[tuple(items)] += 1
    assert set(counts) == set(permutations([1, 2, 3]))
    assert all(150 <= count <= 250 for count in counts.values()), counts


def test_shuffling_zero_or_one_item_draws_nothing() -> None:
    rng = Rng.from_seed(3)
    before = rng.state
    for items in ([], [1]):
        rng.shuffle(items)
    assert rng.state == before


def test_copies_continue_the_same_sequence_independently() -> None:
    rng = Rng.from_seed(8)
    rng.next_u64()
    expected = Rng(rng.state).next_u64()
    for clone in (copy.deepcopy(rng), pickle.loads(pickle.dumps(rng))):
        assert clone == rng
        assert clone.next_u64() == expected
        assert clone != rng, "advancing the copy leaves the original alone"
