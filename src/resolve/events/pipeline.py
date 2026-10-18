"""The event pipeline (design.md §7).

Every change to the game goes through ``ApplyEvents``. One ``ApplyEvents`` holds a set of
simultaneous events, which go through these stages:

1. **Replacement and prevention** (614-616): ``replacement_stage``. Nothing can create
   replacement or prevention effects yet, so it returns the events unchanged. M6 fills it in; when
   several effects apply, the affected player chooses their order (616.1), which is why the
   pipeline is a task that can stop for a decision.
2. **Apply** each event to the state, in order.
3. **Log** each event, with the players who may see it.
4. **Detect triggers** (603.2): ``detect_triggers``. No triggered abilities exist yet; M4 fills
   it in, looking back in time where 603.10 requires.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.errors import EngineError
from resolve.events.base import Event, append_log
from resolve.tasks import Done, Task, TaskResult

if TYPE_CHECKING:
    from resolve.state.game import GameState


@dataclass(slots=True)
class ApplyEvents(Task):
    """Apply a set of simultaneous events through the pipeline."""

    events: tuple[Event, ...]

    def __post_init__(self) -> None:
        if not self.events:
            raise EngineError("ApplyEvents needs at least one event")

    def run(self, state: GameState) -> TaskResult:
        events = replacement_stage(state, self.events)
        visibility = [event.visible_to(state) for event in events]
        for event, visible_to in zip(events, visibility, strict=True):
            event.apply(state)
            append_log(state, event, visible_to)
        detect_triggers(state, events)
        return Done()


def replacement_stage(state: GameState, events: tuple[Event, ...]) -> tuple[Event, ...]:
    """Apply replacement and prevention effects to proposed events (614-616).

    No replacement or prevention effects can exist yet (M6), so the events come back unchanged.
    """
    return events


def detect_triggers(state: GameState, events: tuple[Event, ...]) -> None:
    """Find triggered abilities that trigger on applied events (603.2).

    No triggered abilities can exist yet (M4), so nothing triggers.
    """
