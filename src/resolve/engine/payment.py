"""Paying costs: the mana part (601.2g-h, 605.3a, 118.3, design.md §17.7).

``PayCosts(payer, cost, paying_for)`` pays a mana cost in two parts:

1. **601.2g:** the payer may activate mana abilities first (605.3a). ``ACTIVATE_MANA_ABILITIES``
   is a ``ChooseOne`` of ``PAY`` ("done: pay now") and each mana ability the payer can activate,
   asked again after each activation. Activating them isn't mandatory (118.3c). With no ability
   to activate, "pay" is the only answer and nothing is asked.
2. **601.2h:** the pool is grouped into classes of identical units (equal ``Mana`` values: type
   and source), and ``PAY_COSTS`` is a ``ChooseCounts`` of how many units of each class to spend,
   adding up to the cost's total. ``check_answer`` refuses a choice that doesn't pay it: each
   colored symbol needs a unit of its color (107.4a), each {C} a colorless unit (107.4c), and
   generic mana takes any (107.4b). With exactly one paying choice nothing is asked; with none,
   the cost can't be paid (118.3), and the action paying it is reversed (733.1).

It uses only the payer's own pool and permanents (723.5a), and its decisions are the payer's
(the engine loop maps them through ``defaults.deciding_player``).

``PayCosts`` isn't a task on the stack: the task of the action being paid for (``CastSpell``)
holds it in a field and calls ``step``, ``check_answer`` and ``resume``, because the action needs
the mana abilities activated while paying in order to reverse them (733.1; docs/decisions.md).
``step`` and ``resume`` give a ``NeedDecision``, a ``Push`` of tasks to run before asking again
(an activation), ``Paid`` or ``Unpayable``.

Hybrid, Phyrexian and snow symbols (M9) and {X} (M2.7) raise ``NotImplementedRule``. Mana
restrictions (106.6) and non-mana components arrive in M2.4 and M4.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import TYPE_CHECKING

from resolve.cards.primitives.abilities import ActivatedManaAbility
from resolve.data.mana_cost import ManaCost, SymbolKind
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import (
    ActivateAbilityOption,
    Amounts,
    AnswerValue,
    ChooseCounts,
    ChooseOne,
    ManaOption,
    NamedOption,
    Pick,
)
from resolve.effects.characteristics import characteristics
from resolve.engine.mana import ActivateManaAbility
from resolve.errors import EngineError, InvalidAnswer, NotImplementedRule
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import Mana, ManaType, describe_mana
from resolve.tasks import NeedDecision, Push
from resolve.values import Immutable

if TYPE_CHECKING:
    from resolve.decisions.request import DecisionRequest
    from resolve.state.game import GameState

PAY = NamedOption("pay")
"""601.2g: done activating mana abilities; pay the cost now."""


def mana_ability_options(state: GameState, player: PlayerId) -> tuple[ActivateAbilityOption, ...]:
    """The mana abilities ``player`` can activate now (605.3a, 602.2: of the permanents they
    control), in battlefield order and ability order."""
    options: list[ActivateAbilityOption] = []
    for obj in state.battlefield:
        if state.objects[obj].controller != player:
            continue
        for index, ability in enumerate(characteristics(state, obj).abilities):
            if isinstance(ability, ActivatedManaAbility) and ability.can_activate(
                state, obj, player
            ):
                options.append(ActivateAbilityOption(obj, index))
    return tuple(options)


@dataclass(frozen=True)
class ManaActivation(Immutable):
    """A mana ability activated while paying: ability ``ability`` of ``source`` (733.1).

    ``log_from`` and ``log_to`` delimit the event log entries of its activation (``log_to`` is
    ``None`` until it has finished), so a reversal can keep its results as they happened.
    """

    source: ObjectId
    ability: int
    log_from: int
    log_to: int | None = None


@dataclass(frozen=True)
class Paid(Immutable):
    """The cost is paid with ``mana`` (the units to spend from the pool, 601.2h)."""

    mana: tuple[Mana, ...]


@dataclass(frozen=True)
class Unpayable(Immutable):
    """The cost can't be paid (118.3, 601.2h)."""


