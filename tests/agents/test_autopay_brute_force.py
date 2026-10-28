"""The auto-payer's planner against a brute-force search, on small random boards and costs.

The fuzz summary counts the casts the random seats reverse although they could be paid
(``tools.fuzz.PayableCasts``), and judges "could be paid" by the planner (``plan_payment``). That
is only a fair measure if the planner never calls a payable cast unpayable. So, on random boards,
an exhaustive search through the engine itself (copying the state at each choice, and trying
every answer to each payment decision) tells whether any sequence of answers completes the
action: casting a spell, or, on some boards, activating Selesnya Signet with priority (its {1},
605.3a). Whenever it does, the planner must find a plan; whenever the planner finds a plan, the
auto-payer must complete the action with it.

A board: up to six permanents of P0's (lands, mana rocks and mana creatures, some tapped, some
creatures summoning-sick, 302.6), a pool of up to two units (one maybe restricted to Dinosaurs,
106.6), a commander or none (903.4), and an opponent with permanents and mana of their own, which
P0 can't use (106.4, 602.2).

The search is the engine's own rules (601.2g-h, 602.5, 605.3a-c, 106.1a, 106.6, 107.4, 302.6,
903.4), not the planner's model. To keep it small it activates the mana abilities offered while
paying one cost in increasing object order. That loses no payment, given what holds for every
implemented mana ability:

- (a) each is activated at most once per action (each costs {T}); the ordering would also drop a
  second activation of an ability without {T}, should one exist;
- (b) whether an ability can be activated and what it adds don't depend on what else was tapped
  or activated (Temple of the False God counts lands, tapped or not);
- (c) ``ACTIVATE_MANA_ABILITIES`` is asked whenever any ability is offered, even when the pool
  already pays (``PayCosts.step``), so a later cost can still activate what an earlier one
  didn't;
- (d) 601.2h asks which units to spend whenever the ways to pay differ (identical units are
  interchangeable), and a restriction (106.6) doesn't depend on when its mana was made.

So activating a source earlier only puts its mana in the pool sooner, where it can pay the same
costs; an ability with a mana cost still gets its cost paid inside its own activation (605.3a).
A new kind of mana ability that breaks (a) to (d) needs the search changed with it.
"""

from __future__ import annotations

import copy
from collections.abc import Callable

from resolve.agents.autopay import AutoPayAgent, plan_payment
from resolve.cards.primitives.restrictions import SpendOnlyOnSubtype
from resolve.cards.primitives.words import SubtypeWord
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.request import DecisionAnswer, DecisionRequest
from resolve.decisions.spaces import (
    ActivateAbilityOption,
    Amounts,
    AnswerValue,
    ChooseCounts,
    ChooseOne,
    Pick,
    PlayerOption,
)
from resolve.engine.api import pending_decision, submit, view_for
from resolve.engine.view import PlayerView
from resolve.errors import InvalidAnswer
from resolve.events.mana import ManaAdded
from resolve.events.spells import SpellCast
from resolve.state.config import GameConfig
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import ManaType
from resolve.state.rng import Rng
from resolve.state.turn import Phase
from tests.casting_support import activate_with_priority, cast, choose_targets, choose_x, records
from tests.scenario import Scenario, run_script

