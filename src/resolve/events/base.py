"""Events and the event log (design.md §7).

An event is one atomic change to the game. It is a frozen value: it names the objects and players
involved by ID and cites the CR rules behind it. ``apply`` makes the change; events are applied
only through the ``ApplyEvents`` task (``resolve.events.pipeline``), never directly.

The event log is the ordered record of the game. Each ``LogEntry`` holds either an applied event
or an ``AnswerRecord`` (an answered decision), plus who may see it: ``None`` means every player.
Player views (``view_for``) include only the entries their player may see.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.citations import check_rules
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import AnswerValue
from resolve.state.ids import PlayerId
from resolve.values import Immutable

if TYPE_CHECKING:
    from resolve.state.game import GameState


@dataclass(frozen=True, kw_only=True)
class Event(Immutable, ABC):
    """One atomic change to the game.

    ``rules`` cites the CR rules that cause and govern the change, most specific cause first
    (for example ``("103.3", "701.24a")`` for the shuffle at the start of the game).
    """

    rules: tuple[str, ...]

    def __post_init__(self) -> None:
        check_rules(self.rules)

    @abstractmethod
    def apply(self, state: GameState) -> None:
        """Make the change to ``state``."""

    def visible_to(self, state: GameState) -> tuple[PlayerId, ...] | None:
        """Who may see this event in the log, judged before it is applied; ``None``: everyone."""
        return None


@dataclass(frozen=True)
class AnswerRecord(Immutable):
    """A decision answer, as recorded in the log.

    Replays are rebuilt from these (design.md §12). They are visible only to the player who
    answered: whatever the answer makes public shows up as events.
    """

    request_id: int
    player: PlayerId
    kind: DecisionKind
    value: AnswerValue
    rules: tuple[str, ...]


@dataclass(frozen=True)
class LogEntry(Immutable):
    """One entry of the event log. ``index`` is its position in the log, from 0."""

    index: int
    record: Event | AnswerRecord
    visible_to: tuple[PlayerId, ...] | None

    @property
    def rules(self) -> tuple[str, ...]:
        """The CR rules cited by this entry."""
        return self.record.rules

    def is_visible_to(self, player: PlayerId) -> bool:
        """Whether ``player`` may see this entry."""
        return self.visible_to is None or player in self.visible_to


def append_log(
    state: GameState, record: Event | AnswerRecord, visible_to: tuple[PlayerId, ...] | None
) -> LogEntry:
    """Add an entry to the end of the event log."""
    entry = LogEntry(
        len(state.event_log),
        record,
        None if visible_to is None else tuple(sorted(dict.fromkeys(visible_to))),
    )
    state.event_log.append(entry)
    return entry
