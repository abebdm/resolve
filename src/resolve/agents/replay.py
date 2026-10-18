"""Replaying a game from its recorded inputs (design.md §12).

A game is a pure function of its config, decks, seed and ordered inputs: the answers to its
decisions and the concessions (104.3a). Both are in the event log, in the order they happened:
an ``AnswerRecord`` for each answer and a ``Conceded`` event for each concession. ``replay``
feeds them, in that order, to a new game started from the same config, decks and seed.
"""

from __future__ import annotations

from collections.abc import Iterable

from resolve.decisions.request import DecisionAnswer
from resolve.engine.api import pending_decision, submit
from resolve.engine.concede import concede
from resolve.errors import EngineError
from resolve.events.base import AnswerRecord, LogEntry
from resolve.events.game import Conceded
from resolve.state.game import GameState


class ReplayDiverged(EngineError):
    """The replayed game asked something else than the recorded game, or ended sooner."""


def inputs(log: Iterable[LogEntry]) -> list[AnswerRecord | Conceded]:
    """The inputs recorded in ``log``, in order: answers and concessions."""
    return [entry.record for entry in log if isinstance(entry.record, AnswerRecord | Conceded)]


def replay(state: GameState, log: Iterable[LogEntry]) -> int:
    """Apply the inputs of ``log`` to ``state``, a new game of the same config, decks and seed.

    Each answer must fit the decision the game is asking (same player and kind), and each
    concession must come from a player still in the game, or ``ReplayDiverged`` is raised; so it
    is if the game ends before the last input. Returns the number of inputs applied. Rules gaps
    (``NotImplementedRule``) propagate.
    """
    applied = 0
    for record in inputs(log):
        if state.result is not None:
            raise ReplayDiverged(f"the game ended before input {applied + 1}")
        if isinstance(record, Conceded):
            if state.player(record.player).left_game:
                raise ReplayDiverged(
                    f"input {applied + 1}: player {record.player} has already left the game"
                )
            concede(state, record.player)
        else:
            request = pending_decision(state)
            if request is None:
                raise ReplayDiverged(f"the game ended before input {applied + 1}")
            if (request.player, request.kind) != (record.player, record.kind):
                raise ReplayDiverged(
                    f"input {applied + 1} expects player {record.player} to answer "
                    f"{record.kind.value}, but player {request.player} is asked "
                    f"{request.kind.value}"
                )
            submit(state, DecisionAnswer(request.id, request.player, record.value))
        applied += 1
    return applied