PaymentStep = NeedDecision | Push | Paid | Unpayable


@dataclass(frozen=True)
class ManaNeed(Immutable):
    """What a mana cost requires: units of each colored type and of colorless mana, and a total
    (the generic part takes any mana, 107.4b)."""

    typed: tuple[tuple[ManaType, int], ...]
    total: int

    def paid_by(self, units: Sequence[tuple[Mana, int]]) -> bool:
        """Whether ``units`` (each a unit and how many of it) pay exactly this need."""
        if sum(count for _, count in units) != self.total:
            return False
        for mana_type, needed in self.typed:
            if sum(count for unit, count in units if unit.type is mana_type) < needed:
                return False
        return True


def mana_need(cost: ManaCost) -> ManaNeed:
    """What ``cost`` requires (107.4a-c); ``NotImplementedRule`` for symbols paid otherwise."""
    typed: dict[ManaType, int] = {}
    total = 0
    for symbol in cost.symbols:
        match symbol.kind:
            case SymbolKind.COLORED:
                mana_type = ManaType(symbol.colors[0].value)  # 107.4a
                typed[mana_type] = typed.get(mana_type, 0) + 1
                total += 1
            case SymbolKind.COLORLESS:
                typed[ManaType.COLORLESS] = typed.get(ManaType.COLORLESS, 0) + 1  # 107.4c
                total += 1
            case SymbolKind.GENERIC:
                total += symbol.number  # 107.4b
            case SymbolKind.VARIABLE:
                raise NotImplementedRule("107.3a: paying a cost with {X}")
            case SymbolKind.SNOW:
                raise NotImplementedRule("107.4h: paying {S} with mana from a snow source")
            case _:
                raise NotImplementedRule(
                    "107.4e: paying hybrid and Phyrexian mana symbols (107.4f, 601.2b)"
                )
    return ManaNeed(tuple(sorted(typed.items(), key=lambda item: item[0].value)), total)


def mana_classes(pool: Sequence[Mana]) -> tuple[tuple[Mana, int], ...]:
    """The pool grouped into classes of identical units, in order of first appearance."""
    counts: dict[Mana, int] = {}
    for unit in pool:
        counts[unit] = counts.get(unit, 0) + 1
    return tuple(counts.items())


def payments(
    classes: Sequence[tuple[Mana, int]], need: ManaNeed, limit: int
) -> list[tuple[int, ...]]:
    """Up to ``limit`` ways (amounts per class) to pay ``need`` from ``classes``."""
    found: list[tuple[int, ...]] = []
    maxima = [count for _, count in classes]
    # Capacity of each typed requirement from class i on, to prune hopeless branches.
    suffix: list[dict[ManaType, int]] = [{} for _ in range(len(classes) + 1)]
    for i in range(len(classes) - 1, -1, -1):
        suffix[i] = dict(suffix[i + 1])
        unit, count = classes[i]
        suffix[i][unit.type] = suffix[i].get(unit.type, 0) + count
    rest_total = [sum(maxima[i:]) for i in range(len(classes) + 1)]
    chosen: list[int] = []

    def search(i: int, left: int, have: dict[ManaType, int]) -> None:
        if len(found) >= limit:
            return
        for mana_type, needed in need.typed:
            if have.get(mana_type, 0) + suffix[i].get(mana_type, 0) < needed:
                return
        if i == len(classes):
            if left == 0:
                found.append(tuple(chosen))
            return
        unit, maximum = classes[i]
        for amount in range(max(0, left - rest_total[i + 1]), min(maximum, left) + 1):
            chosen.append(amount)
            have[unit.type] = have.get(unit.type, 0) + amount
            search(i + 1, left - amount, have)
            have[unit.type] -= amount
            chosen.pop()

    search(0, need.total, {})
    return found


class PaymentStage(Enum):
    """Where ``PayCosts`` is: offering mana abilities (601.2g) or paying (601.2h)."""

    ACTIVATE = "activate"
    PAY = "pay"


