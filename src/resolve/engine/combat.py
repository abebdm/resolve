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
from typing import TYPE_CHECKING

from resolve.cards.keywords import Vigilance, has_keyword
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import (
    AmountsEach,
    AnswerValue,
    Assignment,
    ChooseAssignment,
    Distribute,
    DistributeEach,
    ObjectOption,
    Option,
    PlayerOption,
)
from resolve.effects.characteristics import characteristics
from resolve.errors import EngineError, NotImplementedRule
from resolve.events.base import Event
from resolve.events.combat import AttackersDeclared, BlockersDeclared
from resolve.events.damage import DamageDealt
from resolve.events.permanents import PermanentTapped
from resolve.events.pipeline import ApplyEvents
from resolve.rules import defaults
from resolve.rules.combat import (
    attack_declaration,
    block_declaration,
    damage_recipients,
    declared_attacks,
    declared_blocks,
)
from resolve.state.combat import CombatState
from resolve.state.game import apnap_order
from resolve.state.ids import ObjectId, PlayerId
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


@dataclass(slots=True)
class DeclareAttackers(Task):
    """508.1: the attacking creatures are declared, by ``defaults.attack_declarer`` (the active
    player).

    1. 508.1a-b: a ``DECLARE_ATTACKERS`` decision, the ``ChooseAssignment`` compiled by
       ``resolve.rules.combat.attack_declaration``; not asked when no creature may attack. The
       space validates the answer, so an illegal declaration is refused before anything
       changes (508.1, 733).
    2. 508.1c-d (restrictions and requirements on the whole declaration), 508.1e (banding) and
       508.1g-j (costs to attack) have nothing to apply yet: their cards arrive in M3.5 and M9.
    3. 508.1f: the chosen creatures without vigilance tap (702.20b), at the same time; tapping
       isn't a cost.
    4. 508.1k: ``AttackersDeclared`` makes them attacking creatures. 508.1m's triggers are M4's.
    """

    def run(self, state: GameState) -> TaskResult:
        space = attack_declaration(state)
        if space is None:
            return Done()  # 508.1a: no creature can attack, so none does
        return NeedDecision(
            player=defaults.attack_declarer(state),
            kind=DecisionKind.DECLARE_ATTACKERS,
            space=space,
            prompt="Declare attackers: choose what each creature attacks, if anything.",
            rules=("508.1", "508.1a", "508.1b"),
        )

    def resume(self, state: GameState, request: DecisionRequest, answer: AnswerValue) -> TaskResult:
        if not isinstance(request.space, ChooseAssignment) or not isinstance(answer, Assignment):
            raise EngineError(f"DeclareAttackers can't resume with {answer!r}")
        attacks = declared_attacks(request.space, answer.picks)
        if not attacks:
            return Done()  # 508.8 reads that none attacked
        taps = tuple(
            PermanentTapped(obj=obj, rules=("508.1f", "701.26a"))
            for obj, _ in attacks
            if not has_keyword(characteristics(state, obj), Vigilance)  # 702.20b
        )
        declared = AttackersDeclared(attacks=attacks, rules=("508.1k", "508.1b"))
        tasks: list[Task] = [ApplyEvents(taps)] if taps else []
        tasks.append(ApplyEvents((declared,)))
        return Push(tuple(tasks))


@dataclass(slots=True)
class DeclareBlockers(Task):
    """509.1, 802.4: each defending player, in APNAP order, declares their blockers.

    For each defending player still in the game (in ``CombatState.defending_players``' order,
    which is APNAP order, 506.2), from ``next`` on:

    1. 509.1a: a ``DECLARE_BLOCKERS`` decision for ``defaults.block_declarer``, the
       ``ChooseAssignment`` compiled by ``resolve.rules.combat.block_declaration``; not asked
       when none of their creatures may block (one possible declaration, none). The space
       validates the answer, so an illegal declaration is refused before anything changes
       (509.1, 733).
    2. 509.1b-c (restrictions and requirements on the whole declaration) and 509.1d-f (costs to
       block) have nothing to apply yet: their cards arrive in M3.4 and M3.5.
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

    def run(self, state: GameState) -> TaskResult:
        combat = _combat(state)
        players = combat.defending_players
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
                        rules=("509.1", "509.1a", "802.4"),
                    )
            self.next += 1
        if not any(record.blocked is None for record in combat.attackers.values()):
            return Done()
        declared = BlockersDeclared(rules=("509.1h", "509.1g"))
        return Push((ApplyEvents((declared,)),))

    def resume(self, state: GameState, request: DecisionRequest, answer: AnswerValue) -> TaskResult:
        if not isinstance(request.space, ChooseAssignment) or not isinstance(answer, Assignment):
            raise EngineError(f"DeclareBlockers can't resume with {answer!r}")
        player = _combat(state).defending_players[self.next]
        declared = BlockersDeclared(
            blocks=declared_blocks(request.space, answer.picks),
            defending_player=player,
            rules=("509.1g", "509.1h", "802.4"),
        )
        self.next += 1
        return Push((ApplyEvents((declared,)), self))


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

    ``answered`` keeps each player's assignment with the space it answered. Run again after a
    concession (104.3a), the task keeps an answer only if that player's space is unchanged,
    and asks again otherwise.
    """

    answered: tuple[tuple[PlayerId, DistributeEach, AmountsEach], ...] = ()

    def run(self, state: GameState) -> TaskResult:
        fixed: list[tuple[ObjectId, tuple[tuple[Option, int], ...]]] = []
        divided: dict[PlayerId, list[tuple[ObjectId, Distribute]]] = {}
        for creature, recipients in damage_recipients(state):
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
                fixed.append((creature, ((recipients[0], amount),)))
                continue
            assigner = defaults.combat_damage_assigner(state, creature)
            divided.setdefault(assigner, []).append(
                (creature, Distribute(recipients, amount, minimum_each=0))
            )
        kept: list[tuple[PlayerId, DistributeEach, AmountsEach]] = []
        for player in apnap_order(state):
            parts = divided.get(player)
            if not parts:
                continue
            space = DistributeEach(
                tuple(ObjectOption(creature) for creature, _ in parts),
                tuple(part for _, part in parts),
            )
            previous = next((a for p, sp, a in self.answered if p == player and sp == space), None)
            if previous is None:
                self.answered = tuple(kept)
                return NeedDecision(
                    player=player,
                    kind=DecisionKind.ASSIGN_COMBAT_DAMAGE,
                    space=space,
                    prompt="Assign combat damage: divide each creature's damage among the "
                    "creatures it is blocking or blocked by.",
                    rules=("510.1", "510.1c", "510.1d", "510.1e", "802.5"),
                )
            kept.append((player, space, previous))
        assignments = list(fixed)
        for _, space, answer in kept:
            for source, part, amounts in zip(
                space.sources, space.parts, answer.amounts, strict=True
            ):
                if not isinstance(source, ObjectOption):
                    raise EngineError(f"{source!r} isn't a creature dealing combat damage")
                assignments.append(
                    (source.object, tuple(zip(part.recipients, amounts.amounts, strict=True)))
                )
        events = _damage_events(state, assignments)
        if not events:
            return Done()
        return Push((ApplyEvents(events),))

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
