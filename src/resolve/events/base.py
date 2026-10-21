"""Events and the event log (design.md §7).

An event is one atomic change to the game. It is a frozen value: it names the objects and players
involved by ID and cites the CR rules behind it. ``apply`` makes the change; events are applied
only through the ``ApplyEvents`` task (``resolve.events.pipeline``), never directly.

An event is *proposed* before anything is known about its outcome ("player 1 draws a card") and
logged *as applied*: ``apply`` may return a copy that records what happened (which library
object was drawn, and the ID of the new object in the hand, 400.7).

The event log is the ordered record of the game. Each ``LogEntry`` holds either an applied event
or an ``AnswerRecord`` (an answered decision), plus who may see it: ``None`` means every player.
An entry that only some players may see can carry a ``redacted`` form for everyone else (a draw
shows other players the new hand object but not the library object it came from, design.md
§9). Player views (``view_for``) include the entries their player may see, and the redacted form
of the others that have one.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

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

    # 733.1: an action that moved cards to or from a library, shuffled one or revealed cards from
    # one can't be reversed. Events that do any of those say so.
    library_action: ClassVar[bool] = False

    def __post_init__(self) -> None:
        check_rules(self.rules)

    @abstractmethod
    def apply(self, state: GameState) -> Event | None:
        """Make the change to ``state``.

        Returns the event as applied, when applying it learned something the proposal didn't
        say (such as a new object's ID); ``None`` means the proposal itself is the record.
        """

    def visible_to(self, state: GameState) -> tuple[PlayerId, ...] | None:
        """Who may see this event in the log, judged before it is applied; ``None``: everyone."""
        return None

    def redacted(self) -> Event | None:
        """What players outside ``visible_to`` see of this applied event; ``None``: nothing."""
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
    """One entry of the event log. ``index`` is its position in the log, from 0.

    ``redacted`` is what players outside ``visible_to`` see instead of ``record``, if anything.
    """

    index: int
    record: Event | AnswerRecord
    visible_to: tuple[PlayerId, ...] | None
    redacted: Event | None = None

    @property
    def rules(self) -> tuple[str, ...]:
        """The CR rules cited by this entry."""
        return self.record.rules

    def is_visible_to(self, player: PlayerId) -> bool:
        """Whether ``player`` may see this entry."""
        return self.visible_to is None or player in self.visible_to

    def shown_to(self, player: PlayerId) -> LogEntry | None:
        """The entry as ``player`` sees it: itself, its redacted form, or nothing."""
        if self.is_visible_to(player):
            return self
        if self.redacted is not None:
            return LogEntry(self.index, self.redacted, None)
        return None


def append_log(
    state: GameState,
    record: Event | AnswerRecord,
    visible_to: tuple[PlayerId, ...] | None,
    redacted: Event | None = None,
) -> LogEntry:
    """Add an entry to the end of the event log."""
    entry = LogEntry(
        len(state.event_log),
        record,
        None if visible_to is None else tuple(sorted(dict.fromkeys(visible_to))),
        None if visible_to is None else redacted,
    )
    state.event_log.append(entry)
    return entry
