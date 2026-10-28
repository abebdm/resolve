"""Casting spells (601.2, design.md §17.3) and reversing illegal casts (733, design.md §5).

``CastSpell(player, card, variant, permission)`` casts the card ``card`` as ``variant`` under
``permission``, which priority offered (``defaults.cast_options``). It runs 601.2's steps as
stages and never gives priority itself; its caller does (601.2i, 117.3c):

| Stage      | Rule            | Does                                                          |
|------------|-----------------|---------------------------------------------------------------|
| ``PROPOSE``| 601.2a          | takes a checkpoint (733); ``SpellProposed``: the card moves to |
|            |                 | the top of the stack as a new object, with its record          |
| ``MODES``  | 601.2b, 700.2   | a modal spell's modes (``CHOOSE_MODES``, then ``ModesChosen``)  |
| ``X``      | 601.2b, 107.3a  | the value of X (``CHOOSE_X``, then ``XAnnounced``); hybrid and  |
|            |                 | Phyrexian announcements are a gap (M9)                          |
| ``TARGETS``| 601.2c          | targets (``CHOOSE_TARGETS``, then ``BecameTargets``); division  |
|            |                 | is a gap (601.2d, M4)                                           |
| ``CHECK``  | 601.2e, 601.6   | ``legality.allowed`` again for the proposed spell               |
| ``TOTAL``  | 601.2f          | the total cost: the mana cost with X's value, plus increases,   |
|            |                 | minus reductions (``costs.spell_total_cost``); locked in        |
| ``PAY``    | 601.2g-h        | ``PayCosts``: mana abilities, then the payment                 |
| ``CAST``   | 601.2i          | ``SpellCast``; passing in succession starts over (117.4)        |
| ``REVERSE``| 733.1           | the cast is illegal: reverse it                                 |

Other variants than ``NORMAL`` and casting a commander from the command zone are gaps, raised
before anything moves: 709.3 (split halves), 702.102 (fuse), 712.11a-b (back faces), 715.3
(adventures), 720.3 (Omens), 718.3 (prototype), 722.3 (prepare spells), 708.4 (face down) and
903.8 (the commander tax, M7).

**Modes (601.2b, 700.2).** A modal spell's controller chooses its modes: ``CHOOSE_MODES``, a
``ChooseOne`` of ``ModesOption`` values, every choice its ``ModeChoice`` allows among the modes
that may be chosen (``targeting.mode_choices``; 700.2a: a mode needing targets it can't have
can't be), each choice once, its modes in printed order with a repeated mode listed that many
times (700.2d). With one possible choice nothing is asked. The choice is announced
(``ModesChosen``, public) and can't change (700.2f). With no possible choice the cast is illegal
and reversed (priority doesn't offer such a spell, ``defaults.cast_options``).

**X (601.2b, 107.3a).** If the mana cost has {X}, the caster announces its value: ``CHOOSE_X``, a
``ChooseNumber`` from 0 (107.1b) with no upper bound; a value too large to pay is found out by
paying, and the cast reversed (733.1). It is announced (``XAnnounced``, public), and the total
cost (601.2f) has it in place of each {X} (``ManaCost.with_x``). Casting without paying the mana
cost (107.3b: X must be 0) arrives with M2.10's permissions; X defined by the text (107.3c) with
the first card that has it.

**Targets (601.2c).** For each instance of the word "target" in the spell's text (of a modal
spell, in each chosen mode in turn, 700.2c), in order, the caster chooses from the legal targets
(``targeting.legal_targets``) as many as the instance allows (``CHOOSE_TARGETS``, a
``ChooseSubset``: no object or player twice, 115.3). An instance
whose only possible answer is every legal target (one creature for "target creature") isn't
asked. Once all are chosen they become the spell's targets (``BecameTargets``, public). An
instance with fewer legal targets than it needs makes the cast illegal: it is reversed. Priority
doesn't offer such a spell (``defaults.cast_options``), so that happens only if the targets
changed meanwhile.

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

from resolve.cards.primitives.spells import SpellAbility
from resolve.cards.primitives.targets import TargetSpec
from resolve.data.mana_cost import ManaCost, SymbolKind
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import (
    AnswerValue,
    ChooseNumber,
    ChooseOne,
    ChooseSubset,
    ModesOption,
    NamedOption,
    Number,
    ObjectOption,
    Option,
    Pick,
    PickMany,
    PlayerOption,
)
from resolve.effects.characteristics import characteristics
from resolve.engine import reversal
from resolve.engine.payment import Paid, PayCosts, PaymentStep, Unpayable
from resolve.engine.reversal import activations_made
from resolve.errors import EngineError, NotImplementedRule
from resolve.events.mana import ManaSpent
from resolve.events.pipeline import ApplyEvents
from resolve.events.spells import (
    ActionReversed,
    BecameTargets,
    ModesChosen,
    SpellCast,
    SpellProposed,
    XAnnounced,
)
from resolve.rules import costs, legality, targeting
from resolve.rules.legality import Targeter
from resolve.state.checkpoint import Checkpoint, take_checkpoint
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import ForSpell, Mana
from resolve.state.spell import (
    Alternative,
    AlternativeKind,
    Back,
    CastChoices,
    CastPermission,
    CastVariant,
    FaceDown,
    Fused,
    Half,
    Normal,
    Target,
    TargetObject,
    TargetPlayer,
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


DECLINE = NamedOption("decline")
"""The option of casting nothing when an effect allows a cast during its resolution (608.2g)."""


class CastStage(Enum):
    """Where ``CastSpell`` is (601.2a-i, 733.1)."""

    PROPOSE = "propose"
    MODES = "modes"
    X = "x"
    TARGETS = "targets"
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
    - ``chosen``: the targets chosen so far, per instance of "target" (601.2c).
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
    chosen: tuple[tuple[Target, ...], ...] = ()
    total: ManaCost | None = None
    payment: PayCosts | None = None
    spent: tuple[Mana, ...] = ()

    def run(self, state: GameState) -> TaskResult:
        if state.player(self.player).left_game:
            return Done()  # 800.4a: the spell left with its caster
        match self.stage:
            case CastStage.PROPOSE:
                return self._propose(state)
            case CastStage.MODES:
                return self._modes(state)
            case CastStage.X:
                return self._x(state)
            case CastStage.TARGETS:
                return self._targets(state)
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
        self.stage = CastStage.MODES
        proposed = SpellProposed(
            player=self.player,
            card=self.card,
            variant=self.variant,
            permission=self.permission,
            rules=("601.2a",),
        )
        return Push((ApplyEvents((proposed,)), self))

    def _modes(self, state: GameState) -> TaskResult:
        if self.spell is None:
            self.spell = state.stack[-1]  # 601.2a: the topmost object
            obj = state.objects[self.spell]
            if obj.spell is None or obj.controller != self.player:
                raise EngineError(
                    f"object {self.spell} isn't the spell player {self.player} proposed"
                )
        chars = characteristics(state, self.spell)
        ability = chars.spell_ability
        self.stage = CastStage.X
        if ability is None or ability.choose is None:
            return self.run(state)
        # 601.2b, 700.2a: the choices of modes that may be made now.
        targeter = Targeter(self.player, self.spell, chars)
        choices = targeting.mode_choices(state, targeter, ability)
        if not choices:
            self.stage = CastStage.REVERSE  # 601.2b can't be done: the cast is illegal
            return self.run(state)
        if len(choices) == 1:
            return self._announce_modes(choices[0])  # the only possible choice isn't asked
        self.stage = CastStage.MODES
        return NeedDecision(
            player=self.player,
            kind=DecisionKind.CHOOSE_MODES,
            space=ChooseOne(tuple(ModesOption(chosen) for chosen in choices)),
            prompt=f"Choose the modes of {chars.name}: {ability.choose.text(len(ability.modes))}",
            rules=("601.2b", "700.2", "700.2a", "700.2d"),
            source=self.spell,
        )

    def _announce_modes(self, modes: tuple[int, ...]) -> TaskResult:
        assert self.spell is not None
        self.stage = CastStage.X
        chosen = ModesChosen(spell=self.spell, modes=modes, rules=("601.2b", "700.2"))
        return Push((ApplyEvents((chosen,)), self))

    def _x(self, state: GameState) -> TaskResult:
        assert self.spell is not None
        record = self._record(state)
        cost = characteristics(state, self.spell).mana_cost
        if cost is not None and cost.has_x and record.x is None:
            # 601.2b, 107.3a: the caster announces the value of X; any number from 0 (107.1b).
            return NeedDecision(
                player=self.player,
                kind=DecisionKind.CHOOSE_X,
                space=ChooseNumber(0, None),
                prompt=f"Choose the value of X for {characteristics(state, self.spell).name}.",
                rules=("601.2b", "107.3a"),
                source=self.spell,
            )
        if cost is not None and {symbol.kind for symbol in cost.symbols} & set(_ANNOUNCED):
            raise NotImplementedRule(
                "601.2b: announcing how hybrid and Phyrexian mana symbols will be paid (M9)"
            )
        self.stage = CastStage.TARGETS
        return self.run(state)

    def _targets(self, state: GameState) -> TaskResult:
        assert self.spell is not None
        # 601.2d: division (M4).
        chars = characteristics(state, self.spell)
        specs = _target_specs(chars.spell_ability, self._record(state).modes)
        targeter = Targeter(self.player, self.spell, chars)
        while len(self.chosen) < len(specs):
            # 601.2c: the targets of the next instance of "target", in the order of the text.
            spec = specs[len(self.chosen)]
            legal = targeting.legal_targets(state, targeter, spec)
            if len(legal) < spec.minimum:
                self.stage = CastStage.REVERSE  # 601.2c can't be done: the cast is illegal
                return self.run(state)
            most = min(spec.maximum, len(legal))
            if spec.minimum == most == len(legal):
                self.chosen += (legal,)  # the only possible choice isn't asked
                continue
            return NeedDecision(
                player=self.player,
                kind=DecisionKind.CHOOSE_TARGETS,
                space=ChooseSubset(tuple(_option(t) for t in legal), spec.minimum, most),
                prompt=f"Choose {spec.text} for {chars.name}.",
                rules=("601.2c", "115.1"),
                source=self.spell,
            )
        self.stage = CastStage.CHECK
        if not specs:
            return self.run(state)
        became = BecameTargets(spell=self.spell, targets=self.chosen, rules=("601.2c", "115.1"))
        return Push((ApplyEvents((became,)), self))

    def _record(self, state: GameState) -> CastChoices:
        assert self.spell is not None
        record = state.objects[self.spell].spell
        if record is None:
            raise EngineError(f"object {self.spell} is no longer a spell being cast")
        return record

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
        # 601.2f: the total cost is the mana cost, with the announced value in place of each
        # {X} (107.3a), plus increases, minus reductions; then it is locked in (601.8).
        cost = characteristics(state, self.spell).mana_cost
        if cost is None:
            # 118.6: an object with no mana cost can't be cast by paying it.
            self.stage = CastStage.REVERSE
            return self.run(state)
        x = self._record(state).x
        if cost.has_x:
            if x is None:
                raise EngineError(f"spell {self.spell} has {{X}} but no value announced")
            cost = cost.with_x(x)
        cost = costs.spell_total_cost(state, self.spell, self.player, cost)
        self.total = cost
        self.payment = PayCosts(self.player, cost, ForSpell(self.spell))
        self.stage = CastStage.PAY
        return self.run(state)

    def payment_under_way(self) -> PayCosts | None:
        """601.2g-h: the spell's total cost, while it is being paid."""
        return self.payment if self.stage is CastStage.PAY else None

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
            case CastStage.MODES:
                if not isinstance(request.space, ChooseOne) or not isinstance(answer, Pick):
                    raise EngineError(f"CastSpell can't resume with {answer!r}")
                option = request.space.chosen(answer)
                if not isinstance(option, ModesOption):
                    raise EngineError(f"{option!r} isn't a choice of modes")
                return self._announce_modes(option.modes)
            case CastStage.X:
                if not isinstance(answer, Number):
                    raise EngineError(f"CastSpell can't resume with {answer!r}")
                assert self.spell is not None
                announced = XAnnounced(spell=self.spell, x=answer.value, rules=("601.2b", "107.3a"))
                return Push((ApplyEvents((announced,)), self))
            case CastStage.TARGETS:
                if not isinstance(request.space, ChooseSubset) or not isinstance(answer, PickMany):
                    raise EngineError(f"CastSpell can't resume with {answer!r}")
                chosen = tuple(_target(option) for option in request.space.chosen(answer))
                self.chosen += (chosen,)
                return self.run(state)
            case CastStage.PAY:
                return self._paying(state, self._payment().resume(state, request, answer))
            case CastStage.REVERSE:
                if not isinstance(answer, PickMany):
                    raise EngineError(f"CastSpell can't resume with {answer!r}")
                return self._reverse(state, _kept(len(activations_made(self.payment)), answer))
            case _:
                raise EngineError(f"CastSpell asked nothing in its {self.stage.value} stage")


def _target_specs(ability: SpellAbility | None, modes: tuple[int, ...]) -> tuple[TargetSpec, ...]:
    """The spell's instances of the word "target", in the order of its text (601.2c): of a modal
    spell, those of the chosen ``modes`` only, each mode's in turn (700.2c, 700.2d)."""
    if ability is None:
        return ()
    return ability.instances(modes)


def _option(target: Target) -> ObjectOption | PlayerOption:
    match target:
        case TargetObject(object=obj):
            return ObjectOption(obj)
        case TargetPlayer(player=player):
            return PlayerOption(player)


def _target(option: Option) -> Target:
    match option:
        case ObjectOption(object=obj):
            return TargetObject(obj)
        case PlayerOption(player=player):
            return TargetPlayer(player)
        case _:
            raise EngineError(f"{option!r} isn't a target")


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


@dataclass(slots=True)
class CastDuringResolution(Task):
    """608.2g: ``player`` may cast a spell under ``permission`` while a spell resolves (stub)."""

    player: PlayerId
    permission: CastPermission

    def run(self, state: GameState) -> TaskResult:
        raise NotImplementedRule("608.2g: casting a spell during a resolution (stub)")
