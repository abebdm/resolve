"""Casting spells (601.2, design.md §17.3) and reversing illegal casts (733, design.md §5).

``CastSpell(player, card, variant, permission)`` casts the card ``card`` as ``variant`` under
``permission``, which priority offered (``defaults.cast_options``). It runs 601.2's steps as
stages and never gives priority itself; its caller does (601.2i, 117.3c):

| Stage      | Rule            | Does                                                          |
|------------|-----------------|---------------------------------------------------------------|
| ``PROPOSE``| 601.2a          | takes a checkpoint (733); ``SpellProposed``: the card moves to |
|            |                 | the top of the stack as a new object, with its record          |
| ``ANNOUNCE``| 601.2b-d       | modes, X, hybrid and Phyrexian symbols, targets and division:  |
|            |                 | none exist yet (M2.6, M2.7, M4, M9), so each is a gap           |
| ``CHECK``  | 601.2e, 601.6   | ``legality.allowed`` again for the proposed spell               |
| ``TOTAL``  | 601.2f          | the total cost: the mana cost (cost modifiers: M2.9, M7)        |
| ``PAY``    | 601.2g-h        | ``PayCosts``: mana abilities, then the payment                 |
| ``CAST``   | 601.2i          | ``SpellCast``; passing in succession starts over (117.4)        |
| ``REVERSE``| 733.1           | the cast is illegal: reverse it                                 |

Other variants than ``NORMAL`` and casting a commander from the command zone are gaps, raised
before anything moves: 709.3 (split halves), 702.102 (fuse), 712.11a-b (back faces), 715.3
(adventures), 720.3 (Omens), 718.3 (prototype), 722.3 (prepare spells), 708.4 (face down) and
903.8 (the commander tax, M7).

**Reversal (733.1).** If the spell can't be cast (601.2e) or its cost can't be paid (601.2h,
118.3), the player chooses which of the mana abilities they activated while paying to reverse
(``REVERSE_MANA_ABILITIES``, a ``ChooseSubset``; not asked when none were activated). The
checkpoint is restored: the card is back where it was with its old ID, tapped lands untap, pools
are as before. The kept mana abilities aren't undone: their recorded events are made again
exactly as they happened (``Event.redo``), in order, without activating them again and without
logging them twice, so their results stand (a "for each card in your hand" ability keeps what it
added, although the spell is back in hand). Then a public
``ActionReversed`` records that every player saw the card (400.2). The player keeps priority
(733.2), and passes made before the attempt still count: the priority task clears them only once
a spell is cast. The activations listed include those made while paying for a mana ability's
mana cost (Selesnya Signet, 605.3a), and 733.1's dependency rule is checked: an ability whose
mana paid for a kept mana ability must be kept too (``resolve.engine.reversal``).

A caster who leaves the game during the cast (a concession, 104.3a) takes their spell with them
(800.4a): the cast just ends.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from resolve.data.mana_cost import ManaCost, SymbolKind
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import AnswerValue, ChooseSubset, PickMany
from resolve.effects.characteristics import characteristics
from resolve.engine import reversal
from resolve.engine.payment import Paid, PayCosts, PaymentStep, Unpayable
from resolve.engine.reversal import activations_made
from resolve.errors import EngineError, NotImplementedRule
from resolve.events.mana import ManaSpent
from resolve.events.pipeline import ApplyEvents
from resolve.events.spells import ActionReversed, SpellCast, SpellProposed
from resolve.rules import legality
from resolve.state.checkpoint import Checkpoint, take_checkpoint
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import ForSpell, Mana
from resolve.state.spell import (
    Alternative,
    AlternativeKind,
    Back,
    CastPermission,
    CastVariant,
    FaceDown,
    Fused,
    Half,
    Normal,
)
from resolve.tasks import Done, NeedDecision, Push, Task, TaskResult

if TYPE_CHECKING:
    from resolve.decisions.request import DecisionRequest
    from resolve.state.game import GameState

# 601.2b: symbols whose payment is announced as the spell is proposed (M9).
_ANNOUNCED = (
    SymbolKind.HYBRID,
    SymbolKind.MONOCOLORED_HYBRID,
    SymbolKind.COLORLESS_HYBRID,
    SymbolKind.PHYREXIAN,
    SymbolKind.HYBRID_PHYREXIAN,
)


class CastStage(Enum):
    """Where ``CastSpell`` is (601.2a-i, 733.1)."""

    PROPOSE = "propose"
    ANNOUNCE = "announce"
    CHECK = "check"
    TOTAL = "total"
    PAY = "pay"
    CAST = "cast"
    REVERSE = "reverse"


@dataclass(slots=True)
class CastSpell(Task):
    """``player`` casts ``card`` as ``variant`` under ``permission`` (601.2).

    - ``spell``: the spell's object on the stack, once proposed (601.2a).
    - ``checkpoint``: the game as it was before the proposal (733.1).
    - ``total``: the locked-in mana part of the total cost (601.2f).
    - ``payment``: the payment in progress (601.2g-h).
    - ``spent``: the mana spent (601.2h).
    """

    player: PlayerId
    card: ObjectId
    variant: CastVariant
    permission: CastPermission
    stage: CastStage = CastStage.PROPOSE
    spell: ObjectId | None = None
    checkpoint: Checkpoint | None = None
    total: ManaCost | None = None
    payment: PayCosts | None = None
    spent: tuple[Mana, ...] = ()

    def run(self, state: GameState) -> TaskResult:
        if state.player(self.player).left_game:
            return Done()  # 800.4a: the spell left with its caster
        match self.stage:
            case CastStage.PROPOSE:
                return self._propose(state)
            case CastStage.ANNOUNCE:
                return self._announce(state)
            case CastStage.CHECK:
                return self._check(state)
            case CastStage.TOTAL:
                return self._total(state)
            case CastStage.PAY:
                return self._paying(state, self._payment().step(state))
            case CastStage.CAST:
                return self._cast(state)
            case CastStage.REVERSE:
                return self._ask_reverse(state)

    # --- 601.2a-e -------------------------------------------------------------------------------

    def _propose(self, state: GameState) -> TaskResult:
        _variant_gap(state, self.card, self.variant)
        if self.permission.rule == "903.8":
            raise NotImplementedRule(
                "903.8: casting a commander from the command zone (the commander tax, M7)"
            )
        action = legality.CastAction(self.player, self.card, self.variant, self.permission)
        if not legality.allowed(state, action).allowed:
            raise EngineError(f"player {self.player} may not begin to cast object {self.card}")
        # 733.1: the game as it was before the proposal, to return to if the cast is illegal.
        self.checkpoint = take_checkpoint(state)
        self.stage = CastStage.ANNOUNCE
        proposed = SpellProposed(
            player=self.player,
            card=self.card,
            variant=self.variant,
            permission=self.permission,
            rules=("601.2a",),
        )
        return Push((ApplyEvents((proposed,)), self))

    def _announce(self, state: GameState) -> TaskResult:
        if self.spell is None:
            self.spell = state.stack[-1]  # 601.2a: the topmost object
            obj = state.objects[self.spell]
            if obj.spell is None or obj.controller != self.player:
                raise EngineError(
                    f"object {self.spell} isn't the spell player {self.player} proposed"
                )
        cost = characteristics(state, self.spell).mana_cost
        if cost is not None:
            kinds = {symbol.kind for symbol in cost.symbols}
            if SymbolKind.VARIABLE in kinds:
                raise NotImplementedRule("601.2b: announcing the value of X (M2.7)")
            if kinds & set(_ANNOUNCED):
                raise NotImplementedRule(
                    "601.2b: announcing how hybrid and Phyrexian mana symbols will be paid (M9)"
                )
        # 601.2b-d: modes, targets and division come with spell abilities (M2.6, M2.7, M4).
        self.stage = CastStage.CHECK
        return self.run(state)

    def _check(self, state: GameState) -> TaskResult:
        # 601.2e, 601.6: the proposed spell must still be legal to cast.
        assert self.spell is not None
        action = legality.CastAction(self.player, self.spell, self.variant, self.permission)
        self.stage = (
            CastStage.TOTAL if legality.allowed(state, action).allowed else CastStage.REVERSE
        )
        return self.run(state)

    # --- 601.2f-i -------------------------------------------------------------------------------

    def _total(self, state: GameState) -> TaskResult:
        assert self.spell is not None
        # 601.2f: the total cost is the mana cost (cost increases and reductions: M2.9, M7).
        cost = characteristics(state, self.spell).mana_cost
        if cost is None:
            # 118.6: an object with no mana cost can't be cast by paying it.
            self.stage = CastStage.REVERSE
            return self.run(state)
        self.total = cost
        self.payment = PayCosts(self.player, cost, ForSpell(self.spell))
        self.stage = CastStage.PAY
        return self.run(state)

    def _payment(self) -> PayCosts:
        if self.payment is None:
            raise EngineError("CastSpell is paying without a payment")
        return self.payment

    def _paying(self, state: GameState, step: PaymentStep) -> TaskResult:
        match step:
            case NeedDecision():
                return step
            case Push(tasks=tasks):
                return Push((*tasks, self))
            case Paid(mana=mana):
                self.spent = mana
                self.stage = CastStage.CAST
                if not mana:
                    return self.run(state)
                spent = ManaSpent(
                    player=self.player, mana=mana, rules=("601.2h", "118.3a", "106.4a")
                )
                return Push((ApplyEvents((spent,)), self))
            case Unpayable():
                self.stage = CastStage.REVERSE
                return self.run(state)

    def _cast(self, state: GameState) -> TaskResult:
        assert self.spell is not None and self.total is not None
        # 117.4: casting a spell is an action; passing in succession starts over (only now, so a
        # reversed attempt leaves earlier passes standing, 733.2).
        if state.turn is not None:
            state.turn.passed.clear()
        cast = SpellCast(
            player=self.player,
            spell=self.spell,
            total_cost=self.total,
            mana_spent=self.spent,
            rules=("601.2i",),
        )
        return Push((ApplyEvents((cast,)),))

    # --- 733.1 ----------------------------------------------------------------------------------

    def _ask_reverse(self, state: GameState) -> TaskResult:
        made = activations_made(self.payment)
        if not made:
            return self._reverse(state, ())
        return NeedDecision(
            player=self.player,
            kind=DecisionKind.REVERSE_MANA_ABILITIES,
            space=ChooseSubset(reversal.options(made), 0, len(made)),
            prompt="The spell can't be cast. Choose the mana abilities to reverse.",
            rules=("733.1",),
            source=self.spell,
        )

    def _reverse(self, state: GameState, kept: tuple[int, ...]) -> TaskResult:
        if self.checkpoint is None:
            raise EngineError("CastSpell is reversing without a checkpoint")
        made = activations_made(self.payment)
        # 733.1: the mana abilities the player doesn't reverse aren't undone: their results stand
        # exactly as they happened (they aren't activated again).
        reversal.reverse_to(state, self.checkpoint, made, kept)
        reversed_ = ActionReversed(
            player=self.player,
            card=self.card,
            kept=tuple(made[number].source for number in kept),
            rules=("733.1", "733.2"),
        )
        return Push((ApplyEvents((reversed_,)),))

    # --- Answers --------------------------------------------------------------------------------

    def check_answer(self, state: GameState, request: DecisionRequest, answer: AnswerValue) -> None:
        match self.stage:
            case CastStage.PAY:
                self._payment().check_answer(state, answer)
            case CastStage.REVERSE:
                if self.checkpoint is not None and isinstance(answer, PickMany):
                    made = activations_made(self.payment)
                    reversal.check_kept(
                        state, self.checkpoint, self.player, made, _kept(len(made), answer)
                    )
            case _:
                pass

    def resume(self, state: GameState, request: DecisionRequest, answer: AnswerValue) -> TaskResult:
        match self.stage:
            case CastStage.PAY:
                return self._paying(state, self._payment().resume(state, request, answer))
            case CastStage.REVERSE:
                if not isinstance(answer, PickMany):
                    raise EngineError(f"CastSpell can't resume with {answer!r}")
                return self._reverse(state, _kept(len(activations_made(self.payment)), answer))
            case _:
                raise EngineError(f"CastSpell asked nothing in its {self.stage.value} stage")


def _kept(count: int, answer: PickMany) -> tuple[int, ...]:
    """The positions not chosen for reversal (733.1: the answer names those to reverse)."""
    undone = set(answer.indices)
    return tuple(number for number in range(count) if number not in undone)


def _variant_gap(state: GameState, card: ObjectId, variant: CastVariant) -> None:
    """Raise the gap of a way of casting the engine can't do yet (601.3e)."""
    match variant:
        case Normal():
            return
        case Half():
            raise NotImplementedRule("709.3: casting one half of a split card")
        case Fused():
            raise NotImplementedRule("702.102: casting a fused split spell")
        case Back():
            layout = state.card_of(state.object(card)).data.layout
            if layout == "modal_dfc":
                raise NotImplementedRule("712.11b: casting a modal double-faced card's back face")
            raise NotImplementedRule("712.11a: casting a double-faced card transformed")
        case Alternative(kind=kind):
            match kind:
                case AlternativeKind.ADVENTURE:
                    raise NotImplementedRule("715.3: casting an adventurer card as an Adventure")
                case AlternativeKind.OMEN:
                    raise NotImplementedRule("720.3: casting an omen card as an Omen")
                case AlternativeKind.PROTOTYPE:
                    raise NotImplementedRule("718.3: casting a prototype card prototyped")
                case AlternativeKind.PREPARE:
                    raise NotImplementedRule(
                        "722.3: casting a prepare spell (only its copies are cast)"
                    )
        case FaceDown():
            raise NotImplementedRule("708.4: casting a card face down")
