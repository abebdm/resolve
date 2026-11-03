"""The solver of ``ChooseAssignment`` declarations (design.md §17.8, §17.18).

Pure functions over the space (no game state), so the engine, agents and a UI read the same
model:

- ``broken_constraints(space, picks)``: the constraints an answer's picks break (508.1c, 509.1b:
  a declaration that disobeys a restriction is illegal).
- ``requirements_obeyed(space, picks)``: how many requirements the picks obey (508.1d, 509.1c;
  each instance counts once).
- ``obeyable_bound(space)``: the most each item could obey on its own, without costly picks,
  added up: an upper bound of ``most_obeyable``. An answer that reaches it needs no search.
- ``most_obeyable(space)``: the most requirements any answer satisfying every constraint obeys
  without costly picks (508.1d, 509.1c: a player isn't required to pay a cost to obey a
  requirement; the M3 plan's Q2 reading). ``ChooseAssignment.validate`` refuses an answer that
  obeys fewer.
- ``random_legal(space, rng)``: a random legal answer, for agents (not uniform).

**The search.** ``most_obeyable`` is a backtracking search with branch and bound, over groups of
items that share a constraint (items linked by a ``NoneOrAtLeast`` choice; every item, when a
``NotAlone`` or ``AtMost`` constraint exists), each group searched on its own. An item's
candidate picks are reduced without losing an optimum: its constrained choices (those of a
``NoneOrAtLeast``) are tried in every combination its maximum allows, and the rest of its room
goes to the unconstrained choices that obey the most of its requirements (choices obeying the
same requirements are interchangeable), plus one "filler" pick for an item that would otherwise
pick nothing (it matters only to ``NotAlone`` and ``AtMost``). The worst case is exponential in
a group's size (the M3 plan's risk); ``tests/decisions/test_assignment_requirements.py`` has the
plan's benchmark.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import TYPE_CHECKING

from resolve.decisions.spaces import (
    Assignment,
    AtMost,
    ChooseAssignment,
    Constraint,
    NoneOrAtLeast,
    NotAlone,
)
from resolve.errors import EngineError, InvalidAnswer

if TYPE_CHECKING:
    from resolve.decisions.spaces import Option
    from resolve.state.rng import Rng

Picks = tuple[tuple[int, ...], ...]

_RANDOM_TRIES = 8
"""How many random draws ``random_legal`` repairs before it searches (see its docstring)."""


def pickers(space: ChooseAssignment, picks: Picks, choice: Option) -> tuple[int, ...]:
    """The items (by index, in order) whose picks include ``choice``, compared by value."""
    return tuple(
        item
        for item, (choices, chosen) in enumerate(zip(space.choices, picks, strict=True))
        if any(choices[index] == choice for index in chosen)
    )


def broken_constraints(space: ChooseAssignment, picks: Picks) -> tuple[Constraint, ...]:
    """The constraints of ``space`` that ``picks`` (already checked for shape and range) break,
    in the space's order."""
    broken: list[Constraint] = []
    picking = sum(1 for chosen in picks if chosen)
    for constraint in space.constraints:
        match constraint:
            case NoneOrAtLeast(choice=choice, minimum=minimum):
                count = len(pickers(space, picks, choice))
                if 0 < count < minimum:
                    broken.append(constraint)
            case NotAlone(item=item):
                # 506.5: "alone" is the only one declared; any other item picking is company.
                if picks[space.items.index(item)] and picking == 1:
                    broken.append(constraint)
            case AtMost(count=count):
                if picking > count:
                    broken.append(constraint)
    return tuple(broken)


def requirements_obeyed(space: ChooseAssignment, picks: Picks) -> int:
    """How many of the space's requirements ``picks`` obeys (508.1d, 509.1c): a requirement is
    obeyed when its item picks one of its choices; each instance counts once."""
    model = _Model.of(space)
    return sum(model.obeyed(item, picks[item]) for item in range(len(space.items)))


def obeyable_bound(space: ChooseAssignment) -> int:
    """The most requirements each item could obey on its own without costly picks, added up: an
    upper bound of ``most_obeyable`` (equal when no constraint stops the items)."""
    model = _Model.of(space)
    return sum(model.bound(item) for item in range(len(space.items)))


def most_obeyable(space: ChooseAssignment) -> int:
    """The most requirements any answer that satisfies every constraint obeys without costly
    picks (508.1d, 509.1c). Picking nothing satisfies every constraint, so it exists."""
    if not space.requirements:
        return 0
    return _Model.of(space).best(None)[0]


