"""The combat state: who attacks what, and who blocks whom (506-511; design.md §17.18).

``TurnState.combat`` holds a ``CombatState`` during a combat phase, and ``None`` otherwise.
It is pure data, public to every player (``PlayerView.combat``):

- ``defending_players``: fixed as the combat phase begins (506.2; 802.2: every opponent of the
  attacking player in a multiplayer game, a deliberate non-parameter, docs/decisions.md
  2026-10-18). A player who leaves the game stays listed: damage that would be assigned to them
  isn't (800.4e).
- ``attackers``: the attacking creatures, in declaration order, each with an ``AttackRecord``.
- ``blockers``: the blocking creatures, in declaration order, each with a ``BlockRecord``.
- ``attacks_happened``: whether a creature was declared as an attacker or put onto the
  battlefield attacking this combat (508.8 reads this, not the current attackers: an attacker
  removed before blocks doesn't skip the declare blockers step).

``remove_from_combat`` is the one way a permanent leaves combat (506.4); ``CombatEnded`` ends it
all (511.3, ``resolve.events.combat``).

Room is left for the rest of §17.18: the phase's number (numbered segments, M3.8), the
first-strike record (510.4, M3.6), reselecting a target (508.7a) and bands (702.22, M9).
Records are immutable values: an update replaces the record.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from resolve.state.ids import ObjectId, PlayerId
from resolve.values import Immutable

if TYPE_CHECKING:
    from resolve.state.game import GameState


@dataclass(frozen=True)
class AttackPlayer(Immutable):
    """An attacker is attacking ``player`` (506.3, 508.1b)."""

    player: PlayerId


AttackTarget = AttackPlayer
"""What a creature attacks: a player (506.3). Planeswalkers and battles (306, 310) join it as
``AttackPermanent`` in M4."""


@dataclass(frozen=True)
class AttackRecord(Immutable):
    """One attacking creature (508.1k, 508.4).

    - ``attacker``: the creature (the key it is stored under in ``CombatState.attackers``).
    - ``target``: what it attacks; ``None`` once that planeswalker or battle has left combat: it
      is still attacking, but attacks nothing (506.4c).
    - ``declared``: declared as an attacker (508.1); ``False`` if it was put onto the
      battlefield attacking, so it never "attacked" (508.4).
    - ``blocked``: ``None`` until blockers are declared, then whether it is blocked; fixed from
      then on, even if its blockers leave (509.1h). One put onto the battlefield attacking after
      blockers were declared is unblocked (508.4d).
    """

    attacker: ObjectId
    target: AttackTarget | None
    declared: bool = True
    blocked: bool | None = None


@dataclass(frozen=True)
class BlockRecord(Immutable):
    """One blocking creature (509.1g): ``blocking`` lists the attackers it blocks, in the order
    they were chosen (one by default, 509.1a; more with ``blocks_allowed``). ``declared`` is
    ``False`` for one put onto the battlefield blocking (506.3e)."""

    blocker: ObjectId
    blocking: tuple[ObjectId, ...]
    declared: bool = True


@dataclass(slots=True)
class CombatState:
    """The combat of the current combat phase (506; see the module docstring)."""

    defending_players: tuple[PlayerId, ...]
    attackers: dict[ObjectId, AttackRecord] = field(default_factory=dict[ObjectId, AttackRecord])
    blockers: dict[ObjectId, BlockRecord] = field(default_factory=dict[ObjectId, BlockRecord])
    attacks_happened: bool = False

    def blockers_of(self, attacker: ObjectId) -> tuple[ObjectId, ...]:
        """The creatures blocking ``attacker``, in the order they were declared (509.1g)."""
        return tuple(
            record.blocker for record in self.blockers.values() if attacker in record.blocking
        )


def remove_from_combat(state: GameState, obj: ObjectId) -> None:
    """Remove ``obj`` from combat (506.4), if it is in combat: it stops being an attacking,
    blocking, blocked or unblocked creature.

    - An attacker leaves the attackers, and every blocker stops blocking it (it may then block
      nothing: 510.1d). Its blockers stay blocking creatures.
    - A blocker leaves the blockers; the attackers it blocked stay blocked (509.1h).
    - ``attacks_happened`` is unchanged: the creature was still declared (508.8).

    Called as a permanent leaves the battlefield (``move_object``, ``PlayerLeftGame``); control
    changes (M5), phasing (M9), regeneration (M6) and stopping being a creature (M5) will call
    it too. A planeswalker or battle being attacked (506.4c, M4) isn't in combat yet.
    """
    turn = state.turn
    combat = None if turn is None else turn.combat
    if combat is None:
        return
    if obj in combat.attackers:
        del combat.attackers[obj]
        for blocker, record in combat.blockers.items():
            if obj in record.blocking:
                blocking = tuple(attacker for attacker in record.blocking if attacker != obj)
                combat.blockers[blocker] = replace(record, blocking=blocking)
    combat.blockers.pop(obj, None)
