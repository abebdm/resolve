"""Combat's turn-based actions (506-511; design.md §17.18).

``RunStep`` (``resolve.engine.turns``) runs them in their steps:

- **beginning of combat**: 507.1 has no choice (every multiplayer game uses the attack multiple
  players option, 802). The combat state is created as the combat phase's first step begins
  (``CombatBegan``, 506.2), before this step's turn-based actions.
- **declare attackers**: ``DeclareAttackers`` (508.1).
- **declare blockers**: ``DeclareBlockers`` (509.1): blocks are M3.3's. Until then a defending
  player who is attacked and controls an untapped creature could block, which is the gap
  ``NotImplementedRule("509.1")``; otherwise no block is possible, and every attacker becomes
  unblocked (509.1h).
- **combat damage**: ``CombatDamage`` (510.1-510.2), for unblocked attackers. Damage to and by
  blocking creatures (510.1c-d) is M3.3's gap.
- **end of combat**: none (511.1); as the step ends, ``CombatEnded`` removes everything from
  combat (511.3).

508.8 (skipping the declare blockers and combat damage steps when no creature attacked) is
``defaults.is_skipped``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.cards.keywords import Vigilance, has_keyword
from resolve.data.types import CardType
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import AnswerValue, Assignment, ChooseAssignment
from resolve.effects.characteristics import characteristics
from resolve.errors import EngineError, NotImplementedRule
from resolve.events.base import Event
from resolve.events.combat import AttackersDeclared, BlockersDeclared
from resolve.events.damage import DamageDealt
from resolve.events.permanents import PermanentTapped
from resolve.events.pipeline import ApplyEvents
from resolve.rules import defaults
from resolve.rules.combat import attack_declaration, declared_attacks
from resolve.state.combat import AttackPlayer, CombatState
from resolve.state.ids import ObjectId
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
    """509.1, until M3.3: whether any block is possible. A defending player still in the game who
    is attacked (509.1a, 802.4a: only creatures attacking them can be blocked by theirs) and
    controls an untapped creature that isn't a battle could block: declaring blocks is the gap.
    Otherwise the declaration is empty, and every attacker becomes unblocked (509.1h)."""

    def run(self, state: GameState) -> TaskResult:
        combat = _combat(state)
        attacked = {
            record.target.player
            for record in combat.attackers.values()
            if isinstance(record.target, AttackPlayer)
        }
        for obj in state.battlefield:
            permanent = state.objects[obj]
            if permanent.controller not in attacked or permanent.tapped:
                continue
            types = characteristics(state, obj).card_types
            if CardType.CREATURE in types and CardType.BATTLE not in types:
                raise NotImplementedRule("509.1: declaring blockers (M3.3)")
        if not any(record.blocked is None for record in combat.attackers.values()):
            return Done()
        declared = BlockersDeclared(rules=("509.1h", "509.1g"))
        return Push((ApplyEvents((declared,)),))


@dataclass(slots=True)
class CombatDamage(Task):
    """510.1-510.2: combat damage is assigned, then dealt all at once.

    510.1: each attacking creature, in declaration order, assigns ``defaults.combat_damage_amount``
    (its power, 510.1a; 0 or less: none):

    - unblocked, to the player it attacks (510.1b); nothing if it attacks nothing, or a player
      who has left the game (800.4e). One recipient is one possible assignment, so nobody is
      asked (design.md §6).
    - blocked, with no creature blocking it any more: nothing (510.1c).
    - blocked with blockers, and blockers' damage (510.1c-d): M3.3's, a gap until then.

    510.2: the assigned damage is dealt simultaneously, one ``DamageDealt`` per source
    (``combat=True``, 120.4b) in one set of events. Combat damage a commander would deal to a
    player must be tallied (903.10a, M7): a gap until then, raised before anything is dealt.
    """

    def run(self, state: GameState) -> TaskResult:
        combat = _combat(state)
        if any(record.blocking for record in combat.blockers.values()):
            raise NotImplementedRule(
                "510.1c: combat damage assigned to and by blocking creatures (M3.3)"
            )
        events: list[Event] = []
        for attacker, record in combat.attackers.items():
            if record.blocked is None:
                raise EngineError(f"attacker {attacker} is neither blocked nor unblocked (509.1h)")
            if record.blocked:
                continue  # 510.1c: no creature is blocking it
            target = record.target
            if target is None:
                continue  # 510.1b: it attacks nothing (506.4c)
            player = target.player
            if state.player(player).left_game:
                continue  # 800.4e
            amount = defaults.combat_damage_amount(state, attacker)
            if amount <= 0:
                continue  # 510.1a
            if _is_commander(state, attacker):
                raise NotImplementedRule(
                    "903.10a: tallying the combat damage a commander deals to a player (M7)"
                )
            events.append(
                DamageDealt(
                    source=attacker,
                    to_players=((player, amount),),
                    combat=True,
                    rules=("510.2", "510.1b", "120.3a"),
                )
            )
        if not events:
            return Done()
        return Push((ApplyEvents(tuple(events)),))


def _is_commander(state: GameState, obj: ObjectId) -> bool:
    """Whether the permanent ``obj`` is a commander in a game with the Commander rules (903.3:
    the designation belongs to the card, whoever's it is)."""
    if state.config.commander is None:
        return False
    game_object = state.objects[obj]
    if game_object.zone.kind is not ZoneKind.BATTLEFIELD or game_object.card is None:
        return False
    return any(game_object.card in player.commanders for player in state.players)
