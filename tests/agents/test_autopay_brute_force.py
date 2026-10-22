"""The auto-payer's planner against a brute-force search, on small random boards and costs.

The fuzz summary counts the casts the random seats reverse although they could be paid
(``tools.fuzz.PayableCasts``), and judges "could be paid" by the planner (``plan_payment``). That
is only a fair measure if the planner never calls a payable cast unpayable. So: on random boards
of up to four mana sources, a mana pool of up to two units (some restricted, 106.6) and a spell,
an exhaustive search through the engine itself (copying the state at each choice, and trying
every answer to each payment decision) tells whether any sequence of answers casts the spell.
Whenever it does, the planner must find a plan. Conversely, whenever the planner finds a plan,
the auto-payer must cast the spell with it.

The search is the engine's own rules (601.2g-h, 605.3a-c, 106.1a, 106.6, 107.4, 903.4), not the
planner's model. To keep it small it activates the mana abilities offered while paying one cost
in increasing object order; that loses no payment: mana in the pool may pay any later cost, and
601.2h asks which units to spend whenever two or more ways exist, so activating a source earlier
never takes away a choice (an ability with a mana cost still gets its cost paid inside its own
activation, 605.3a).
"""

from __future__ import annotations

import copy

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
)
from resolve.engine.api import pending_decision, submit, view_for
from resolve.engine.view import PlayerView
from resolve.errors import InvalidAnswer
from resolve.events.spells import SpellCast
from resolve.state.config import GameConfig
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import ManaType
from resolve.state.rng import Rng
from resolve.state.turn import Phase
from tests.casting_support import cast, records
from tests.scenario import Scenario, run_script

P0 = PlayerId(0)
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
)
SPELLS = (
    "Grizzly Bears",  # {1}{G}
    "Savannah Lions",  # {W}
    "Hill Giant",  # {3}{R}
    "Test Raptor",  # {1}{G}, a Dinosaur (106.6)
    "Sol Ring",  # {1}
    "Selesnya Signet",  # {2}
    "Avacyn's Pilgrim",  # {G}
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


def random_board(rng: Rng) -> tuple[GameState, str]:
    """P0's main phase with up to four sources, up to two units of mana and a spell cast: the
    spell's payment is pending. Returns the state and a description for failure messages."""
    commander = pick(rng, COMMANDERS)
    config = GameConfig.standard() if commander is None else GameConfig.commander_game()
    scenario = Scenario(2, config=config)
    if commander is not None:
        scenario.commander(P0, commander)
    sources = [pick(rng, SOURCES) for _ in range(1 + rng.randbelow(4))]
    scenario.battlefield(P0, sources)
    pool = [pick(rng, tuple(ManaType)) for _ in range(rng.randbelow(3))]
    restricted = bool(pool) and rng.randbelow(3) == 0
    if restricted:
        scenario.mana(P0, pool[0], restriction=DINOSAUR)
        pool = pool[1:]
    scenario.mana(P0, *pool)
    spell = pick(rng, SPELLS)
    (card,) = scenario.hand(P0, [spell])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(card, P0))
    shown = [
        unit.type.value + ("*" if unit.restriction else "") for unit in state.player(P0).mana_pool
    ]
    return state, f"{spell} from {sources}, pool {shown}, commander {commander}"


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


def payable_by_search(state: GameState) -> bool:
    """Whether some answers to the pending payment decisions cast the spell (601.2i)."""

    def search(state: GameState, last: dict[ObjectId | None, ObjectId]) -> bool:
        if records(state, SpellCast):
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


def cast_by_autopayer(state: GameState) -> bool:
    agent = AutoPayAgent(_Unused())
    while (request := pending_decision(state)) is not None and request.kind in (
        *PAYMENT,
        DecisionKind.REVERSE_MANA_ABILITIES,
    ):
        submit(state, agent.decide(view_for(state, request.player), request))
    return bool(records(state, SpellCast))


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
        state, board = random_board(rng)
        request = pending_decision(state)
        if request is None or request.kind is not DecisionKind.ACTIVATE_MANA_ABILITIES:
            continue  # the engine paid without asking, or reversed at once: nothing to plan
        assert isinstance(request.space, ChooseOne)
        offered = [o for o in request.space.options if isinstance(o, ActivateAbilityOption)]
        plan = plan_payment(view_for(state, P0), P0, offered)
        payable = payable_by_search(copy.deepcopy(state))
        judged[payable] += 1
        if payable and plan is None:
            problems.append(f"brute force pays but the planner finds no plan: {board}")
        if plan is not None and not cast_by_autopayer(copy.deepcopy(state)):
            problems.append(f"the planner's plan doesn't cast the spell: {board}")
        if plan is not None and not payable:
            problems.append(f"the planner finds a plan brute force doesn't: {board}")
    assert not problems, "\n".join(problems)
    # The boards exercise both outcomes, not just one.
    assert min(judged.values()) >= boards // 10, judged
