"""The solver of ``ChooseAssignment`` declarations (design.md §17.8, §17.18).

Pure functions over the space (no game state), so the engine, agents and a UI read the same
model:

- ``broken_constraints(space, picks)``: the constraints an answer's picks break (509.1b: a
  declaration that disobeys a restriction is illegal). ``ChooseAssignment.validate`` refuses an
  answer that breaks any.
- ``random_legal(space, rng)``: a random answer that satisfies every constraint, for agents. It
  isn't uniform over the legal answers: each item draws its picks as before constraints existed
  (a number of picks uniformly from 0 to its maximum, then that many of its choices), then each
  broken constraint is repaired.

The constraints so far are ``NoneOrAtLeast`` (menace, 702.111b). M3.5 adds ``NotAlone``,
``AtMost``, the requirements (508.1d, 509.1c: obey as many as possible) and the costly picks;
``random_legal`` then becomes a randomized search.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from resolve.decisions.spaces import Assignment, ChooseAssignment, Constraint

if TYPE_CHECKING:
    from resolve.state.rng import Rng


def broken_constraints(
    space: ChooseAssignment, picks: tuple[tuple[int, ...], ...]
) -> tuple[Constraint, ...]:
    """The constraints of ``space`` that ``picks`` (already checked for shape and range) break,
    in the space's order."""
    return ()


def random_legal(space: ChooseAssignment, rng: Rng) -> Assignment:
    """A random answer to ``space`` that satisfies all its constraints (see the module)."""
    picks = [
        _subset(rng, len(choices), maximum)
        for choices, maximum in zip(space.choices, space.maxima, strict=True)
    ]
    return Assignment(tuple(picks))


def _subset(rng: Rng, population: int, maximum: int) -> tuple[int, ...]:
    """A size uniformly from 0 to ``maximum``, then each subset of ``range(population)`` of that
    size equally likely, as sorted indices."""
    size = rng.randbelow(maximum + 1)
    items = list(range(population))
    # A partial Fisher-Yates shuffle: the first ``size`` items are a uniform sample.
    for i in range(size):
        j = i + rng.randbelow(population - i)
        items[i], items[j] = items[j], items[i]
    return tuple(sorted(items[:size]))