P0, P1 = PlayerId(0), PlayerId(1)
SOURCES = (
    "Forest",
    "Plains",
    "Mountain",
    "Island",
    "Swamp",
    "Sol Ring",
    "Selesnya Signet",
    "Arcane Signet",
    "Command Tower",
    "Avacyn's Pilgrim",
    "Ixalli's Lorekeeper",
    "Llanowar Elves",
    "Temple of the False God",
    "Emerald Medallion",  # not a source: green spells cost {1} less (601.2f)
    "Kinjalli's Caller",  # Dinosaur spells cost {1} less
)
CREATURES = ("Avacyn's Pilgrim", "Ixalli's Lorekeeper", "Llanowar Elves")
SPELLS = (
    "Grizzly Bears",  # {1}{G}
    "Savannah Lions",  # {W}
    "Hill Giant",  # {3}{R}
    "Test Raptor",  # {1}{G}, a Dinosaur (106.6)
    "Sol Ring",  # {1}
    "Selesnya Signet",  # {2}
    "Avacyn's Pilgrim",  # {G}
    "Test Blaze",  # {X}{R}, X from 0 to 3: the total cost has X's value (601.2f)
)
COMMANDERS = (None, "Avacyn's Pilgrim", "Hill Giant", "Savannah Lions")
DINOSAUR = SpendOnlyOnSubtype(SubtypeWord("Dinosaur"))
PAYMENT = (
    DecisionKind.ACTIVATE_MANA_ABILITIES,
    DecisionKind.PAY_COSTS,
    DecisionKind.CHOOSE_COLOR,
)
QUICK_BOARDS = 150
"""Boards by default: a few seconds, both outcomes well represented."""
THOROUGH_BOARDS = 20_000
"""Boards with ``--thorough`` (docs/verification.md): a few minutes; rare boards, such as one
Signet's mana paying another's cost, turn up."""


def pick[T](rng: Rng, items: tuple[T, ...]) -> T:
    return items[rng.randbelow(len(items))]


Done = Callable[[GameState], bool]
"""Whether the action a board starts has been completed."""


def random_board(rng: Rng) -> tuple[GameState, str, Done]:
    """A random board (module docstring) with P0's action begun: a spell cast and its payment
    pending, or, on half of the boards with an untapped Selesnya Signet, that Signet
    activated with priority. Returns the state, a description for failure messages, and whether
    the action has been completed."""
    commander = pick(rng, COMMANDERS)
    config = GameConfig.standard() if commander is None else GameConfig.commander_game()
    scenario = Scenario(2, config=config)
    if commander is not None:
        scenario.commander(P0, commander)
    names = [pick(rng, SOURCES) for _ in range(1 + rng.randbelow(6))]
    permanents: list[ObjectId] = []
    shown: list[str] = []
    for name in names:
        sick = name in CREATURES and rng.randbelow(3) == 0
        (obj,) = scenario.battlefield(P0, [name], entered_turn=1 if sick else 0)
        permanents.append(obj)
        if rng.randbelow(5) == 0:
            scenario.tap(obj)
            shown.append(name + " (tapped)")
        else:
            shown.append(name + (" (sick)" if sick else ""))
    pool = [pick(rng, tuple(ManaType)) for _ in range(rng.randbelow(3))]
    if pool and rng.randbelow(3) == 0:
        scenario.mana(P0, pool[0], restriction=DINOSAUR)
        pool = pool[1:]
    scenario.mana(P0, *pool)
    # The opponent's resources, never P0's to use (106.4, 602.2).
    scenario.battlefield(P1, [pick(rng, SOURCES) for _ in range(rng.randbelow(3))])
    scenario.mana(P1, *[pick(rng, tuple(ManaType)) for _ in range(rng.randbelow(3))])
    spell = pick(rng, SPELLS)
    (card,) = scenario.hand(P0, [spell])
    scenario.at(Phase.PRECOMBAT_MAIN, number=1)
    state = scenario.build()
    units = [u.type.value + ("*" if u.restriction else "") for u in state.player(P0).mana_pool]
    where = f"from {shown}, pool {units}, commander {commander}"
    signets = [
        obj
        for obj, name in zip(permanents, names, strict=True)
        if name == "Selesnya Signet" and not state.objects[obj].tapped
    ]
    if signets and rng.randbelow(2) == 0:
        signet = signets[0]
        run_script(state, activate_with_priority(signet))

        def signet_done(state: GameState) -> bool:
            return any(
                unit.source == signet for added in records(state, ManaAdded) for unit in added.mana
            )

        return state, f"Selesnya Signet #{signet} with priority {where}", signet_done
    run_script(state, cast(card, P0))
    if spell == "Test Blaze":
        x = rng.randbelow(4)
        run_script(state, choose_x(x), choose_targets(PlayerOption(P1)))
        spell = f"{spell} (X = {x})"
    return state, f"{spell} {where}", lambda state: bool(records(state, SpellCast))


