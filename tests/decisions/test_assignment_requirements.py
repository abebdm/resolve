"""The ``ChooseAssignment`` solver with M3.5's vocabulary: the constraints ``NotAlone`` and
``AtMost``, requirements and costly picks (design.md §17.8, §17.18).

From the pinned CR:

- 508.1c, 509.1b: a declaration that disobeys a restriction is illegal. 508.1c's example: two
  creatures that "can't attack alone" may attack together (``NotAlone``). Silent Arbiter's "No
  more than one creature can attack each combat" is ``AtMost(1)``.
- 508.1d, 509.1c: the number of requirements obeyed must be at least the maximum that could be
  obeyed without disobeying any restriction; a player isn't required to pay a cost to obey a
  requirement. Each requirement counts once. The M3 plan's reading (Q2, docs/decisions.md): the
  maximum is taken over declarations without costly picks, and a declaration with costly picks
  must obey at least that many.
- 508.1d's example: one creature that attacks if able, one with no abilities, "No more than one
  creature can attack each turn": the only legal attack is the first creature alone.
- 509.1c's example: one creature that blocks if able and one with no abilities, an attacker
  with menace: the only legal declaration is both blocking it.

Every expected count below is worked out by hand from these rules.
"""

from __future__ import annotations

import time

import pytest

from resolve.decisions.assignment import (
    most_obeyable,
    obeyable_bound,
    random_legal,
    requirements_obeyed,
)
from resolve.decisions.spaces import (
    Assignment,
    AtMost,
    ChooseAssignment,
    CostlyPick,
    NoneOrAtLeast,
    NotAlone,
    ObjectOption,
    PlayerOption,
    Requirement,
)
from resolve.errors import InvalidAnswer
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.rng import Rng

A, B, C = (ObjectOption(ObjectId(i)) for i in (10, 11, 12))
P1, P2 = PlayerOption(PlayerId(1)), PlayerOption(PlayerId(2))
X, Y, Z = (ObjectOption(ObjectId(i)) for i in (1, 2, 3))


def legal(space: ChooseAssignment, *picks: tuple[int, ...]) -> bool:
    try:
        space.validate(Assignment(picks))
    except InvalidAnswer:
        return False
    return True


# --- NotAlone (508.1c) --------------------------------------------------------------------------


def test_not_alone_refuses_the_item_picking_alone() -> None:
    """A can't attack alone: A alone is refused; A with B (attacking another player: Mogg
    Flunkies' ruling) and nothing at all are accepted; B alone is accepted (B has no such
    restriction)."""
    space = ChooseAssignment((A, B), ((P1, P2), (P1, P2)), (1, 1), (NotAlone(A),))
    assert not legal(space, (0,), ())
    assert legal(space, (0,), (1,))
    assert legal(space, (), ())
    assert legal(space, (), (0,))


def test_508_1c_example_two_items_that_cant_attack_alone_satisfy_each_other() -> None:
    """508.1c's example: two creatures, each "can't attack alone", may attack together; either
    alone is refused."""
    space = ChooseAssignment((A, B), ((P1,), (P1,)), (1, 1), (NotAlone(A), NotAlone(B)))
    assert legal(space, (0,), (0,))
    assert not legal(space, (0,), ())
    assert not legal(space, (), (0,))


def test_not_alone_must_name_an_item() -> None:
    with pytest.raises(ValueError):
        ChooseAssignment((A,), ((P1,),), (1,), (NotAlone(B),))


# --- AtMost (508.1c, 509.1b) --------------------------------------------------------------------


def test_at_most_counts_items_that_pick_anything() -> None:
    """AtMost(1): one item picking (even two choices, a Palace Guard) is accepted; two are
    refused. AtMost(0) refuses any pick."""
    space = ChooseAssignment((A, B), ((X, Y), (X, Y)), (2, 1), (AtMost(1),))
    assert legal(space, (0, 1), ())
    assert legal(space, (), (1,))
    assert not legal(space, (0,), (1,))
    zero = ChooseAssignment((A,), ((X,),), (1,), (AtMost(0),))
    assert legal(zero, ())
    assert not legal(zero, (0,))
    with pytest.raises(ValueError):
        AtMost(-1)


# --- Requirements (508.1d, 509.1c) ---------------------------------------------------------------


