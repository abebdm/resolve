"""Events of combat (506-511): the combat phase's combat state beginning and ending, and
attackers being declared. Stubs until M3.2's implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.errors import NotImplementedRule
from resolve.events.base import Event
from resolve.state.combat import AttackTarget
from resolve.state.ids import ObjectId, PlayerId

if TYPE_CHECKING:
    from resolve.state.game import GameState


@dataclass(frozen=True, kw_only=True)
class CombatBegan(Event):
    defending_players: tuple[PlayerId, ...]

    def apply(self, state: GameState) -> None:
        raise NotImplementedRule("506.2: the combat state (M3.2)")


@dataclass(frozen=True, kw_only=True)
class AttackersDeclared(Event):
    attacks: tuple[tuple[ObjectId, AttackTarget], ...]

    def apply(self, state: GameState) -> None:
        raise NotImplementedRule("508.1k: attacking creatures (M3.2)")


@dataclass(frozen=True, kw_only=True)
class CombatEnded(Event):
    def apply(self, state: GameState) -> None:
        raise NotImplementedRule("511.3: the end of combat (M3.2)")