@dataclass(slots=True)
class PayCosts:
    """``payer`` pays ``cost``, the mana part of a total cost, for ``paying_for`` (601.2g-h).

    ``activations`` lists the mana abilities activated while paying, in order (733.1).
    """

    payer: PlayerId
    cost: ManaCost
    paying_for: ObjectId | None = None
    stage: PaymentStage = PaymentStage.ACTIVATE
    activations: list[ManaActivation] = field(default_factory=list[ManaActivation])

    def step(self, state: GameState) -> PaymentStep:
        """Ask, activate or finish; safe to call again after it asked (design.md §5)."""
        if self.activations and self.activations[-1].log_to is None:
            # The activation pushed last has finished: its log entries end here.
            self.activations[-1] = replace(self.activations[-1], log_to=len(state.event_log))
        if self.stage is PaymentStage.ACTIVATE:
            abilities = mana_ability_options(state, self.payer)
            if abilities:
                return NeedDecision(
                    player=self.payer,
                    kind=DecisionKind.ACTIVATE_MANA_ABILITIES,
                    space=ChooseOne((PAY, *abilities)),
                    prompt=f"Activate mana abilities, or pay {self.cost.text}.",
                    rules=("601.2g", "605.3a"),
                    source=self.paying_for,
                )
            self.stage = PaymentStage.PAY
        need = mana_need(self.cost)
        pool = state.player(self.payer).mana_pool
        classes = mana_classes(pool)
        found = payments(classes, need, limit=2)
        if not found:
            return Unpayable()  # 118.3
        if len(found) == 1:
            return Paid(_units(classes, found[0]))
        return NeedDecision(
            player=self.payer,
            kind=DecisionKind.PAY_COSTS,
            space=ChooseCounts(
                tuple(ManaOption(unit) for unit, _ in classes),
                tuple(count for _, count in classes),
                need.total,
            ),
            prompt=f"Pay {self.cost.text} from {describe_mana(tuple(pool))}.",
            rules=("601.2h", "118.3a"),
            source=self.paying_for,
        )

    def check_answer(self, state: GameState, answer: AnswerValue) -> None:
        """Refuse a payment that doesn't pay the cost (601.2h, 107.4a-c)."""
        if self.stage is not PaymentStage.PAY:
            return
        if not isinstance(answer, Amounts):
            raise EngineError(f"PayCosts can't check {answer!r}")
        classes = mana_classes(state.player(self.payer).mana_pool)
        chosen = [(unit, amount) for (unit, _), amount in zip(classes, answer.amounts, strict=True)]
        if not mana_need(self.cost).paid_by(chosen):
            raise InvalidAnswer(
                f"that mana doesn't pay {self.cost.text}: colored symbols need mana of their "
                "color and {C} colorless mana (107.4a, 107.4c)"
            )

    def resume(
        self, state: GameState, request: DecisionRequest, answer: AnswerValue
    ) -> PaymentStep:
        """Continue with the (checked) answer to the decision ``step`` asked."""
        if self.stage is PaymentStage.ACTIVATE:
            if not isinstance(request.space, ChooseOne) or not isinstance(answer, Pick):
                raise EngineError(f"PayCosts can't resume with {answer!r}")
            match request.space.chosen(answer):
                case ActivateAbilityOption(object=source, ability=index):
                    self.activations.append(ManaActivation(source, index, len(state.event_log)))
                    return Push((ActivateManaAbility(self.payer, source, index),))
                case _:
                    self.stage = PaymentStage.PAY
                    return self.step(state)
        if not isinstance(answer, Amounts):
            raise EngineError(f"PayCosts can't resume with {answer!r}")
        classes = mana_classes(state.player(self.payer).mana_pool)
        return Paid(_units(classes, answer.amounts))


def _units(classes: Sequence[tuple[Mana, int]], amounts: Sequence[int]) -> tuple[Mana, ...]:
    return tuple(
        unit for (unit, _), amount in zip(classes, amounts, strict=True) for _ in range(amount)
    )