def test_requirements_obeyed_counts_each_instance() -> None:
    """A has two instances of "attacks if able" (Juggernaut under a Test Warmonger), B one:
    A attacking obeys 2, B attacking 1, both 3, neither 0."""
    space = ChooseAssignment(
        (A, B),
        ((P1,), (P1,)),
        (1, 1),
        requirements=(Requirement(A, (P1,)), Requirement(A, (P1,)), Requirement(B, (P1,))),
    )
    assert requirements_obeyed(space, ((0,), ())) == 2
    assert requirements_obeyed(space, ((), (0,))) == 1
    assert requirements_obeyed(space, ((0,), (0,))) == 3
    assert requirements_obeyed(space, ((), ())) == 0
    assert most_obeyable(space) == 3
    assert legal(space, (0,), (0,))
    assert not legal(space, (0,), ())


def test_508_1d_example_at_most_one_and_a_creature_that_attacks_if_able() -> None:
    """508.1d's example: A attacks if able, B has no abilities, at most one creature attacks.
    The only legal attack is A alone: B alone obeys no requirement where 1 can be obeyed, both
    break AtMost, neither obeys none."""
    space = ChooseAssignment((A, B), ((P1,), (P1,)), (1, 1), (AtMost(1),), (Requirement(A, (P1,)),))
    assert most_obeyable(space) == 1
    assert legal(space, (0,), ())
    assert not legal(space, (), (0,))
    assert not legal(space, (0,), (0,))
    assert not legal(space, (), ())


def test_509_1c_example_menace_and_a_creature_that_blocks_if_able() -> None:
    """509.1c's example: A blocks if able, B has no abilities, X has menace. Only both blocking
    X is legal: A alone breaks menace; B alone breaks menace and obeys nothing; neither obeys
    nothing where 1 can be obeyed."""
    space = ChooseAssignment(
        (A, B), ((X,), (X,)), (1, 1), (NoneOrAtLeast(X, 2),), (Requirement(A, (X,)),)
    )
    assert most_obeyable(space) == 1
    assert legal(space, (0,), (0,))
    assert not legal(space, (0,), ())
    assert not legal(space, (), (0,))
    assert not legal(space, (), ())


def test_a_requirement_obeyed_by_some_choices_only() -> None:
    """Prized Unicorn (X): A must block X if able; blocking Y obeys nothing. A blocks one
    attacker, so blocking Y is refused and blocking X is accepted."""
    space = ChooseAssignment((A,), ((X, Y),), (1,), requirements=(Requirement(A, (X,)),))
    assert legal(space, (0,))
    assert not legal(space, (1,))
    assert not legal(space, ())


def test_two_unicorns_each_item_obeys_one() -> None:
    """Two Prized Unicorns X and Y; A and B each have a requirement to block each. With one
    block each, the most is 2 (each blocks one Unicorn, not necessarily the same: its ruling);
    blocking Z obeys nothing."""
    reqs = tuple(Requirement(item, (u,)) for item in (A, B) for u in (X, Y))
    space = ChooseAssignment((A, B), ((X, Y, Z),) * 2, (1, 1), requirements=reqs)
    assert obeyable_bound(space) == 2
    assert most_obeyable(space) == 2
    assert legal(space, (0,), (1,))
    assert legal(space, (0,), (0,))
    assert not legal(space, (0,), (2,))
    assert not legal(space, (), (1,))


def test_requirement_must_name_its_items_choices() -> None:
    with pytest.raises(ValueError):
        ChooseAssignment((A,), ((X,),), (1,), requirements=(Requirement(A, (Y,)),))
    with pytest.raises(ValueError):
        ChooseAssignment((A,), ((X,),), (1,), requirements=(Requirement(B, (X,)),))
    with pytest.raises(ValueError):
        Requirement(A, ())


def test_a_requirement_disobeyed_because_of_not_alone() -> None:
    """A attacks if able but can't attack alone (Mogg Flunkies attacking if able); B can attack.
    The most is 1 (A with B), so A and B both attack (Mogg Flunkies' ruling); neither is
    refused, and so is B alone."""
    space = ChooseAssignment(
        (A, B), ((P1,), (P1,)), (1, 1), (NotAlone(A),), (Requirement(A, (P1,)),)
    )
    assert most_obeyable(space) == 1
    assert legal(space, (0,), (0,))
    assert not legal(space, (), ())
    assert not legal(space, (), (0,))