def random_legal(space: ChooseAssignment, rng: Rng) -> Assignment:
    """A random legal answer to ``space``: every constraint satisfied and at least
    ``most_obeyable`` requirements obeyed.

    It draws up to ``_RANDOM_TRIES`` answers. Each draw first decides, with equal probability,
    whether it may pick costly choices at all (so at least half the answers need no cost: an
    agent that can't pay isn't stuck declaring, being reversed and declaring again). Then each
    item picks, for each of its requirements in a random order, a random allowed obeying choice
    while it has room, then a random number of random other allowed choices up to its maximum;
    each broken constraint is then repaired (``_repair``, with the allowed choices only). The
    first draw that is legal is the answer. If none is, a randomized search returns an answer
    obeying the most requirements without costly picks (``_Model.best`` with the candidates
    shuffled). Not uniform over the legal answers.
    """
    model = _Model.of(space)
    target = most_obeyable(space)
    for _ in range(_RANDOM_TRIES):
        costly = bool(space.costly) and bool(rng.randbelow(2))
        allowed = [
            tuple(range(len(choices))) if costly else model.free[item]
            for item, choices in enumerate(space.choices)
        ]
        picks = [model.draw(item, allowed[item], rng) for item in range(len(space.items))]
        _repair(space, picks, allowed, rng)
        checked = tuple(tuple(p) for p in picks)
        if not broken_constraints(space, checked) and (
            requirements_obeyed(space, checked) >= target
        ):
            return _checked(space, checked)
    found = model.best(rng)[1]
    return _checked(space, found)


def _checked(space: ChooseAssignment, picks: Picks) -> Assignment:
    answer = Assignment(picks)
    try:
        space.validate(answer)
    except InvalidAnswer as error:  # the search is complete, so an engine bug
        raise EngineError(f"random_legal found an illegal answer: {error}") from None
    return answer


def _repair(
    space: ChooseAssignment,
    picks: list[list[int]],
    allowed: list[tuple[int, ...]],
    rng: Rng,
) -> None:
    """Repair the constraints ``picks`` breaks, in place, adding only ``allowed`` choices.

    First each ``NoneOrAtLeast`` choice picked by too few items (the constraints on one choice
    taken together: the largest minimum) is filled up with randomly chosen other items that offer
    it (allowed) and have room, or cleared from the items that picked it, with equal probability when both
    are possible. Then, while a constraint is broken, it is repaired by removing picks only
    (clearing the choice, a ``NotAlone`` item, or random picking items beyond an ``AtMost``):
    picks only decrease and picking nothing breaks nothing, so this ends.
    """
    minimums: dict[Option, int] = {}
    for constraint in space.constraints:
        if isinstance(constraint, NoneOrAtLeast):
            choice = constraint.choice
            minimums[choice] = max(minimums.get(choice, 0), constraint.minimum)
    for choice, minimum in minimums.items():
        chosen = pickers(space, tuple(tuple(p) for p in picks), choice)
        if not 0 < len(chosen) < minimum:
            continue
        room = [
            item
            for item, (choices, maximum) in enumerate(zip(space.choices, space.maxima, strict=True))
            if item not in chosen
            and choice in choices
            and choices.index(choice) in allowed[item]
            and len(picks[item]) < maximum
        ]
        missing = minimum - len(chosen)
        if len(room) >= missing and rng.randbelow(2):
            for item in _sample(rng, room, missing):
                picks[item] = sorted([*picks[item], space.choices[item].index(choice)])
        else:
            for item in chosen:
                picks[item] = [i for i in picks[item] if space.choices[item][i] != choice]
    while broken := broken_constraints(space, tuple(tuple(p) for p in picks)):
        match broken[0]:
            case NoneOrAtLeast(choice=choice):
                for item in range(len(picks)):
                    picks[item] = [i for i in picks[item] if space.choices[item][i] != choice]
            case NotAlone(item=item):
                picks[space.items.index(item)] = []
            case AtMost(count=count):
                picking = [item for item, chosen in enumerate(picks) if chosen]
                for item in _sample(rng, picking, len(picking) - count):
                    picks[item] = []