def counts(space: ChooseCounts) -> list[tuple[int, ...]]:
    """Every answer inside a ``ChooseCounts`` space."""
    found: list[tuple[int, ...]] = []

    def fill(index: int, left: int, chosen: tuple[int, ...]) -> None:
        if index == len(space.maxima):
            if left == 0:
                found.append(chosen)
            return
        for amount in range(min(space.maxima[index], left) + 1):
            fill(index + 1, left - amount, (*chosen, amount))

    fill(0, space.total, ())
    return found


def answers(
    request: DecisionRequest, last: dict[ObjectId | None, ObjectId]
) -> list[tuple[AnswerValue, dict[ObjectId | None, ObjectId]]]:
    """Every answer the search tries, with the last source activated for each cost after it."""
    space = request.space
    if isinstance(space, ChooseCounts):
        return [(Amounts(amounts), last) for amounts in counts(space)]
    assert isinstance(space, ChooseOne)
    tried: list[tuple[AnswerValue, dict[ObjectId | None, ObjectId]]] = []
    for index, option in enumerate(space.options):
        if isinstance(option, ActivateAbilityOption):
            previous = last.get(request.source)
            if previous is not None and option.object <= previous:
                continue
            tried.append((Pick(index), {**last, request.source: option.object}))
        else:
            tried.append((Pick(index), last))
    return tried


def payable_by_search(state: GameState, done: Done) -> bool:
    """Whether some answers to the pending payment decisions complete the action (601.2i)."""

    def search(state: GameState, last: dict[ObjectId | None, ObjectId]) -> bool:
        if done(state):
            return True
        request = pending_decision(state)
        if request is None or request.kind not in PAYMENT:
            return False  # reversed (733.1), or back at priority
        for value, after in answers(request, last):
            trial = copy.deepcopy(state)
            try:
                submit(trial, DecisionAnswer(request.id, request.player, value))
            except InvalidAnswer:
                continue  # 601.2h, 106.6: that mana doesn't pay
            if search(trial, after):
                return True
        return False

    return search(state, {})


def done_by_autopayer(state: GameState, done: Done) -> bool:
    agent = AutoPayAgent(_Unused())
    while (request := pending_decision(state)) is not None and request.kind in (
        *PAYMENT,
        DecisionKind.REVERSE_MANA_ABILITIES,
    ):
        submit(state, agent.decide(view_for(state, request.player), request))
    return done(state)


class _Unused:
    def decide(self, view: PlayerView, request: DecisionRequest) -> DecisionAnswer:
        raise AssertionError(f"the auto-payer delegated a {request.kind.value} decision")


def test_the_presets() -> None:
    assert (QUICK_BOARDS, THOROUGH_BOARDS) == (150, 20_000)


def test_the_planner_finds_a_plan_whenever_brute_force_finds_a_payment(thorough: bool) -> None:
    check_planner(THOROUGH_BOARDS if thorough else QUICK_BOARDS)


def check_planner(boards: int, seed: int = 2026_10_22) -> None:
    """Compare the planner with the search on ``boards`` random boards (module docstring)."""
    rng = Rng.from_seed(seed)
    judged = {True: 0, False: 0}
    problems: list[str] = []
    for _ in range(boards):
        state, board, done = random_board(rng)
        request = pending_decision(state)
        if request is None or request.kind is not DecisionKind.ACTIVATE_MANA_ABILITIES:
            continue  # the engine paid without asking, or reversed at once: nothing to plan
        assert isinstance(request.space, ChooseOne)
        offered = [o for o in request.space.options if isinstance(o, ActivateAbilityOption)]
        plan = plan_payment(view_for(state, P0), P0, offered)
        payable = payable_by_search(copy.deepcopy(state), done)
        judged[payable] += 1
        if payable and plan is None:
            problems.append(f"brute force pays but the planner finds no plan: {board}")
        if plan is not None and not done_by_autopayer(copy.deepcopy(state), done):
            problems.append(f"the planner's plan doesn't complete the action: {board}")
        if plan is not None and not payable:
            problems.append(f"the planner finds a plan brute force doesn't: {board}")
    assert not problems, "\n".join(problems)
    # The boards exercise both outcomes, not just one.
    assert min(judged.values()) >= boards // 10, judged
