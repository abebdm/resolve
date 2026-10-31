"""Events of combat (506-511; design.md §17.18): the combat phase's combat state beginning and
ending, attackers being declared, and blockers being declared.

- ``CombatBegan`` (506.2, 802.2): as the first step of a combat phase begins, the combat state
  is created with its defending players. 507.1 has no choice to make: every multiplayer game
  uses the attack multiple players option (802), whose defending players are every opponent.
- ``AttackersDeclared`` (508.1k): the chosen creatures become attacking creatures, each
  attacking what was announced for it (508.1b, 802.3).
- ``BlockersDeclared`` (509.1g-h): the chosen creatures become blocking creatures, and each
  attacker becomes blocked or unblocked, which it stays for the rest of combat (509.1h).
  M3.2 declares no blocks yet (509.1 is a gap whenever a block is possible), so its event has
  only unblocked attackers; M3.3 declares blocks with it.
- ``CombatEnded`` (511.3): as the end of combat step ends, everything is removed from combat.

All are public: the combat state is (``PlayerView.combat``).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from resolve.errors import EngineError
from resolve.events.base import Event
from resolve.state.combat import AttackRecord, AttackTarget, BlockRecord, CombatState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.turn import Phase

if TYPE_CHECKING:
    from resolve.state.game import GameState


def _combat(state: GameState) -> CombatState:
    turn = state.turn
    if turn is None or turn.combat is None:
        raise EngineError("there is no combat in progress (506.1)")
    return turn.combat


@dataclass(frozen=True, kw_only=True)
class CombatBegan(Event):
    """The combat phase's combat state begins, with ``defending_players`` (506.2, 802.2)."""

    defending_players: tuple[PlayerId, ...]

    def apply(self, state: GameState) -> None:
        turn = state.turn
        if turn is None or turn.phase is not Phase.COMBAT:
            raise EngineError("a combat begins only in a combat phase (506.1)")
        if turn.combat is not None:
            raise EngineError("this combat phase already has its combat state")
        turn.combat = CombatState(self.defending_players)


@dataclass(frozen=True, kw_only=True)
class AttackersDeclared(Event):
    """The creatures of ``attacks`` become attacking creatures, each attacking its target, in
    this order (508.1k): declared, not put onto the battlefield attacking (508.4), and not yet
    blocked or unblocked (509.1h decides that)."""

    attacks: tuple[tuple[ObjectId, AttackTarget], ...]

    def apply(self, state: GameState) -> None:
        combat = _combat(state)
        if not self.attacks:
            raise EngineError("an empty declaration of attackers isn't an event (508.8)")
        for attacker, _ in self.attacks:
            if attacker in combat.attackers:
                raise EngineError(f"object {attacker} is already attacking")
        for attacker, target in self.attacks:
            combat.attackers[attacker] = AttackRecord(attacker, target)
        combat.attacks_happened = True  # 508.8


@dataclass(frozen=True, kw_only=True)
class BlockersDeclared(Event):
    """Blockers are declared (509.1g-h): each blocker of ``blocks`` blocks its attackers, in
    the order given; each attacker it names becomes blocked, and every other attacking creature
    whose status is undecided becomes unblocked. Blocked status then stays fixed (509.1h)."""

    blocks: tuple[tuple[ObjectId, tuple[ObjectId, ...]], ...] = ()

    def apply(self, state: GameState) -> None:
        combat = _combat(state)
        blocked: dict[ObjectId, None] = {}
        for blocker, attackers in self.blocks:
            if blocker in combat.blockers:
                raise EngineError(f"object {blocker} is already blocking")
            for attacker in attackers:
                if attacker not in combat.attackers:
                    raise EngineError(f"object {attacker} isn't attacking, so it can't be blocked")
                blocked[attacker] = None
        for blocker, attackers in self.blocks:
            combat.blockers[blocker] = BlockRecord(blocker, attackers)
        for attacker, record in combat.attackers.items():
            if record.blocked is None:
                combat.attackers[attacker] = replace(record, blocked=attacker in blocked)


@dataclass(frozen=True, kw_only=True)
class CombatEnded(Event):
    """511.3: as the end of combat step ends, all creatures are removed from combat; the
    combat phase is over."""

    def apply(self, state: GameState) -> None:
        _combat(state)
        assert state.turn is not None
        state.turn.combat = None
