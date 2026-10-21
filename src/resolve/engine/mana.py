"""Activating mana abilities (605, 602.2b, 733.1) and emptying mana pools (500.5)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from resolve.cards.primitives.abilities import ActivatedManaAbility
from resolve.cards.primitives.costs import ManaPaymentCost
from resolve.cards.primitives.effects import AddMana
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import (
    AnswerValue,
    ChooseOne,
    ChooseSubset,
    ColorOption,
    Pick,
    PickMany,
)
from resolve.effects.characteristics import characteristics
from resolve.engine import reversal
from resolve.engine.payment import AbilityKey, Paid, PayCosts, PaymentStep, Unpayable
from resolve.engine.reversal import activations_made
from resolve.errors import EngineError
from resolve.events.mana import ManaPoolEmptied, ManaSpent
from resolve.events.pipeline import ApplyEvents
from resolve.events.spells import ActionReversed
from resolve.rules import defaults
from resolve.state.checkpoint import Checkpoint, take_checkpoint
from resolve.state.game import apnap_order
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import ForAbility
from resolve.tasks import Done, NeedDecision, Push, Task, TaskResult

if TYPE_CHECKING:
    from resolve.decisions.request import DecisionRequest
    from resolve.events.base import Event
    from resolve.state.game import GameState


class ActivationStage(Enum):
    """Where ``ActivateManaAbility`` is (602.2b, 605.3b, 733.1)."""

    BEGIN = "begin"
    PAY = "pay"
    RESOLVE = "resolve"
    CHOOSE_COLOR = "choose color"
    FINISH = "finish"
    REVERSE = "reverse"


@dataclass(slots=True)
class ActivateManaAbility(Task):
    """``player`` activates ability ``index`` of ``source``, a mana ability (605.3a).

    The costs are paid (602.2b, 601.2g-h), then the ability resolves at once without using the
    stack (605.3b). Stages:

    - ``BEGIN``: 602.5 and 605.3c checked; the ability is kept (it resolves even if its source
      changes meanwhile, 113.7a). Without a mana cost its costs are paid at once.
    - ``PAY``: a mana cost (Selesnya Signet's {1}) is paid through an embedded ``PayCosts``, during
      which other mana abilities may be activated (605.3a), but not this one or those whose costs
      this one is paying for (``excluding``, 605.3c). A checkpoint is taken first: if the payment
      turns out impossible (118.3), the activation is reversed (``REVERSE``, 733.1). Once paid,
      the other costs ({T}) are paid with it.
    - ``RESOLVE`` and ``CHOOSE_COLOR``: the effect adds its mana; "one mana of any color" asks
      for the color when there are two or more (106.1a), and adds nothing with none (106.5).
    - ``FINISH``: the activation is over (``log_to``). A completed activation is an action:
      passing in succession starts over (117.4). A reversed one isn't (733.2).

    ``log_from`` and ``log_to`` delimit its log entries, so a reversal of the action it was part of
    can keep its results as they happened (``resolve.engine.reversal``); ``payment`` holds the
    activations made while paying for it; ``reversed`` says it was reversed.
    """

    player: PlayerId
    source: ObjectId
    index: int
    excluding: tuple[AbilityKey, ...] = ()
    stage: ActivationStage = ActivationStage.BEGIN
    ability: ActivatedManaAbility | None = None
    log_from: int | None = None
    log_to: int | None = None
    checkpoint: Checkpoint | None = None
    payment: PayCosts | None = None
    reversed: bool = False

    def run(self, state: GameState) -> TaskResult:
        if state.player(self.player).left_game:
            return Done()  # 800.4a: a player who left takes no actions
        match self.stage:
            case ActivationStage.BEGIN:
                return self._begin(state)
            case ActivationStage.PAY:
                return self._paying(state, self._payment().step(state))
            case ActivationStage.RESOLVE:
                return self._resolve(state)
            case ActivationStage.CHOOSE_COLOR:
                raise EngineError("ActivateManaAbility is waiting for a color")
            case ActivationStage.FINISH:
                self.log_to = len(state.event_log)
                if not self.reversed and state.turn is not None:
                    state.turn.passed.clear()  # 117.4: an action
                return Done()
            case ActivationStage.REVERSE:
                return self._ask_reverse(state)

    def _begin(self, state: GameState) -> TaskResult:
        ability = characteristics(state, self.source).abilities[self.index]
        if not isinstance(ability, ActivatedManaAbility):
            raise EngineError(f"ability {self.index} of object {self.source} isn't a mana ability")
        if (self.source, self.index) in self.excluding or not ability.can_activate(
            state, self.source, self.player
        ):
            raise EngineError(f"player {self.player} can't activate that ability now")
        self.ability = ability
        self.log_from = len(state.event_log)
        mana_cost = ability.mana_cost
        if mana_cost is None:
            self.stage = ActivationStage.RESOLVE
            return self._pay_other_costs(state, ())
        # 733.1: the game as it was, to return to if the mana cost can't be paid.
        self.checkpoint = take_checkpoint(state)
        self.payment = PayCosts(
            self.player,
            mana_cost.mana,
            ForAbility(self.source, self.index),
            (*self.excluding, (self.source, self.index)),
        )
        self.stage = ActivationStage.PAY
        return self.run(state)

    def _ability(self) -> ActivatedManaAbility:
        if self.ability is None:
            raise EngineError("ActivateManaAbility hasn't begun")
        return self.ability

    def _payment(self) -> PayCosts:
        if self.payment is None:
            raise EngineError("ActivateManaAbility is paying without a payment")
        return self.payment

    def _pay_other_costs(self, state: GameState, mana: tuple[Event, ...]) -> TaskResult:
        """Pay the costs other than mana (602.2b), with the mana spending ``mana``, if any."""
        payment = list(mana)
        for cost in self._ability().cost:
            if not isinstance(cost, ManaPaymentCost):
                payment += cost.payment(state, self.source, self.player)
        return Push((ApplyEvents(tuple(payment)), self)) if payment else self.run(state)

    def _paying(self, state: GameState, step: PaymentStep) -> TaskResult:
        match step:
            case NeedDecision():
                return step
            case Push(tasks=tasks):
                return Push((*tasks, self))
            case Paid(mana=mana):
                others = [c for c in self._ability().cost if not isinstance(c, ManaPaymentCost)]
                if not all(cost.can_pay(state, self.source, self.player) for cost in others):
                    self.stage = ActivationStage.REVERSE  # 118.3: e.g. its {T} can't be paid now
                    return self.run(state)
                self.stage = ActivationStage.RESOLVE
                spent = ManaSpent(
                    player=self.player, mana=mana, rules=("601.2h", "602.2b", "118.3a", "106.4a")
                )
                return self._pay_other_costs(state, (spent,) if mana else ())
            case Unpayable():
                self.stage = ActivationStage.REVERSE
                return self.run(state)

    def _resolve(self, state: GameState) -> TaskResult:
        # 605.3b: it resolves at once.
        effect = self._ability().effect
        self.stage = ActivationStage.FINISH
        if isinstance(effect, AddMana):
            return self._add(effect.events(state, self.source, self.player))
        colors = effect.colors(state, self.source, self.player)
        if len(colors) > 1:
            self.stage = ActivationStage.CHOOSE_COLOR
            return NeedDecision(
                player=self.player,
                kind=DecisionKind.CHOOSE_COLOR,
                space=ChooseOne(tuple(ColorOption(color) for color in colors)),
                prompt="Choose the color of the mana.",
                rules=("106.1a", "605.3b"),
                source=self.source,
            )
        # 106.5: with no color to choose, it adds no mana.
        return self._add(
            effect.events(state, self.source, self.player, colors[0] if colors else None)
        )

    def _add(self, events: tuple[Event, ...]) -> TaskResult:
        return Push((ApplyEvents(events), self)) if events else Push((self,))

    # --- 733.1 ----------------------------------------------------------------------------------

    def _ask_reverse(self, state: GameState) -> TaskResult:
        made = activations_made(self.payment)
        if not made:
            return self._reverse(state, ())
        return NeedDecision(
            player=self.player,
            kind=DecisionKind.REVERSE_MANA_ABILITIES,
            space=ChooseSubset(reversal.options(made), 0, len(made)),
            prompt="The ability's cost can't be paid. Choose the mana abilities to reverse.",
            rules=("733.1",),
            source=self.source,
        )

    def _reverse(self, state: GameState, kept: tuple[int, ...]) -> TaskResult:
        if self.checkpoint is None:
            raise EngineError("ActivateManaAbility is reversing without a checkpoint")
        made = activations_made(self.payment)
        reversal.reverse_to(state, self.checkpoint, made, kept)
        self.reversed = True
        self.stage = ActivationStage.FINISH
        reversed_ = ActionReversed(
            player=self.player,
            source=self.source,
            kept=tuple(made[number].source for number in kept),
            rules=("733.1", "733.2"),
        )
        return Push((ApplyEvents((reversed_,)), self))

    # --- Answers --------------------------------------------------------------------------------

    def check_answer(self, state: GameState, request: DecisionRequest, answer: AnswerValue) -> None:
        match self.stage:
            case ActivationStage.PAY:
                self._payment().check_answer(state, answer)
            case ActivationStage.REVERSE:
                if self.checkpoint is not None and isinstance(answer, PickMany):
                    made = activations_made(self.payment)
                    reversal.check_kept(
                        state, self.checkpoint, self.player, made, _kept(len(made), answer)
                    )
            case _:
                pass

    def resume(self, state: GameState, request: DecisionRequest, answer: AnswerValue) -> TaskResult:
        match self.stage:
            case ActivationStage.PAY:
                return self._paying(state, self._payment().resume(state, request, answer))
            case ActivationStage.CHOOSE_COLOR:
                if not isinstance(request.space, ChooseOne) or not isinstance(answer, Pick):
                    raise EngineError(f"ActivateManaAbility can't resume with {answer!r}")
                chosen = request.space.chosen(answer)
                if not isinstance(chosen, ColorOption):
                    raise EngineError(f"{chosen!r} isn't a color")
                effect = self._ability().effect
                if isinstance(effect, AddMana):
                    raise EngineError("this ability's mana has no color to choose")
                self.stage = ActivationStage.FINISH
                return self._add(effect.events(state, self.source, self.player, chosen.color))
            case ActivationStage.REVERSE:
                if not isinstance(answer, PickMany):
                    raise EngineError(f"ActivateManaAbility can't resume with {answer!r}")
                return self._reverse(state, _kept(len(activations_made(self.payment)), answer))
            case _:
                raise EngineError(
                    f"ActivateManaAbility asked nothing in its {self.stage.value} stage"
                )


def _kept(count: int, answer: PickMany) -> tuple[int, ...]:
    """The positions not chosen for reversal (733.1: the answer names those to reverse)."""
    undone = set(answer.indices)
    return tuple(number for number in range(count) if number not in undone)


def empty_mana_pools(state: GameState) -> tuple[Event, ...]:
    """500.5, 703.4q: every player's unspent mana that empties does so, in APNAP order
    (``defaults.mana_that_empties``: all of it); nothing for a player with none to empty."""
    events: list[Event] = []
    for player in apnap_order(state):
        emptying = defaults.mana_that_empties(state, player)
        if not emptying:
            continue
        kept = list(state.player(player).mana_pool)
        for unit in emptying:
            kept.remove(unit)
        events.append(
            ManaPoolEmptied(
                player=player, mana=emptying, kept=tuple(kept), rules=("500.5", "703.4q", "106.4")
            )
        )
    return tuple(events)


@dataclass(slots=True)
class EmptyManaPools(Task):
    """As a step or phase ends, unspent mana empties from every pool (500.5, 703.4q)."""

    def run(self, state: GameState) -> TaskResult:
        events = empty_mana_pools(state)
        return Push((ApplyEvents(events),)) if events else Done()
