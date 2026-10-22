"""The auto-payer: an agent-side helper that pays mana costs (design.md §6, "Convenience lives
outside the engine").

The engine always asks the full question; ``AutoPayAgent(inner)`` answers the payment decisions
itself and passes every other decision to ``inner``:

- ``ACTIVATE_MANA_ABILITIES`` (601.2g): the next mana ability of its plan, or "pay";
- ``PAY_COSTS`` (601.2h): the units of the pool to spend;
- ``CHOOSE_COLOR`` (106.1a) while a payment is under way (with none, ``inner`` chooses);
- ``REVERSE_MANA_ABILITIES`` (733.1): every mana ability is reversed.

It is stateless: each answer is worked out again from the view and the request alone (rule 4),
so the same view and request always give the same answer. What it reads:

- ``PlayerView.payments``: the costs being paid, outermost first (a spell's, then the mana cost
  of a mana ability activated while paying it, 605.3a), with the mana restrictions that allow
  spending mana on each (106.6);
- the mana pool and the permanents' abilities (``ObjectView.abilities``) of the player whose
  decision it is (``request.for_player``): deciding for a controlled player, it uses only that
  player's resources (723.5a);
- the mana abilities the request offers (601.2g, 605.3c: not those being activated).

**The plan** (``plan_payment``). A plan is a set of offered mana abilities to activate such that
every cost under way can be paid: each colored symbol by mana of its color (107.4a), each {C} by
colorless mana (107.4c), generic mana by any (107.4b), restricted mana only where allowed
(106.6). The mana a mana ability under way will add pays only the costs outside its own. The
planned mana abilities with a mana cost (Selesnya Signet) are activated one after another, and
each order is tried: the mana of each pays the costs under way and the costs of those activated
after it (602.2b), never its own. Their costs aren't paid with restricted mana: a restriction is
judged by the engine only for the payments under way (``PaymentView.spendable``), and no
implemented card's restriction allows spending on a mana ability with a mana cost.
``tests/agents/test_autopay_brute_force.py`` checks that the planner finds a plan whenever a
search through the engine finds a payment. Among the plans, it prefers, in order:

1. the fewest sources of flexible mana (a choice of color, such as Command Tower);
2. the fewest sources of restricted mana (Ixalli's Lorekeeper): both are kept for where they're
   required;
3. the fewest permanents tapped;
4. exact colors: the fewest units of a color no symbol asks for;
5. the least mana left over;
6. the earliest permanents, in the order offered.

Whether a set of abilities pays is a bipartite matching of the costs' symbols to units of mana.
Only the abilities whose mana pays the innermost cost are activated now (one per decision); the
others are activated when the outer payment resumes, and the cost of a mana ability while it is
being activated. With no plan it answers "pay", and the action is reversed (118.3, 733.1).

**Paying from the pool** (601.2h). Of the ways to pay the innermost cost (the engine's
``payments``), it picks the one that leaves the most colored and {C} symbols of the outer costs
payable from what's left and the mana of the abilities under way (a mana ability activated
later for an outer cost can pay a generic symbol, but a colored one only with its color), then
the most symbols, then spends restricted mana first and mana of the cost's colors first.

**Colors** (106.1a). It picks the color that lets the most colored symbols, then the most
symbols, of the costs under way be paid from the pool, the mana of the abilities under way and
the new unit. Mana abilities of flexible mana are activated last, so the rest of the plan's
mana is already in the pool.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations, permutations

from resolve.agents.base import Agent
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.request import DecisionAnswer, DecisionRequest
from resolve.decisions.spaces import (
    ActivateAbilityOption,
    Amounts,
    AnswerValue,
    ChooseCounts,
    ChooseOne,
    ChooseSubset,
    ColorOption,
    ManaOption,
    Pick,
    PickMany,
)
from resolve.engine.payment import PAY, ManaNeed, mana_need, payments
from resolve.engine.view import AbilityView, ManaOutput, PaymentView, PlayerView
from resolve.errors import NotImplementedRule
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import ForAbility, Mana, ManaRestriction, ManaType
from resolve.values import Immutable

# How many ways to pay from the pool ``choose_payment`` compares, at most.
PAYMENT_LIMIT = 1000


@dataclass(frozen=True)
class Plan(Immutable):
    """A payment plan: ``sources``, every mana ability to activate for the payments under way
    (including those activated while paying another's mana cost, and those for an outer cost);
    ``now``, those to activate for the innermost payment, in the order to activate them."""

    sources: tuple[ActivateAbilityOption, ...]
    now: tuple[ActivateAbilityOption, ...]


# --- The model: demands (costs), units of mana and the matching between them ------------------


@dataclass(frozen=True)
class _Demand:
    """A cost to pay: ``need``, and the restrictions that allow spending mana on it (106.6;
    ``None``: only unrestricted mana)."""

    need: ManaNeed
    spendable: tuple[ManaRestriction, ...] | None


@dataclass(frozen=True)
class _Unit:
    """One unit of mana, in the pool or to come: its type, or the types it may be chosen as
    (106.1a); its restriction; ``reach``, the demands it may pay given when it exists (``None``:
    any); and the planned source it comes from (``None``: the pool or an ability under way)."""

    types: tuple[ManaType, ...]
    restriction: ManaRestriction | None
    reach: tuple[int, ...] | None = None
    source: int | None = None


Slot = tuple[int, ManaType | None]
"""A symbol to pay: its demand and the type it needs (``None``: generic, 107.4b)."""


def _slots(demands: Sequence[_Demand], order: Sequence[int]) -> list[Slot]:
    """Every symbol of the demands, demand by demand in ``order``, colored and {C} symbols before
    generic ones."""
    slots: list[Slot] = []
    for index in order:
        need = demands[index].need
        typed = 0
        for mana_type, count in need.typed:
            slots += [(index, mana_type)] * count
            typed += count
        slots += [(index, None)] * (need.total - typed)
    return slots


def _may_pay(unit: _Unit, slot: Slot, demands: Sequence[_Demand]) -> bool:
    demand, needed = slot
    if unit.reach is not None and demand not in unit.reach:
        return False
    if unit.restriction is not None:
        spendable = demands[demand].spendable
        if spendable is None or unit.restriction not in spendable:
            return False  # 106.6
    return needed is None or needed in unit.types  # 107.4a-c


def _match(
    slots: Sequence[Slot], units: Sequence[_Unit], demands: Sequence[_Demand]
) -> list[int | None]:
    """A maximum matching of slots to units (each unit pays at most one symbol), found by
    augmenting paths in slot order, so an earlier slot is never left unpaid for a later one."""
    owner: list[int | None] = [None] * len(units)
    matched: list[int | None] = [None] * len(slots)

    def augment(slot: int, seen: list[bool]) -> bool:
        for unit in range(len(units)):
            if seen[unit] or not _may_pay(units[unit], slots[slot], demands):
                continue
            seen[unit] = True
            holder = owner[unit]
            if holder is None or augment(holder, seen):
                owner[unit] = slot
                matched[slot] = unit
                return True
        return False

    for slot in range(len(slots)):
        augment(slot, [False] * len(units))
    return matched


def _assign(slots: Sequence[Slot], units: Sequence[_Unit], demands: Sequence[_Demand]) -> list[int]:
    """The first complete assignment of units to slots in slot order: each slot takes the
    earliest unit that still lets every later slot be paid. The slots must all be payable."""
    taken: list[int] = []
    for index, slot in enumerate(slots):
        for unit in range(len(units)):
            if unit in taken or not _may_pay(units[unit], slot, demands):
                continue
            rest = [u for u in range(len(units)) if u not in taken and u != unit]
            matched = _match(slots[index + 1 :], [units[u] for u in rest], demands)
            if all(m is not None for m in matched):
                taken.append(unit)
                break
        else:
            raise ValueError("the slots can't all be paid")
    return taken


# --- What the view says ------------------------------------------------------------------------


def _payments(view: PlayerView, player: PlayerId) -> tuple[PaymentView, ...]:
    """The payments under way of ``player``, outermost first."""
    return tuple(payment for payment in view.payments if payment.payer == player)


def _ability(view: PlayerView, obj: ObjectId, index: int) -> AbilityView | None:
    for shown in view.battlefield:
        if shown.id == obj:
            for ability in shown.abilities:
                if ability.index == index:
                    return ability
    return None


def _pool(view: PlayerView, player: PlayerId) -> tuple[Mana, ...]:
    for summary in view.players:
        if summary.id == player:
            return summary.mana_pool
    return ()


def _output_units(
    output: ManaOutput, reach: tuple[int, ...] | None, source: int | None = None
) -> list[_Unit]:
    if output.fixed:
        return [_Unit((t,), output.restriction, reach, source) for t in output.fixed]
    if output.one_of:
        return [_Unit(output.one_of, output.restriction, reach, source)]
    return []  # 106.5: it adds no mana


def _chain(view: PlayerView, player: PlayerId) -> tuple[list[_Demand], list[_Unit]] | None:
    """The demands of the payments under way, outermost first, and the units already there or
    on their way: the pool (for any demand) and the mana of each mana ability under way (for
    the demands outside its own cost). ``None`` if a cost can't be planned for."""
    demands: list[_Demand] = []
    try:
        for payment in _payments(view, player):
            demands.append(_Demand(mana_need(payment.cost), payment.spendable))
    except NotImplementedRule:
        return None
    units = [_Unit((unit.type,), unit.restriction) for unit in _pool(view, player)]
    for level, payment in enumerate(_payments(view, player)):
        purpose = payment.purpose
        if level and isinstance(purpose, ForAbility):
            ability = _ability(view, purpose.source, purpose.ability)
            if ability is not None and ability.mana is not None:
                units += _output_units(ability.mana, tuple(range(level)))
    return demands, units


# --- Planning ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Source:
    """An offered mana ability: the option naming it, its mana cost and the mana it adds."""

    option: ActivateAbilityOption
    position: int
    cost: ManaNeed | None
    output: ManaOutput

    @property
    def flexible(self) -> bool:
        return not self.output.fixed and len(self.output.one_of) > 1

    @property
    def restricted(self) -> bool:
        return self.output.restriction is not None

    @property
    def signature(self) -> tuple[object, ...]:
        return (self.cost, self.output)


def _sources(view: PlayerView, offered: Sequence[ActivateAbilityOption]) -> list[_Source]:
    """The offered mana abilities that add mana, with what they add; abilities whose cost can't
    be planned for are left out."""
    found: list[_Source] = []
    for position, option in enumerate(offered):
        ability = _ability(view, option.object, option.ability)
        if ability is None or ability.mana is None:
            continue
        if not ability.mana.fixed and not ability.mana.one_of:
            continue  # 106.5: adds nothing
        try:
            cost = None if ability.mana_cost is None else mana_need(ability.mana_cost)
        except NotImplementedRule:
            continue
        found.append(_Source(option, position, cost, ability.mana))
    return found


@dataclass(frozen=True)
class _Trial:
    """A set of sources tried: whether it pays, and how good it is."""

    feasible: bool
    chosen: tuple[_Source, ...]
    score: tuple[object, ...]
    demands: tuple[_Demand, ...]
    slots: tuple[Slot, ...]
    units: tuple[_Unit, ...]
    order: tuple[int, ...] = ()  # the sources with a mana cost, in the order to activate them


def _try(demands: Sequence[_Demand], units: Sequence[_Unit], chosen: Sequence[_Source]) -> _Trial:
    """Whether the payments under way can be paid with the mana ``chosen`` adds (and the costs
    of those of them that have one), and the plan's score (lower is better).

    The sources with a mana cost are activated one after another, in some order: the mana of
    each pays the payments under way and the costs of those activated after it (602.2b: it comes
    only once its own cost is paid), never its own or an earlier one's. Each order is tried."""
    chain = len(demands)
    costly = [index for index, source in enumerate(chosen) if source.cost is not None]
    outer = tuple(range(chain))
    asked = {mana_type for demand in demands for mana_type, _ in demand.need.typed}
    asked |= {mana_type for i in costly for mana_type, _ in _cost(chosen[i]).typed}
    trial: _Trial | None = None
    for order in permutations(costly):
        all_demands = [*demands, *(_Demand(_cost(chosen[i]), None) for i in order)]
        all_units = list(units)
        for index, source in enumerate(chosen):
            reach: tuple[int, ...] | None = None
            if source.cost is not None:
                rank = order.index(index)
                reach = (*outer, *range(chain + rank + 1, chain + len(order)))
            all_units += _output_units(source.output, reach, index)
        # Innermost first: the ability costs to come, then the payments under way inside out.
        slots = _slots(all_demands, [*range(chain, len(all_demands)), *range(chain - 1, -1, -1)])
        if len(all_units) < len(slots):
            return _Trial(False, tuple(chosen), (), (), (), (), ())
        feasible = all(unit is not None for unit in _match(slots, all_units, all_demands))
        off_color = sum(
            1
            for unit in all_units
            if unit.source is not None and len(unit.types) == 1 and unit.types[0] not in asked
        )
        score = (
            sum(source.flexible for source in chosen),
            sum(source.restricted for source in chosen),
            len(chosen),
            off_color,
            len(all_units) - len(slots),
            tuple(source.position for source in chosen),
        )
        trial = _Trial(
            feasible,
            tuple(chosen),
            score,
            tuple(all_demands),
            tuple(slots),
            tuple(all_units),
            order,
        )
        if feasible:
            return trial
    assert trial is not None
    return trial


def _cost(source: _Source) -> ManaNeed:
    if source.cost is None:
        raise ValueError("the source has no mana cost")
    return source.cost


def _selections(groups: Sequence[Sequence[_Source]], size: int) -> list[list[_Source]]:
    """Every choice of ``size`` sources, taking the first sources of each group of identical
    ones, groups in order."""
    found: list[list[_Source]] = []

    def pick(index: int, left: int, chosen: list[_Source]) -> None:
        if left == 0:
            found.append(sorted(chosen, key=lambda source: source.position))
            return
        if index == len(groups):
            return
        for count in range(min(left, len(groups[index])), -1, -1):
            pick(index + 1, left - count, [*chosen, *groups[index][:count]])

    pick(0, size, [])
    return found


def plan_payment(
    view: PlayerView, player: PlayerId, offered: Sequence[ActivateAbilityOption]
) -> Plan | None:
    """The best plan to pay ``player``'s payments under way with the ``offered`` mana abilities
    (preferences in the module docstring), or ``None`` if there is none."""
    chain = _chain(view, player)
    if chain is None or not chain[0]:
        return None
    demands, units = chain
    sources = _sources(view, offered)
    groups: list[list[_Source]] = []
    for source in sources:
        for group in groups:
            if group[0].signature == source.signature:
                group.append(source)
                break
        else:
            groups.append([source])
    if not _exists(demands, units, sources):
        return None
    # A best plan uses each source's mana, so it has at most one source per symbol to pay.
    limit = sum(demand.need.total for demand in demands) + sum(
        source.cost.total for source in sources if source.cost is not None
    )
    sizes = range(min(len(sources), limit) + 1)
    by_size: dict[int, list[list[_Source]]] = {}
    # Search by the score's first three parts, in order: flexible sources, restricted sources,
    # permanents. Within the first level that pays, the rest of the score decides.
    for flex in range(sum(source.flexible for source in sources) + 1):
        for restrict in range(sum(source.restricted for source in sources) + 1):
            for size in sizes:
                if size not in by_size:
                    by_size[size] = _selections(groups, size)
                trials = [
                    trial
                    for chosen in by_size[size]
                    if sum(source.flexible for source in chosen) == flex
                    and sum(source.restricted for source in chosen) == restrict
                    and (trial := _try(demands, units, chosen)).feasible
                ]
                if trials:
                    return _plan(min(trials, key=lambda trial: trial.score), len(demands))
    return None  # pragma: no cover - _exists found a plan


def _exists(demands: Sequence[_Demand], units: Sequence[_Unit], sources: Sequence[_Source]) -> bool:
    """Whether any plan pays: adding a source without a mana cost never stops a payment, so one
    exists if every such source, with some of those with a mana cost, pays."""
    free = [source for source in sources if source.cost is None]
    costly = [source for source in sources if source.cost is not None]
    for count in range(len(costly) + 1):
        for subset in combinations(costly, count):
            chosen = sorted([*free, *subset], key=lambda source: source.position)
            if _try(demands, units, chosen).feasible:
                return True
    return False


def _plan(trial: _Trial, chain: int) -> Plan:
    """The plan of a feasible trial: activate now the sources whose mana pays the innermost
    payment, those with a mana cost first and those of flexible mana last."""
    chosen = trial.chosen
    now: list[int] = []
    assigned = _assign(trial.slots, trial.units, trial.demands)
    for (demand, _), unit in zip(trial.slots, assigned, strict=True):
        source = trial.units[unit].source
        if demand == chain - 1 and source is not None and source not in now:
            now.append(source)

    def rank(i: int) -> tuple[int, bool, int]:
        costly = trial.order.index(i) if i in trial.order else len(trial.order)
        return (costly, chosen[i].flexible, chosen[i].position)

    now.sort(key=rank)
    return Plan(tuple(source.option for source in chosen), tuple(chosen[i].option for i in now))


# --- The other answers -------------------------------------------------------------------------


def choose_payment(view: PlayerView, player: PlayerId, space: ChooseCounts) -> Amounts:
    """601.2h: how many units of each class to spend on the innermost payment (module
    docstring). The space's maxima already leave out restricted mana that can't be spent."""
    options = space.options
    classes = [
        (option.mana, maximum)
        for option, maximum in zip(options, space.maxima, strict=True)
        if isinstance(option, ManaOption)
    ]
    if len(classes) != len(options):
        raise ValueError("a PAY_COSTS space offers classes of mana")
    chain = _chain(view, player)
    if chain is None or not chain[0]:
        need = ManaNeed((), space.total)
        found = payments(classes, need, limit=1)
        return Amounts(found[0] if found else _any_counts(space))
    demands, units = chain
    innermost = len(demands) - 1
    found = payments(classes, demands[innermost].need, limit=PAYMENT_LIMIT)
    if not found:
        return Amounts(_any_counts(space))
    outer = demands[:innermost]
    asked = {mana_type for mana_type, _ in demands[innermost].need.typed}
    pool = _pool(view, player)

    # Colored and {C} symbols first: a mana ability activated later for an outer cost may pay
    # any generic symbol (107.4b), but a colored one only with its color (107.4a).
    every = _slots(outer, range(len(outer)))
    colored = [slot for slot in every if slot[1] is not None]
    slots = colored + [slot for slot in every if slot[1] is None]

    def score(amounts: tuple[int, ...]) -> tuple[int, int, int, int]:
        left = list(pool)
        for (unit, _), amount in zip(classes, amounts, strict=True):
            for _ in range(amount):
                left.remove(unit)
        rest = [_Unit((unit.type,), unit.restriction) for unit in left]
        rest += units[len(pool) :]  # the mana of the abilities under way
        matched = _match(slots, rest, outer)
        unpaid_colored = sum(unit is None for unit in matched[: len(colored)])
        unpaid = sum(unit is None for unit in matched)
        spent = [
            unit for (unit, _), amount in zip(classes, amounts, strict=True) for _ in range(amount)
        ]
        restricted = sum(unit.restriction is not None for unit in spent)
        off_color = sum(unit.type not in asked for unit in spent)
        return (unpaid_colored, unpaid, -restricted, off_color)

    return Amounts(min(found, key=score))


def _any_counts(space: ChooseCounts) -> tuple[int, ...]:
    """Some answer inside the space (the engine then refuses it if it doesn't pay)."""
    amounts: list[int] = []
    left = space.total
    for maximum in space.maxima:
        amount = min(maximum, left)
        amounts.append(amount)
        left -= amount
    return tuple(amounts)


def choose_color(
    view: PlayerView, player: PlayerId, source: ObjectId | None, options: Sequence[ColorOption]
) -> int | None:
    """106.1a: the index of the color to choose for ``source``'s mana while paying, or ``None``
    when no payment is under way."""
    chain = _chain(view, player)
    if chain is None or not chain[0]:
        return None
    demands, units = chain
    restriction = None
    if source is not None:
        for shown in view.battlefield:
            if shown.id == source:
                for ability in shown.abilities:
                    if ability.mana is not None and ability.mana.one_of:
                        restriction = ability.mana.restriction
                        break
    every = tuple(range(len(demands)))
    colored = [slot for slot in _slots(demands, every) if slot[1] is not None]
    generic = [slot for slot in _slots(demands, every) if slot[1] is None]
    slots = colored + generic

    def score(index: int) -> tuple[int, int]:
        unit = _Unit((ManaType(options[index].color.value),), restriction)
        matched = _match(slots, [*units, unit], demands)
        return (
            sum(unit is None for unit in matched[: len(colored)]),
            sum(unit is None for unit in matched),
        )

    return min(range(len(options)), key=score)


# --- The agent ---------------------------------------------------------------------------------


class AutoPayAgent:
    """Answers the payment decisions with the auto-payer and delegates the rest to ``inner``
    (module docstring). Stateless: an answer depends only on the view and the request."""

    def __init__(self, inner: Agent) -> None:
        self.inner = inner

    def decide(self, view: PlayerView, request: DecisionRequest) -> DecisionAnswer:
        value = self.answer(view, request)
        if value is None:
            return self.inner.decide(view, request)
        return DecisionAnswer(request.id, request.player, value)

    def answer(self, view: PlayerView, request: DecisionRequest) -> AnswerValue | None:
        """The auto-payer's answer to ``request``, or ``None`` to leave it to ``inner``."""
        player = request.for_player  # 723.5a: the resources are this player's
        space = request.space
        match request.kind, space:
            case DecisionKind.ACTIVATE_MANA_ABILITIES, ChooseOne(options=options):
                offered = [
                    option for option in options if isinstance(option, ActivateAbilityOption)
                ]
                plan = plan_payment(view, player, offered)
                chosen = PAY if plan is None or not plan.now else plan.now[0]
                return Pick(options.index(chosen))
            case DecisionKind.PAY_COSTS, ChooseCounts():
                return choose_payment(view, player, space)
            case DecisionKind.CHOOSE_COLOR, ChooseOne(options=options):
                colors = [option for option in options if isinstance(option, ColorOption)]
                if len(colors) != len(options):
                    return None
                index = choose_color(view, player, request.source, colors)
                return None if index is None else Pick(index)
            case DecisionKind.REVERSE_MANA_ABILITIES, ChooseSubset(options=options):
                return PickMany(tuple(range(len(options))))  # 733.1: reverse them all
            case _:
                return None
