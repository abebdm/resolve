"""Turns, phases, steps and priority (500-514, 117).

A turn has five phases (500.1): beginning, precombat main, combat, postcombat main and ending.
The beginning, combat and ending phases are made of steps; a main phase has none (505.2).
``TURN_SEQUENCE`` lists every segment of a turn in order, a main phase being a segment with no
step. No effect can add or skip phases or steps yet (500.7-500.11); the rules that skip steps
(103.8a, 508.8) are applied by ``resolve.engine.turns.TakeTurn``.

``TurnState`` is the turn in progress: its number, the active player (102.1), the current phase
and step, and the priority bookkeeping of 117: who holds priority now and who has passed in
succession since the last action (117.4). The priority fields are procedural pointers kept by
the priority task, not game events (docs/decisions.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from resolve.state.ids import PlayerId


class Phase(Enum):
    """The phases of a turn, in order (500.1)."""

    BEGINNING = "beginning"  # 501
    PRECOMBAT_MAIN = "precombat main"  # 505
    COMBAT = "combat"  # 506
    POSTCOMBAT_MAIN = "postcombat main"  # 505
    ENDING = "ending"  # 512


class Step(Enum):
    """The steps of the phases that have steps (501.1, 506.1, 512.1)."""

    UNTAP = "untap"  # 502
    UPKEEP = "upkeep"  # 503
    DRAW = "draw"  # 504
    BEGINNING_OF_COMBAT = "beginning of combat"  # 507
    DECLARE_ATTACKERS = "declare attackers"  # 508
    DECLARE_BLOCKERS = "declare blockers"  # 509
    COMBAT_DAMAGE = "combat damage"  # 510
    END_OF_COMBAT = "end of combat"  # 511
    END = "end"  # 513
    CLEANUP = "cleanup"  # 514


Segment = tuple[Phase, Step | None]
"""A phase and one of its steps, or a main phase (which has no steps) and ``None``."""

TURN_SEQUENCE: tuple[Segment, ...] = (
    (Phase.BEGINNING, Step.UNTAP),
    (Phase.BEGINNING, Step.UPKEEP),
    (Phase.BEGINNING, Step.DRAW),
    (Phase.PRECOMBAT_MAIN, None),
    (Phase.COMBAT, Step.BEGINNING_OF_COMBAT),
    (Phase.COMBAT, Step.DECLARE_ATTACKERS),
    (Phase.COMBAT, Step.DECLARE_BLOCKERS),
    (Phase.COMBAT, Step.COMBAT_DAMAGE),
    (Phase.COMBAT, Step.END_OF_COMBAT),
    (Phase.POSTCOMBAT_MAIN, None),
    (Phase.ENDING, Step.END),
    (Phase.ENDING, Step.CLEANUP),
)
"""Every segment of a turn, in order (500.1, 501.1, 505.1, 506.1, 512.1)."""

MAIN_PHASES = (Phase.PRECOMBAT_MAIN, Phase.POSTCOMBAT_MAIN)


def segment_of(where: Phase | Step) -> Segment:
    """The segment for a step, or for a main phase; ``ValueError`` for a phase with steps."""
    for segment in TURN_SEQUENCE:
        phase, step = segment
        if where is step or (step is None and where is phase):
            return segment
    raise ValueError(f"the {where.value} phase has steps; name one of them")


def gives_priority(step: Step | None) -> bool:
    """Whether players normally receive priority in this step (117.3a, 502.4, 514.3).

    No player receives priority in the untap step, and normally none in the cleanup step;
    ``None`` (a main phase) has priority.
    """
    return step not in (Step.UNTAP, Step.CLEANUP)


@dataclass(slots=True)
class TurnState:
    """The turn in progress.

    - ``number``: turns taken in the game so far, counting this one (the first turn is 1).
    - ``active_player``: whose turn it is (102.1).
    - ``phase``, ``step``: where the turn is; ``step`` is ``None`` in a main phase (505.2).
    - ``priority``: the player who holds priority, or ``None`` when no one does (117.3a: during
      turn-based actions, the untap step, and while a step is beginning or ending).
    - ``passed``: the players who have passed priority in succession since the last time a
      player took an action, in the order they passed (117.3d, 117.4).
    - ``lands_played``: lands the active player has played this turn (305.2).
    - ``segments``: the phases and steps still to begin this turn, in order (500.1), as data so
      effects can insert and remove them (500.8-500.10). A turn starts with all of them; the one
      in progress is not among them.
    """

    number: int
    active_player: PlayerId
    phase: Phase = Phase.BEGINNING
    step: Step | None = Step.UNTAP
    priority: PlayerId | None = None
    passed: list[PlayerId] = field(default_factory=list[PlayerId])
    lands_played: int = 0
    segments: list[Segment] = field(default_factory=list[Segment])

    @property
    def segment(self) -> Segment:
        """The current phase and step."""
        return (self.phase, self.step)

    @property
    def in_main_phase(self) -> bool:
        """Whether the turn is in one of its main phases (505.1)."""
        return self.phase in MAIN_PHASES
