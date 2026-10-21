"""Resolving the top object of the stack (608). Stub until M2.3's implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.errors import NotImplementedRule
from resolve.tasks import Task, TaskResult

if TYPE_CHECKING:
    from resolve.state.game import GameState


@dataclass(slots=True)
class ResolveTopOfStack(Task):
    """The top object of the stack resolves (608.1, 405.5)."""

    def run(self, state: GameState) -> TaskResult:
        raise NotImplementedRule("608.1: resolving the top object of the stack (M2.3, in progress)")
