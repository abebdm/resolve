"""Combat's turn-based actions (506-511; design.md §17.18).

``RunStep`` (``resolve.engine.turns``) runs them in their steps:

- **beginning of combat**: 507.1 has no choice (every multiplayer game uses the attack multiple
  players option, 802). The combat state is created as the combat phase's first step begins
  (``CombatBegan``, 506.2), before this step's turn-based actions.
- **declare attackers**: ``DeclareAttackers`` (508.1).
- **declare blockers**: ``DeclareBlockers`` (509.1, 802.4): each defending player declares
  their blockers, in APNAP order.
- **combat damage**: ``CombatDamage`` (510.1-510.2, 802.5): damage is assigned, each player
  dividing their creatures' damage among two or more recipients in APNAP order, then dealt at
  once.
- **end of combat**: none (511.1); as the step ends, ``CombatEnded`` removes everything from
  combat (511.3).

508.8 (skipping the declare blockers and combat damage steps when no creature attacked) is
``defaults.is_skipped``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from resolve.cards.keywords import Vigilance, has_keyword
from resolve.data.mana_cost import ManaCost
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import (
    AmountsEach,
    AnswerValue,
    Assignment,
    ChooseAssignment,
    ChooseSubset,
    Distribute,
    DistributeEach,
    ObjectOption,
    Option,
    PickMany,
    PlayerOption,
)
from resolve.effects.characteristics import characteristics
from resolve.engine import reversal
from resolve.engine.payment import Paid, PayCosts, PaymentStep, Unpayable
from resolve.engine.reversal import activations_made
from resolve.errors import EngineError, NotImplementedRule
from resolve.events.base import Event
from resolve.events.combat import AttackersDeclared, BlockersDeclared
from resolve.events.damage import DamageDealt
from resolve.events.mana import ManaSpent
from resolve.events.permanents import PermanentTapped
from resolve.events.pipeline import ApplyEvents
from resolve.events.spells import ActionReversed
from resolve.rules import defaults
from resolve.rules.combat import (
    attack_cost,
    attack_declaration,
    block_cost,
    block_declaration,
    damage_recipients,
    declared_attacks,
    declared_blocks,
)
from resolve.state.checkpoint import Checkpoint, take_checkpoint
from resolve.state.combat import AttackTarget, CombatState
from resolve.state.game import apnap_order
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import ForAttack, ForBlock
from resolve.state.zones import ZoneKind
from resolve.tasks import Done, NeedDecision, Push, Task, TaskResult

if TYPE_CHECKING:
    from resolve.decisions.request import DecisionRequest
    from resolve.state.game import GameState


def _combat(state: GameState) -> CombatState:
    turn = state.turn
    if turn is None or turn.combat is None:
        raise EngineError("combat's turn-based actions need a combat (506.1)")
    return turn.combat


class DeclarationStage(Enum):
    """Where a declaration of attackers or blockers is (508.1, 509.1, 733.1)."""

    DECLARE = "declare"
    PAY = "pay"
    REVERSE = "reverse"


@dataclass(slots=True)
class DeclarationCost:
    """The cost of a declaration being paid (508.1g-j, 509.1d-f), shared by ``DeclareAttackers``
    and ``DeclareBlockers``: the game before the declaration (``checkpoint``, 733.1), the
    locked-in total (``total``, 508.1h, 509.1d) and its payment (``payment``, 508.1i-j,
    509.1e-f). ``PayCosts`` asks for the mana abilities and the payment; one that can't be paid
    reverses the declaration (508.1, 509.1: "the game returns to the moment before the
    declaration"), the payer choosing which mana abilities to reverse too (733.1)."""

    payer: PlayerId
    checkpoint: Checkpoint
    total: ManaCost
    payment: PayCosts

    def reverse(self, state: GameState, kept: tuple[int, ...]) -> ActionReversed:
        """Return to the checkpoint, keeping the mana abilities at ``kept`` (733.1)."""
        made = activations_made(self.payment)
        reversal.reverse_to(state, self.checkpoint, made, kept)
        return ActionReversed(
            player=self.payer,
            kept=tuple(made[number].source for number in kept),
            declaration=True,
            rules=("508.1", "509.1", "733.1"),
        )

    def ask_reverse(self, prompt: str) -> NeedDecision | None:
        """733.1: which mana abilities activated while paying to reverse; ``None`` if none."""
        made = activations_made(self.payment)
        if not made:
            return None
        return NeedDecision(
            player=self.payer,
            kind=DecisionKind.REVERSE_MANA_ABILITIES,
            space=ChooseSubset(reversal.options(made), 0, len(made)),
            prompt=prompt,
            rules=("733.1",),
        )

    def check_answer(self, state: GameState, stage: DeclarationStage, answer: AnswerValue) -> None:
        if stage is DeclarationStage.PAY:
            self.payment.check_answer(state, answer)
        elif stage is DeclarationStage.REVERSE and isinstance(answer, PickMany):
            made = activations_made(self.payment)
            reversal.check_kept(state, self.checkpoint, self.payer, made, _kept(len(made), answer))


def _kept(count: int, answer: PickMany) -> tuple[int, ...]:
    """The positions of the activations to keep: those not chosen for reversal."""
    chosen = set(answer.indices)
    return tuple(number for number in range(count) if number not in chosen)


@dataclass(slots=True)
class DeclareAttackers(Task):
    """508.1: the attacking creatures are declared, by ``defaults.attack_declarer`` (the active
    player).

    1. 508.1a-d: a ``DECLARE_ATTACKERS`` decision, the ``ChooseAssignment`` compiled by
       ``resolve.rules.combat.attack_declaration`` (the restrictions on one creature are left
       out of it; those on the whole declaration, its requirements and its costly picks are in
       it); not asked when no creature may attack. The space validates the answer, so an
       illegal declaration is refused before anything changes (508.1, 733).
    2. 508.1e (banding) has nothing to apply yet (M9).
    3. 508.1f: the chosen creatures without vigilance tap (702.20b), at the same time; tapping
       isn't a cost. A checkpoint is taken first (733.1).
    4. 508.1g-j: if the declaration needs a cost (``rules.combat.attack_cost``: Ghostly Prison),
       the total is locked in and paid (``PayCosts``, ``ForAttack``; mana abilities may be
       activated, 508.1i). If it can't be paid, the declaration is reversed (``DeclarationCost``)
       and asked again. 508.1g's optional costs have no card yet.
    5. 508.1k: ``AttackersDeclared`` (with the cost paid) makes them attacking creatures.
       508.1m's triggers are M4's.
    """

    stage: DeclarationStage = DeclarationStage.DECLARE
    attacks: tuple[tuple[ObjectId, AttackTarget], ...] = ()
    cost: DeclarationCost | None = None

    def run(self, state: GameState) -> TaskResult:
        turn = state.turn
        if turn is None or state.player(turn.active_player).left_game:
            return Done()  # 800.4a: the attacking player left; their creatures went with them
        match self.stage:
            case DeclarationStage.DECLARE:
                space = attack_declaration(state)
                if space is None:
                    return Done()  # 508.1a: no creature can attack, so none does
                return NeedDecision(
                    player=defaults.attack_declarer(state),
                    kind=DecisionKind.DECLARE_ATTACKERS,
                    space=space,
                    prompt="Declare attackers: choose what each creature attacks, if anything.",
                    rules=("508.1", "508.1a", "508.1b", "508.1c", "508.1d"),
                )
            case DeclarationStage.PAY:
                return self._paying(state, self._cost().payment.step(state))
            case DeclarationStage.REVERSE:
                return self._ask_reverse(state)

    def _cost(self) -> DeclarationCost:
        if self.cost is None:
            raise EngineError("DeclareAttackers is paying without a cost")
        return self.cost

    def payment_under_way(self) -> PayCosts | None:
        """508.1i-j: the total cost to attack, while it is being paid."""
        if self.stage is DeclarationStage.PAY and self.cost is not None:
            return self.cost.payment
        return None

    def _declared(self, state: GameState, total: ManaCost | None) -> TaskResult:
        # 508.1k: each chosen creature still controlled by the active player attacks.
        turn = state.turn
        assert turn is not None
        attacks = tuple(
            (obj, target)
            for obj, target in self.attacks
            if obj in state.objects
            and state.objects[obj].zone.kind is ZoneKind.BATTLEFIELD
            and state.objects[obj].controller == turn.active_player
        )
        self.stage, self.attacks, self.cost = DeclarationStage.DECLARE, (), None
        if not attacks:
            return Done()
        declared = AttackersDeclared(attacks=attacks, cost=total, rules=("508.1k", "508.1b"))
        return Push((ApplyEvents((declared,)),))

    def _paying(self, state: GameState, step: PaymentStep) -> TaskResult:
        cost = self._cost()
        match step:
            case NeedDecision():
                return step
            case Push(tasks=tasks):
                return Push((*tasks, self))
            case Paid(mana=mana):
                total = cost.total
                result = self._declared(state, total)
                if not mana:
                    return result
                spent = ManaSpent(player=cost.payer, mana=mana, rules=("508.1j", "118.3a"))
                tail = result.tasks if isinstance(result, Push) else ()
                return Push((ApplyEvents((spent,)), *tail))
            case Unpayable():
                self.stage = DeclarationStage.REVERSE
                return self.run(state)

    def _ask_reverse(self, state: GameState) -> TaskResult:
        asked = self._cost().ask_reverse(
            "The attack can't be paid for. Choose the mana abilities to reverse."
        )
        return asked if asked is not None else self._reverse(state, ())

    def _reverse(self, state: GameState, kept: tuple[int, ...]) -> TaskResult:
        reversed_ = self._cost().reverse(state, kept)
        self.stage, self.attacks, self.cost = DeclarationStage.DECLARE, (), None
        return Push((ApplyEvents((reversed_,)), self))  # 508.1: declare again

    def check_answer(self, state: GameState, request: DecisionRequest, answer: AnswerValue) -> None:
        if self.cost is not None:
            self.cost.check_answer(state, self.stage, answer)

    def resume(self, state: GameState, request: DecisionRequest, answer: AnswerValue) -> TaskResult:
        match self.stage:
            case DeclarationStage.PAY:
                return self._paying(state, self._cost().payment.resume(state, request, answer))
            case DeclarationStage.REVERSE:
                if not isinstance(answer, PickMany):
                    raise EngineError(f"DeclareAttackers can't resume with {answer!r}")
                made = activations_made(self._cost().payment)
                return self._reverse(state, _kept(len(made), answer))
            case DeclarationStage.DECLARE:
                pass
        if not isinstance(request.space, ChooseAssignment) or not isinstance(answer, Assignment):
            raise EngineError(f"DeclareAttackers can't resume with {answer!r}")
        attacks = declared_attacks(request.space, answer.picks)
        if not attacks:
            return Done()  # 508.8 reads that none attacked
        turn = state.turn
        assert turn is not None
        total = attack_cost(state, attacks)
        self.attacks = attacks
        if total is not None:
            # 733.1: the game before the declaration's first change (508.1f), to return to.
            self.cost = DeclarationCost(
                turn.active_player,
                take_checkpoint(state),
                total,
                PayCosts(turn.active_player, total, ForAttack(tuple(obj for obj, _ in attacks))),
            )
            self.stage = DeclarationStage.PAY
        taps = tuple(
            PermanentTapped(obj=obj, rules=("508.1f", "701.26a"))
            for obj, _ in attacks
            if not has_keyword(characteristics(state, obj), Vigilance)  # 702.20b
        )
        if total is None:
            declared = self._declared(state, None)
            tail = declared.tasks if isinstance(declared, Push) else ()
            return Push((ApplyEvents(taps), *tail)) if taps else declared
        # 508.1f, then 508.1g-j: the creatures tap before the total cost is paid.
        return Push((ApplyEvents(taps), self)) if taps else self.run(state)


@dataclass(slots=True)
class DeclareBlockers(Task):
    """509.1, 802.4: each defending player, in APNAP order, declares their blockers.

    For each defending player still in the game (in ``CombatState.defending_players``' order,
    which is APNAP order, 506.2), from ``next`` on:

    1. 509.1a-c: a ``DECLARE_BLOCKERS`` decision for ``defaults.block_declarer``, the
       ``ChooseAssignment`` compiled by ``resolve.rules.combat.block_declaration`` (with the
       restrictions on the whole declaration, its requirements and its costly picks); not asked
       when none of their creatures may block (one possible declaration, none). The space
       validates the answer, so an illegal declaration is refused before anything changes
       (509.1, 733).
    2. 509.1d-f: if the blocks need a cost (``rules.combat.block_cost``: Test Tollkeeper), the
       total is locked in and paid by that player (``PayCosts``, ``ForBlock``); one that can't
       be paid reverses the declaration (``DeclarationCost``), and the player declares again.
    3. 509.1g-h: ``BlockersDeclared(defending_player=...)`` makes their blockers and fixes the
       blocked status of the creatures attacking them, before the next player declares (802.4:
       "the first defending player declares all their blocks, then the second").

    Then a ``BlockersDeclared`` without a player makes every attacker still undecided unblocked
    (those attacking a player who wasn't asked, or who left, 800.4a), if any. 509.2a's triggers
    are M4's.

    The task records which player is next in ``next``, so after a concession (104.3a) it runs
    again from the player being asked, and the declarations already made stay made.
    """

    next: int = 0
    stage: DeclarationStage = DeclarationStage.DECLARE
    blocks: tuple[tuple[ObjectId, tuple[ObjectId, ...]], ...] = ()
    cost: DeclarationCost | None = None

    def run(self, state: GameState) -> TaskResult:
        combat = _combat(state)
        players = combat.defending_players
        if self.stage is not DeclarationStage.DECLARE:
            if state.player(players[self.next]).left_game:
                # 800.4a: the paying player left; their declaration goes with them.
                self.stage, self.blocks, self.cost = DeclarationStage.DECLARE, (), None
                self.next += 1
            elif self.stage is DeclarationStage.PAY:
                return self._paying(state, self._cost().payment.step(state))
            else:
                asked = self._cost().ask_reverse(
                    "The blocks can't be paid for. Choose the mana abilities to reverse."
                )
                return asked if asked is not None else self._reverse(state, ())
        while self.next < len(players):
            player = players[self.next]
            if not state.player(player).left_game:
                space = block_declaration(state, player)
                if space is not None:
                    return NeedDecision(
                        player=defaults.block_declarer(state, player),
                        kind=DecisionKind.DECLARE_BLOCKERS,
                        space=space,
                        prompt=(
                            f"Declare player {player}'s blockers: choose which attackers each "
                            "creature blocks, if any."
                        ),
                        rules=("509.1", "509.1a", "509.1b", "509.1c", "802.4"),
                    )
            self.next += 1
        if not any(record.blocked is None for record in combat.attackers.values()):
            return Done()
        declared = BlockersDeclared(rules=("509.1h", "509.1g"))
        return Push((ApplyEvents((declared,)),))

    def _cost(self) -> DeclarationCost:
        if self.cost is None:
            raise EngineError("DeclareBlockers is paying without a cost")
        return self.cost

    def payment_under_way(self) -> PayCosts | None:
        """509.1e-f: the total cost to block, while it is being paid."""
        if self.stage is DeclarationStage.PAY and self.cost is not None:
            return self.cost.payment
        return None

    def _declared(self, state: GameState, total: ManaCost | None) -> list[Task]:
        player = _combat(state).defending_players[self.next]
        # 509.1g: each chosen creature still controlled by the defending player blocks.
        blocks = tuple(
            (blocker, attackers)
            for blocker, attackers in self.blocks
            if blocker in state.objects
            and state.objects[blocker].zone.kind is ZoneKind.BATTLEFIELD
            and state.objects[blocker].controller == player
        )
        declared = BlockersDeclared(
            blocks=blocks,
            defending_player=player,
            cost=total,
            rules=("509.1g", "509.1h", "802.4"),
        )
        self.stage, self.blocks, self.cost = DeclarationStage.DECLARE, (), None
        self.next += 1
        return [ApplyEvents((declared,)), self]

    def _paying(self, state: GameState, step: PaymentStep) -> TaskResult:
        cost = self._cost()
        match step:
            case NeedDecision():
                return step
            case Push(tasks=tasks):
                return Push((*tasks, self))
            case Paid(mana=mana):
                tasks = self._declared(state, cost.total)
                if mana:
                    spent = ManaSpent(player=cost.payer, mana=mana, rules=("509.1f", "118.3a"))
                    tasks.insert(0, ApplyEvents((spent,)))
                return Push(tuple(tasks))
            case Unpayable():
                self.stage = DeclarationStage.REVERSE
                return self.run(state)

    def _reverse(self, state: GameState, kept: tuple[int, ...]) -> TaskResult:
        reversed_ = self._cost().reverse(state, kept)
        self.stage, self.blocks, self.cost = DeclarationStage.DECLARE, (), None
        return Push((ApplyEvents((reversed_,)), self))  # 509.1: the same player declares again

    def check_answer(self, state: GameState, request: DecisionRequest, answer: AnswerValue) -> None:
        if self.cost is not None:
            self.cost.check_answer(state, self.stage, answer)

    def resume(self, state: GameState, request: DecisionRequest, answer: AnswerValue) -> TaskResult:
        match self.stage:
            case DeclarationStage.PAY:
                return self._paying(state, self._cost().payment.resume(state, request, answer))
            case DeclarationStage.REVERSE:
                if not isinstance(answer, PickMany):
                    raise EngineError(f"DeclareBlockers can't resume with {answer!r}")
                made = activations_made(self._cost().payment)
                return self._reverse(state, _kept(len(made), answer))
            case DeclarationStage.DECLARE:
                pass
        if not isinstance(request.space, ChooseAssignment) or not isinstance(answer, Assignment):
            raise EngineError(f"DeclareBlockers can't resume with {answer!r}")
        player = _combat(state).defending_players[self.next]
        self.blocks = declared_blocks(request.space, answer.picks)
        total = block_cost(state, self.blocks)
        if total is None:
            return Push(tuple(self._declared(state, None)))
        blockers = tuple(blocker for blocker, _ in self.blocks)
        self.cost = DeclarationCost(
            player, take_checkpoint(state), total, PayCosts(player, total, ForBlock(blockers))
        )
        self.stage = DeclarationStage.PAY
        return self.run(state)


@dataclass(slots=True)
class CombatDamage(Task):
    """510.1-510.2: combat damage is assigned, then dealt all at once.

    510.1: each attacking creature, then each blocking creature (``rules.combat.
    damage_recipients``), assigns ``defaults.combat_damage_amount`` (its power, 510.1a; 0 or
    less: none) among its possible recipients:

    - none (an unblocked creature attacking nothing or a player who left, 510.1b, 800.4e; a
      blocked one with no blocker left, 510.1c; a blocker blocking nothing, 510.1d): nothing;
    - one: all of it to that one, without a question (design.md §6: one possible assignment);
    - two or more (510.1c-d): divided as ``defaults.combat_damage_assigner`` (its controller)
      chooses. Each player assigns all the damage they divide in one ``ASSIGN_COMBAT_DAMAGE``
      decision, a ``DistributeEach`` with one ``Distribute`` per creature (minimum 0 each),
      in APNAP order (510.1: the active player first, then the defending players; 802.5). The
      space checks the total assignment (510.1e), so an illegal one is refused and the player
      assigns again (733).

    510.2: the assigned damage is dealt simultaneously, one ``DamageDealt`` per source
    (``combat=True``, 120.4b) in one set of events, after every player has assigned. Combat damage
    a commander would deal to a player must be tallied (903.10a, M7): a gap until then, raised
    before anyone is asked or anything is dealt.

    ``answered`` keeps each player's announced assignment with the space it answered. Run again
    after a concession (104.3a), the task keeps every announced assignment (leaving the game
    undoes no announcement, 800.4a; 510.1e's return applies only to an illegal assignment): what
    has left combat since isn't dealt the damage assigned to it, and the players who haven't
    assigned yet are asked about the board as it is now.
    """

    answered: tuple[tuple[PlayerId, DistributeEach, AmountsEach], ...] = ()

    def run(self, state: GameState) -> TaskResult:
        current = dict(damage_recipients(state))
        announced = self._announced()
        assignments: list[tuple[ObjectId, tuple[tuple[Option, int], ...]]] = []
        divided: dict[PlayerId, list[tuple[ObjectId, Distribute]]] = {}
        for creature, recipients in current.items():
            if creature in announced:
                # 510.1: its assignment was announced and stands; what has left combat since
                # (a player who conceded took their creatures, 800.4a) isn't dealt damage.
                still = [(r, amount) for r, amount in announced[creature] if r in recipients]
                assignments.append((creature, tuple(still)))
                continue
            if not recipients:
                continue  # 510.1b-d: it assigns no combat damage
            amount = defaults.combat_damage_amount(state, creature)
            if amount <= 0:
                continue  # 510.1a
            if any(isinstance(r, PlayerOption) for r in recipients) and _is_commander(
                state, creature
            ):
                raise NotImplementedRule(
                    "903.10a: tallying the combat damage a commander deals to a player (M7)"
                )
            if len(recipients) == 1:
                assignments.append((creature, ((recipients[0], amount),)))
                continue
            assigner = defaults.combat_damage_assigner(state, creature)
            if any(player == assigner for player, _, _ in self.answered):
                raise EngineError(
                    f"player {assigner} has assigned combat damage, but not {creature}'s (510.1)"
                )
            divided.setdefault(assigner, []).append(
                (creature, Distribute(recipients, amount, minimum_each=0))
            )
        for player in apnap_order(state):
            parts = divided.get(player)
            if not parts:
                continue
            return NeedDecision(
                player=player,
                kind=DecisionKind.ASSIGN_COMBAT_DAMAGE,
                space=DistributeEach(
                    tuple(ObjectOption(creature) for creature, _ in parts),
                    tuple(part for _, part in parts),
                ),
                prompt="Assign combat damage: divide each creature's damage among the "
                "creatures it is blocking or blocked by.",
                rules=("510.1", "510.1c", "510.1d", "510.1e", "802.5"),
            )
        events = _damage_events(state, assignments)
        if not events:
            return Done()
        return Push((ApplyEvents(events),))

    def _announced(self) -> dict[ObjectId, tuple[tuple[Option, int], ...]]:
        """The assignments already announced (510.1), by source: each recipient and amount."""
        announced: dict[ObjectId, tuple[tuple[Option, int], ...]] = {}
        for _, space, answer in self.answered:
            for source, part, amounts in zip(
                space.sources, space.parts, answer.amounts, strict=True
            ):
                if not isinstance(source, ObjectOption):
                    raise EngineError(f"{source!r} isn't a creature dealing combat damage")
                announced[source.object] = tuple(zip(part.recipients, amounts.amounts, strict=True))
        return announced

    def resume(self, state: GameState, request: DecisionRequest, answer: AnswerValue) -> TaskResult:
        if not isinstance(request.space, DistributeEach) or not isinstance(answer, AmountsEach):
            raise EngineError(f"CombatDamage can't resume with {answer!r}")
        self.answered = (*self.answered, (request.player, request.space, answer))
        return Push((self,))


def _damage_events(
    state: GameState, assignments: list[tuple[ObjectId, tuple[tuple[Option, int], ...]]]
) -> tuple[Event, ...]:
    """510.2: one ``DamageDealt`` per source that assigned any damage, attackers first, then
    blockers (``damage_recipients``' order); 0 damage isn't dealt (120.8)."""
    order = {creature: index for index, (creature, _) in enumerate(damage_recipients(state))}
    events: list[Event] = []
    for source, assigned in sorted(assignments, key=lambda item: order[item[0]]):
        to_objects = tuple(
            (r.object, amount) for r, amount in assigned if isinstance(r, ObjectOption) and amount
        )
        to_players = tuple(
            (r.player, amount) for r, amount in assigned if isinstance(r, PlayerOption) and amount
        )
        if not to_objects and not to_players:
            continue
        rules = ("510.2", "510.1b", "120.3a") if to_players else ("510.2", "510.1c", "120.3e")
        events.append(
            DamageDealt(
                source=source,
                to_objects=to_objects,
                to_players=to_players,
                combat=True,
                rules=rules,
            )
        )
    return tuple(events)


def _is_commander(state: GameState, obj: ObjectId) -> bool:
    """Whether the permanent ``obj`` is a commander in a game with the Commander rules (903.3:
    the designation belongs to the card, whoever's it is)."""
    if state.config.commander is None:
        return False
    game_object = state.objects[obj]
    if game_object.zone.kind is not ZoneKind.BATTLEFIELD or game_object.card is None:
        return False
    return any(game_object.card in player.commanders for player in state.players)