@dataclass(frozen=True, slots=True)
class _Model:
    """The space by indices, for the search: per item, its cost-free choice indices (``free``),
    its requirements as sets of choice indices (``requirements``), and which of its choices are
    a ``NoneOrAtLeast`` choice (``constrained``: choice index to the choice's minimum)."""

    space: ChooseAssignment
    free: tuple[tuple[int, ...], ...]
    requirements: tuple[tuple[frozenset[int], ...], ...]
    constrained: tuple[dict[int, int], ...]
    minimums: dict[Option, int]

    @staticmethod
    def of(space: ChooseAssignment) -> _Model:
        costly = {(pick.item, pick.choice) for pick in space.costly}
        minimums: dict[Option, int] = {}
        for constraint in space.constraints:
            if isinstance(constraint, NoneOrAtLeast):
                choice = constraint.choice
                minimums[choice] = max(minimums.get(choice, 0), constraint.minimum)
        free: list[tuple[int, ...]] = []
        requirements: list[list[frozenset[int]]] = [[] for _ in space.items]
        constrained: list[dict[int, int]] = []
        index = {item: number for number, item in enumerate(space.items)}
        for item, choices in zip(space.items, space.choices, strict=True):
            free.append(tuple(i for i, c in enumerate(choices) if (item, c) not in costly))
            constrained.append({i: minimums[c] for i, c in enumerate(choices) if c in minimums})
        for requirement in space.requirements:
            number = index[requirement.item]
            choices = space.choices[number]
            requirements[number].append(frozenset(choices.index(c) for c in requirement.choices))
        return _Model(
            space,
            tuple(free),
            tuple(tuple(r) for r in requirements),
            tuple(constrained),
            minimums,
        )

    def obeyed(self, item: int, chosen: tuple[int, ...] | list[int]) -> int:
        picked = set(chosen)
        return sum(1 for requirement in self.requirements[item] if requirement & picked)

    def bound(self, item: int) -> int:
        candidates = self.candidates(item)
        return max(self.obeyed(item, c) for c in candidates)

    def candidates(self, item: int) -> list[tuple[int, ...]]:
        """The item's cost-free candidate picks (the module's reduction), most obeying first."""
        maximum = self.space.maxima[item]
        free = self.free[item]
        constrained = [i for i in free if i in self.constrained[item]]
        loose = [i for i in free if i not in self.constrained[item]]
        # Loose choices obeying the same requirements are interchangeable: one of each kind.
        kinds: dict[frozenset[int], int] = {}
        for i in loose:
            signature = frozenset(
                number for number, req in enumerate(self.requirements[item]) if i in req
            )
            kinds.setdefault(signature, i)
        useful = [i for signature, i in kinds.items() if signature]
        filler = kinds.get(frozenset())
        found: dict[tuple[int, ...], None] = {}
        for size in range(min(maximum, len(constrained)) + 1):
            for subset in combinations(constrained, size):
                room = maximum - size
                best: tuple[int, ...] = ()
                best_count = -1
                for extra in range(min(room, len(useful)) + 1):
                    for added in combinations(useful, extra):
                        count = self.obeyed(item, (*subset, *added))
                        if count > best_count:
                            best, best_count = added, count
                found[tuple(sorted((*subset, *best)))] = None
        found[()] = None  # picking nothing matters to ``NotAlone`` and ``AtMost``
        if filler is not None and maximum:
            # Picking something matters to ``NotAlone`` and ``AtMost`` even if it obeys nothing.
            found[(filler,)] = None
        return sorted(found, key=lambda c: -self.obeyed(item, c))

    def groups(self) -> list[list[int]]:
        """The items in groups that share no constraint, each in item order."""
        count = len(self.space.items)
        if any(isinstance(c, NotAlone | AtMost) for c in self.space.constraints):
            return [list(range(count))]
        parent = list(range(count))

        def root(item: int) -> int:
            while parent[item] != item:
                parent[item] = parent[parent[item]]
                item = parent[item]
            return item

        holders: dict[Option, int] = {}
        for item, choices in enumerate(self.space.choices):
            for index in self.constrained[item]:
                if index not in self.free[item]:
                    continue
                choice = choices[index]
                if choice in holders:
                    parent[root(item)] = root(holders[choice])
                else:
                    holders[choice] = item
        grouped: dict[int, list[int]] = {}
        for item in range(count):
            grouped.setdefault(root(item), []).append(item)
        return list(grouped.values())

    def best(self, rng: Rng | None) -> tuple[int, Picks]:
        """The most requirements obeyable without costly picks, and an answer obeying them
        (with ``rng``, the candidates of each item are tried in a random order)."""
        picks: list[tuple[int, ...]] = [() for _ in self.space.items]
        total = 0
        for group in self.groups():
            if not any(self.requirements[item] for item in group) and rng is None:
                continue
            count, found = self._search(group, rng)
            total += count
            for item, chosen in zip(group, found, strict=True):
                picks[item] = chosen
        return total, tuple(picks)

    def _search(self, group: list[int], rng: Rng | None) -> tuple[int, list[tuple[int, ...]]]:
        candidates = [self.candidates(item) for item in group]
        if rng is not None:
            candidates = [_shuffled(rng, c) for c in candidates]
        bounds = [
            max(self.obeyed(item, c) for c in cs)
            for item, cs in zip(group, candidates, strict=True)
        ]
        suffix = [0] * (len(group) + 1)
        for position in range(len(group) - 1, -1, -1):
            suffix[position] = suffix[position + 1] + bounds[position]
        # How many items from each position on could still pick each constrained choice.
        later: list[dict[Option, int]] = [{} for _ in range(len(group) + 1)]
        for position in range(len(group) - 1, -1, -1):
            item = group[position]
            counts = dict(later[position + 1])
            for index in self.constrained[item]:
                if index in self.free[item] and self.space.maxima[item]:
                    choice = self.space.choices[item][index]
                    counts[choice] = counts.get(choice, 0) + 1
            later[position] = counts
        limit = min(
            (c.count for c in self.space.constraints if isinstance(c, AtMost)), default=None
        )
        best_count = -1
        best: list[tuple[int, ...]] = [() for _ in group]
        chosen: list[tuple[int, ...]] = [() for _ in group]
        counts: dict[Option, int] = {}
        state = {"picking": 0, "count": 0}

        def visit(position: int) -> bool:
            """Search from ``position``; True once the bound is reached (stop)."""
            nonlocal best_count, best
            if state["count"] + suffix[position] <= best_count:
                return False
            if position == len(group):
                full: list[tuple[int, ...]] = [() for _ in self.space.items]
                for item, picked in zip(group, chosen, strict=True):
                    full[item] = picked
                if broken_constraints(self.space, tuple(full)):
                    return False
                best_count, best = state["count"], list(chosen)
                return best_count == suffix[0]
            item = group[position]
            for candidate in candidates[position]:
                picking = state["picking"] + (1 if candidate else 0)
                if limit is not None and picking > limit:
                    continue
                added = [self.space.choices[item][i] for i in candidate]
                for choice in added:
                    counts[choice] = counts.get(choice, 0) + 1
                feasible = all(
                    counts.get(choice, 0) == 0
                    or counts[choice] + later[position + 1].get(choice, 0) >= minimum
                    for choice, minimum in self.minimums.items()
                )
                if feasible:
                    chosen[position] = candidate
                    gained = self.obeyed(item, candidate)
                    state["picking"], state["count"] = picking, state["count"] + gained
                    stop = visit(position + 1)
                    state["picking"] = picking - (1 if candidate else 0)
                    state["count"] -= gained
                    chosen[position] = ()
                else:
                    stop = False
                for choice in added:
                    counts[choice] -= 1
                if stop:
                    return True
            return False

        visit(0)
        if best_count < 0:  # unreachable: picking nothing satisfies every constraint
            raise EngineError("the declaration search found no legal answer")
        return best_count, best

    def draw(self, item: int, allowed: tuple[int, ...], rng: Rng) -> list[int]:
        """A random pick for ``item`` among the ``allowed`` choices (see ``random_legal``), as
        sorted choice indices."""
        maximum = self.space.maxima[item]
        picked: list[int] = []
        for requirement in _shuffled(rng, list(self.requirements[item])):
            options = sorted(requirement & set(allowed))
            if len(picked) >= maximum or requirement & set(picked) or not options:
                continue
            picked.append(options[rng.randbelow(len(options))])
        size = len(picked) + rng.randbelow(maximum - len(picked) + 1)
        # A partial Fisher-Yates shuffle: the first ones drawn are a uniform sample (without
        # requirements or costs, the same draws as M3.4's, so seeded games don't change).
        rest = [i for i in allowed if i not in picked]
        picked += _sample(rng, rest, min(size - len(picked), len(rest)))
        return sorted(picked)


def _shuffled[T](rng: Rng, items: list[T]) -> list[T]:
    """A copy of ``items`` in a uniformly random order (Fisher-Yates)."""
    pool = list(items)
    for i in range(len(pool) - 1):
        j = i + rng.randbelow(len(pool) - i)
        pool[i], pool[j] = pool[j], pool[i]
    return pool


def _sample(rng: Rng, items: list[int], size: int) -> list[int]:
    """``size`` distinct members of ``items``, each set equally likely."""
    pool = list(items)
    for i in range(size):
        j = i + rng.randbelow(len(pool) - i)
        pool[i], pool[j] = pool[j], pool[i]
    return pool[:size]