def test_a_requirement_no_declaration_can_obey() -> None:
    """A attacks if able but can't attack alone, and is the only item: the requirement can't be
    obeyed, so attacking with nothing is legal (and A alone is refused by NotAlone)."""
    space = ChooseAssignment((A,), ((P1,),), (1,), (NotAlone(A),), (Requirement(A, (P1,)),))
    assert most_obeyable(space) == 0
    assert legal(space, ())
    assert not legal(space, (0,))


# --- Costly picks (508.1d, 509.1c) ---------------------------------------------------------------


def test_a_cost_isnt_required_to_obey_a_requirement() -> None:
    """A attacks if able; attacking P1 is costly (Ghostly Prison), attacking P2 isn't. The most
    obeyed without costs is 1 (A attacks P2), so not attacking is refused, and attacking P1
    (paying) or P2 is accepted."""
    space = ChooseAssignment(
        (A,), ((P1, P2),), (1,), requirements=(Requirement(A, (P1, P2)),),
        costly=(CostlyPick(A, P1),),
    )  # fmt: skip
    assert most_obeyable(space) == 1
    assert legal(space, (0,))
    assert legal(space, (1,))
    assert not legal(space, ())


def test_when_every_pick_is_costly_nothing_is_required() -> None:
    """A attacks if able, and attacking its only target is costly: the most obeyed without costs
    is 0, so A needn't attack (Juggernaut's ruling), and may (paying)."""
    space = ChooseAssignment(
        (A,), ((P1,),), (1,), requirements=(Requirement(A, (P1,)),), costly=(CostlyPick(A, P1),)
    )
    assert most_obeyable(space) == 0
    assert legal(space, ())
    assert legal(space, (0,))


def test_costly_picks_must_name_the_spaces_items_and_choices() -> None:
    with pytest.raises(ValueError):
        ChooseAssignment((A,), ((P1,),), (1,), costly=(CostlyPick(A, P2),))
    with pytest.raises(ValueError):
        ChooseAssignment((A,), ((P1,),), (1,), costly=(CostlyPick(B, P1),))


def test_a_paid_declaration_must_still_obey_the_cost_free_maximum() -> None:
    """A and B attack if able. B may attack only P1 (costly); A may attack P1 (costly) or P2.
    Without costs the most is 1 (A attacks P2). B attacking P1 alone obeys 1 (paying): accepted.
    Nothing obeys 0: refused."""
    space = ChooseAssignment(
        (A, B), ((P1, P2), (P1,)), (1, 1),
        requirements=(Requirement(A, (P1, P2)), Requirement(B, (P1,))),
        costly=(CostlyPick(A, P1), CostlyPick(B, P1)),
    )  # fmt: skip
    assert most_obeyable(space) == 1
    assert legal(space, (), (0,))
    assert legal(space, (1,), ())
    assert legal(space, (0,), (0,))
    assert not legal(space, (), ())


# --- random_legal and the benchmark ------------------------------------------------------------


def _random_space(rng: Rng) -> ChooseAssignment:
    """A random declaration of 2 to 5 items over 4 choices (at most 2 picks each), with random
    menace, NotAlone and AtMost constraints, requirements and costly picks."""
    choices = (X, Y, Z, ObjectOption(ObjectId(4)))
    items = tuple(ObjectOption(ObjectId(20 + i)) for i in range(2 + rng.randbelow(4)))
    own = tuple(
        tuple(c for c in choices if rng.randbelow(3)) or (choices[rng.randbelow(4)],) for _ in items
    )
    maxima = tuple(1 + rng.randbelow(min(2, len(o))) for o in own)
    constraints: list[NoneOrAtLeast | NotAlone | AtMost] = [
        NoneOrAtLeast(c, 2 + rng.randbelow(2)) for c in choices if not rng.randbelow(3)
    ]
    constraints += [NotAlone(item) for item in items if not rng.randbelow(4)]
    if not rng.randbelow(3):
        constraints.append(AtMost(rng.randbelow(len(items) + 1)))
    requirements = [
        Requirement(item, tuple(c for c in o if rng.randbelow(2)) or o)
        for item, o in zip(items, own, strict=True)
        for _ in range(rng.randbelow(3))
    ]
    costly = [
        CostlyPick(item, c) for item, o in zip(items, own, strict=True) for c in o
        if not rng.randbelow(4)
    ]  # fmt: skip
    return ChooseAssignment(
        items, own, maxima, tuple(constraints), tuple(requirements), tuple(costly)
    )


