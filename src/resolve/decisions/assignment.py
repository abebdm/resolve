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

from resolve.decisions.spaces import Assignment, ChooseAssignment, Constraint, NoneOrAtLeast
from resolve.errors import EngineError, InvalidAnswer

if TYPE_CHECKING:
    from resolve.decisions.spaces import Option
    from resolve.state.rng import Rng


def pickers(
    space: ChooseAssignment, picks: tuple[tuple[int, ...], ...], choice: Option
) -> tuple[int, ...]:
    """The items (by index, in order) whose picks include ``choice``, compared by value."""
    return tuple(
        item
        for item, (choices, chosen) in enumerate(zip(space.choices, picks, strict=True))
        if any(choices[index] == choice for index in chosen)
    )


def broken_constraints(
    space: ChooseAssignment, picks: tuple[tuple[int, ...], ...]
) -> tuple[Constraint, ...]:
    """The constraints of ``space`` that ``picks`` (already checked for shape and range) break,
    in the space's order."""
    broken: list[Constraint] = []
    for constraint in space.constraints:
        match constraint:
            case NoneOrAtLeast(choice=choice, minimum=minimum):
                count = len(pickers(space, picks, choice))
                if 0 < count < minimum:
                    broken.append(constraint)
    return tuple(broken)


def random_legal(space: ChooseAssignment, rng: Rng) -> Assignment:
    """A random answer to ``space`` that satisfies all its constraints (see the module).

    Each ``NoneOrAtLeast`` choice picked by too few items (the constraints on one choice taken
    together: the largest minimum) is repaired one way or the other with equal probability, when
    both are possible: filled up with randomly chosen other items that offer the choice and have
    room under their maximum, or cleared from the items that picked it. Filling only adds picks
    of that choice and clearing only removes them, so repairing one choice never breaks another.
    """
    picks = [
        list(_subset(rng, len(choices), maximum))
        for choices, maximum in zip(space.choices, space.maxima, strict=True)
    ]
    minimums: dict[Option, int] = {}
    for constraint in space.constraints:
        minimums[constraint.choice] = max(minimums.get(constraint.choice, 0), constraint.minimum)
    for choice, minimum in minimums.items():
        current = tuple(tuple(p) for p in picks)
        chosen = pickers(space, current, choice)
        if not 0 < len(chosen) < minimum:
            continue
        room = [
            item
            for item, (choices, maximum) in enumerate(zip(space.choices, space.maxima, strict=True))
            if item not in chosen and choice in choices and len(picks[item]) < maximum
        ]
        missing = minimum - len(chosen)
        if len(room) >= missing and rng.randbelow(2):
            for item in _sample(rng, room, missing):
                picks[item] = sorted([*picks[item], space.choices[item].index(choice)])
        else:
            for item in chosen:
                picks[item] = [i for i in picks[item] if space.choices[item][i] != choice]
    answer = Assignment(tuple(tuple(p) for p in picks))
    try:
        space.validate(answer)
    except InvalidAnswer as error:  # the repairs above are complete, so an engine bug
        raise EngineError(f"random_legal drew an illegal answer: {error}") from None
    return answer


def _sample(rng: Rng, items: list[int], size: int) -> list[int]:
    """``size`` distinct members of ``items``, each set equally likely."""
    pool = list(items)
    for i in range(size):
        j = i + rng.randbelow(len(pool) - i)
        pool[i], pool[j] = pool[j], pool[i]
    return pool[:size]


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
