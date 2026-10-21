"""Casting spells (601.2): ``CastSpell``. Stub until M2.3's implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.errors import NotImplementedRule
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.spell import CastPermission, CastVariant
from resolve.tasks import Task, TaskResult

if TYPE_CHECKING:
    from resolve.state.game import GameState


@dataclass(slots=True)
class CastSpell(Task):
    """``player`` casts ``card`` as ``variant`` under ``permission`` (601.2)."""

    player: PlayerId
    card: ObjectId
    variant: CastVariant
    permission: CastPermission

    def run(self, state: GameState) -> TaskResult:
        raise NotImplementedRule("601.2: casting a spell (M2.3, in progress)")
