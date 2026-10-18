"""Drawing cards (121)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.errors import NotImplementedRule
from resolve.state.ids import PlayerId
from resolve.tasks import Task, TaskResult

if TYPE_CHECKING:
    from resolve.state.game import GameState


@dataclass(slots=True)
class DrawCards(Task):
    """``player`` draws ``count`` cards, one at a time (121.2)."""

    player: PlayerId
    count: int
    rules: tuple[str, ...]

    def run(self, state: GameState) -> TaskResult:
        raise NotImplementedRule("121.1: drawing cards")
