"""Drawing cards (121)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.events.cards import CardDrawn
from resolve.events.pipeline import ApplyEvents
from resolve.state.ids import PlayerId
from resolve.tasks import Done, Push, Task, TaskResult

if TYPE_CHECKING:
    from resolve.state.game import GameState


@dataclass(slots=True)
class DrawCards(Task):
    """``player`` draws ``count`` cards, one at a time (121.2).

    Each draw is its own event, so replacement effects apply to each draw separately and finish
    before the next begins (121.6b). ``rules`` are cited on every draw, the cause first.
    ``drawn`` counts the draws done so far.
    """

    player: PlayerId
    count: int
    rules: tuple[str, ...]
    drawn: int = 0

    def run(self, state: GameState) -> TaskResult:
        if self.drawn >= self.count:
            return Done()
        self.drawn += 1
        draw = ApplyEvents((CardDrawn(player=self.player, rules=self.rules),))
        if self.drawn == self.count:
            return Push((draw,))
        return Push((draw, self))