def _brute_force_most(space: ChooseAssignment) -> int:
    """The most requirements any constraint-satisfying cost-free answer obeys, by enumerating
    every answer (the definition of 508.1d's maximum)."""
    from itertools import combinations, product

    from resolve.decisions.assignment import broken_constraints

    costly = {(p.item, p.choice) for p in space.costly}
    per_item: list[list[tuple[int, ...]]] = []
    for item, own, maximum in zip(space.items, space.choices, space.maxima, strict=True):
        free = [i for i, c in enumerate(own) if (item, c) not in costly]
        per_item.append(
            [combo for size in range(maximum + 1) for combo in combinations(free, size)]
        )
    best = 0
    for picks in product(*per_item):
        if not broken_constraints(space, picks):
            best = max(best, requirements_obeyed(space, picks))
    return best


def test_most_obeyable_matches_a_brute_force_search() -> None:
    """On 300 random spaces the solver's maximum equals the brute-force one."""
    rng = Rng.from_seed(7)
    for _ in range(300):
        space = _random_space(rng)
        assert most_obeyable(space) == _brute_force_most(space), space


def test_random_legal_obeys_the_most_requirements() -> None:
    """On many seeds and random spaces, ``random_legal`` gives an answer the space accepts
    (constraints satisfied, at least the cost-free maximum of requirements obeyed)."""
    for seed in range(40):
        rng = Rng.from_seed(seed)
        for _ in range(10):
            space = _random_space(rng)
            answer = random_legal(space, rng)
            space.validate(answer)
            assert requirements_obeyed(space, answer.picks) >= _brute_force_most(space)


def test_random_legal_still_varies_without_requirements() -> None:
    """Without requirements random answers stay varied: over 200 draws of two free attackers,
    each of the four declarations (neither, either, both) appears."""
    space = ChooseAssignment((A, B), ((P1,), (P1,)), (1, 1))
    rng = Rng.from_seed(3)
    seen = {random_legal(space, rng).picks for _ in range(200)}
    assert seen == {((), ()), ((0,), ()), ((), (0,)), ((0,), (0,))}


def test_random_legal_sometimes_picks_a_costly_choice() -> None:
    """A costly pick is legal, so random answers include it: A must attack, P1 costly."""
    space = ChooseAssignment(
        (A,), ((P1, P2),), (1,), requirements=(Requirement(A, (P1, P2)),),
        costly=(CostlyPick(A, P1),),
    )  # fmt: skip
    rng = Rng.from_seed(5)
    seen = {random_legal(space, rng).picks for _ in range(100)}
    assert seen == {((0,),), ((1,),)}


def _benchmark_space() -> ChooseAssignment:
    """30 blockers against 30 attackers: attackers 0-9 have menace, 10-12 are Prized Unicorns
    (each blocker must block one if able), each blocker blocks one of any attacker."""
    attackers = tuple(ObjectOption(ObjectId(100 + i)) for i in range(30))
    blockers = tuple(ObjectOption(ObjectId(200 + i)) for i in range(30))
    unicorns = attackers[10:13]
    return ChooseAssignment(
        blockers,
        (attackers,) * 30,
        (1,) * 30,
        tuple(NoneOrAtLeast(a, 2) for a in attackers[:10]),
        tuple(Requirement(b, (u,)) for b in blockers for u in unicorns),
    )


def test_solver_benchmark() -> None:
    """The M3 plan's benchmark (section 3.2): 30 against 30 with menace and three Unicorns.
    Validating an obeying answer, a disobeying one, and drawing a random legal one each take
    well under a second; the most is 30 (every blocker blocks a Unicorn)."""
    space = _benchmark_space()
    start = time.perf_counter()
    assert most_obeyable(space) == 30
    space.validate(Assignment(tuple((10 + i % 3,) for i in range(30))))
    with pytest.raises(InvalidAnswer):
        space.validate(Assignment(((0,), (0,), *(((10,),) * 28))))
    answer = random_legal(space, Rng.from_seed(1))
    space.validate(answer)
    assert time.perf_counter() - start < 1.0
