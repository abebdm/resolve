"""The game's random number generator (design.md §12; docs/decisions.md 2026-10-18).

All randomness in a game comes from the ``Rng`` stored in its state, so a game is a pure function
of its config, decks, seed and answers. The engine implements its own generator instead of using
``random.Random`` because Python only promises that ``random()`` itself stays the same across
versions; ``shuffle`` and ``randrange`` may change. A replay, a networked peer on another Python
version, or a later port to another language must reproduce every shuffle exactly.

The algorithm is xoshiro256** (Blackman and Vigna), seeded by running splitmix64 on the seed.
Integers below a bound use rejection sampling, and shuffling is Fisher-Yates, so every
permutation is equally likely (701.24a).
"""

from __future__ import annotations

from dataclasses import dataclass

MASK64 = (1 << 64) - 1
SEED_LIMIT = 1 << 64

_GOLDEN_GAMMA = 0x9E3779B97F4A7C15


def splitmix64(state: int) -> tuple[int, int]:
    """One splitmix64 step: returns ``(next_state, output)``."""
    state = (state + _GOLDEN_GAMMA) & MASK64
    z = state
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
    return state, z ^ (z >> 31)


def _rotl(x: int, k: int) -> int:
    return ((x << k) | (x >> (64 - k))) & MASK64


@dataclass(slots=True)
class Rng:
    """xoshiro256** state: four 64-bit integers, never all zero."""

    state: tuple[int, int, int, int]

    @classmethod
    def from_seed(cls, seed: int) -> Rng:
        """A generator seeded with ``seed``, an integer in ``[0, 2**64)``."""
        if isinstance(seed, bool) or not 0 <= seed < SEED_LIMIT:
            raise ValueError(f"seed must be an integer in [0, 2**64), got {seed!r}")
        sm = seed
        words: list[int] = []
        for _ in range(4):
            sm, word = splitmix64(sm)
            words.append(word)
        # splitmix64's output function is a bijection and the four states differ, so at most one
        # word is 0: the state is never all zero, which xoshiro256** requires.
        return cls((words[0], words[1], words[2], words[3]))

    def next_u64(self) -> int:
        """The next 64-bit output."""
        s0, s1, s2, s3 = self.state
        result = (_rotl((s1 * 5) & MASK64, 7) * 9) & MASK64
        t = (s1 << 17) & MASK64
        s2 ^= s0
        s3 ^= s1
        s1 ^= s2
        s0 ^= s3
        s2 ^= t
        s3 = _rotl(s3, 45)
        self.state = (s0, s1, s2, s3)
        return result

    def randbelow(self, n: int) -> int:
        """A uniformly random integer in ``[0, n)``, for ``1 <= n <= 2**64``."""
        if isinstance(n, bool) or not 1 <= n <= SEED_LIMIT:
            raise ValueError(f"randbelow needs 1 <= n <= 2**64, got {n!r}")
        # Reject the top partial block of outputs so every residue is equally likely.
        limit = SEED_LIMIT - (SEED_LIMIT % n)
        while True:
            value = self.next_u64()
            if value < limit:
                return value % n

    def shuffle[T](self, items: list[T]) -> None:
        """Shuffle ``items`` in place (Fisher-Yates)."""
        for i in range(len(items) - 1, 0, -1):
            j = self.randbelow(i + 1)
            items[i], items[j] = items[j], items[i]
