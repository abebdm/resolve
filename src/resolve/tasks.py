"""Tasks and task results (design.md §5).

A task is one step of the game's procedure, stored as data on ``GameState.tasks`` (a stack whose
last element runs next). The engine loop calls the top task's ``run`` and acts on its result:

- ``Done()``: the task is finished and is popped.
- ``Push(tasks)``: the task is popped and replaced by ``tasks``; ``tasks[0]`` runs next. A task
  that wants to continue after its sub-tasks puts itself last, as in
  ``Push((child, self))``, after updating its own fields to record where it is.
- ``NeedDecision(...)``: the engine stops and waits for a player's answer. The task stays on top.
  When the answer comes, the engine calls ``check_answer`` and then ``resume`` on this same task.

A task keeps all of its progress in its own fields, never in Python locals across calls, so a
state copied or pickled while the task is paused resumes exactly as the original would. Tasks
store object and player IDs, never references to ``GameObject`` or ``Player`` instances. They
change the game only through ``state`` and never touch ``state.tasks`` themselves.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.citations import check_rules
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import AnswerSpace, AnswerValue
from resolve.errors import EngineError
from resolve.state.ids import ObjectId, PlayerId

if TYPE_CHECKING:
    from resolve.decisions.request import DecisionRequest
    from resolve.state.game import GameState


class Task(ABC):
    """One step of the game's procedure.

    Subclasses are ``@dataclass(slots=True)`` classes whose fields are pure data.
    """

    __slots__ = ()

    @abstractmethod
    def run(self, state: GameState) -> TaskResult:
        """Do this task's work (or its first part) and say what happens next."""

    def check_answer(self, state: GameState, request: DecisionRequest, answer: AnswerValue) -> None:
        """Reject an answer the request's space allows but the rules don't.

        Called before ``resume``, after the answer space has accepted the answer. It must not
        change anything: raise ``InvalidAnswer`` to reject the answer. The default accepts it.
        """
        return None

    def resume(self, state: GameState, request: DecisionRequest, answer: AnswerValue) -> TaskResult:
        """Continue with the validated answer to the decision this task asked for."""
        raise EngineError(f"{type(self).__name__} doesn't ask for decisions")


@dataclass(frozen=True)
class Done:
    """The task is finished."""


@dataclass(frozen=True)
class Push:
    """Replace the task with ``tasks``, which then run in order (``tasks[0]`` first)."""

    tasks: tuple[Task, ...]

    def __post_init__(self) -> None:
        if not self.tasks:
            raise EngineError("Push needs at least one task; return Done() instead")


@dataclass(frozen=True)
class NeedDecision:
    """Stop until ``player`` answers; the engine turns this into a ``DecisionRequest``."""

    player: PlayerId
    kind: DecisionKind
    space: AnswerSpace
    prompt: str
    rules: tuple[str, ...]
    source: ObjectId | None = None

    def __post_init__(self) -> None:
        check_rules(self.rules)


TaskResult = Done | Push | NeedDecision
