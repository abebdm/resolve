"""Checkpoints: what reversing an illegal action restores (733, design.md §17.4).

When an action begins (casting a spell; from M4, activating an ability or taking a special
action), its task takes a ``Checkpoint``: a copy of every restorable ``GameState`` field. Every
field is restorable except those in ``NOT_RESTORED``:

- the event log, which records what happened, the attempt included;
- the task stack and ``pending``, which the engine loop owns;
- the ID, timestamp and request counters, which only ever grow, so no ID is reused;
- the RNG, which is never rewound, so a reversal can't be used to look at randomness.

``restore_checkpoint`` puts the copied fields back (733.1: "the entire action is reversed and any
payments already made are canceled"). Two things it refuses or keeps:

- 733.1 forbids reversing an action that moved cards to or from a library, shuffled one or
  revealed cards from one. 601.2h pays such costs last, once a payment is known to be possible,
  and mana abilities can't do them (605.1a), so finding one (``Event.library_action``) in the
  log since the checkpoint is an engine bug: ``EngineError``.
- A player who left the game during the attempt (a concession, 104.3a) stays gone: leaving isn't
  part of the action. Their restored record is replaced by the current one, and the objects they
  owned are removed again (800.4a).
"""

from __future__ import annotations

import copy
import dataclasses
from dataclasses import dataclass, field
from typing import Any

from resolve.errors import EngineError
from resolve.events.base import Event
from resolve.state.game import GameState, zone_list

NOT_RESTORED = (
    "event_log",
    "tasks",
    "pending",
    "next_object_id",
    "next_timestamp",
    "next_request_id",
    "rng",
)
"""The ``GameState`` fields a checkpoint leaves out (design.md §17.4)."""


@dataclass(slots=True)
class Checkpoint:
    """A copy of every restorable ``GameState`` field (``values``, by field name), and how long
    the event log was (``log_length``) when it was taken."""

    log_length: int
    values: dict[str, Any] = field(default_factory=dict[str, Any])


def restorable_fields() -> tuple[str, ...]:
    """The names of the ``GameState`` fields a checkpoint copies, in declaration order."""
    return tuple(f.name for f in dataclasses.fields(GameState) if f.name not in NOT_RESTORED)


def take_checkpoint(state: GameState) -> Checkpoint:
    """A checkpoint of ``state`` as it is now."""
    values = {name: copy.deepcopy(getattr(state, name)) for name in restorable_fields()}
    return Checkpoint(len(state.event_log), values)


def restore_checkpoint(state: GameState, checkpoint: Checkpoint) -> None:
    """Put ``state`` back as it was when ``checkpoint`` was taken (733.1), keeping what
    ``NOT_RESTORED`` lists and the departures of players who left meanwhile.

    Raises ``EngineError`` if an action since the checkpoint can't be reversed (733.1).
    """
    for entry in state.event_log[checkpoint.log_length :]:
        record = entry.record
        if isinstance(record, Event) and record.library_action:
            raise EngineError(
                f"733.1: {type(record).__name__} (log entry {entry.index}) involved a library, "
                "so the action can't be reversed"
            )
    current_players = state.players
    for name, value in checkpoint.values.items():
        setattr(state, name, copy.deepcopy(value))
    for current in current_players:
        if not current.left_game or state.player(current.id).left_game:
            continue
        # 800.4a: the player left during the attempt; they and their objects stay gone.
        owned = [o for o, game_object in state.objects.items() if game_object.owner == current.id]
        for obj in owned:
            zone_list(state, state.objects[obj].zone).remove(obj)
            del state.objects[obj]
        state.players[current.id] = current
