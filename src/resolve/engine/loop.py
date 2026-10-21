"""The engine loop: run tasks until a decision is needed or the game ends (design.md §5).

``run`` repeatedly takes the top task of ``state.tasks``, runs it and applies its result. It stops
when a task returns ``NeedDecision`` (the request is stored in ``state.pending``) or when the game
is over (``state.result`` is set).

``submit_answer`` validates an answer, then resumes the paused task with it:

1. The answer must be for the pending request, from its player, and inside its answer space.
2. The paused task's ``check_answer`` may reject it on rules grounds.
3. Only then is anything changed: the answer is logged, ``pending`` is cleared, the task's
   ``resume`` runs, and the loop continues.

Steps 1 and 2 change nothing, so a rejected answer (``InvalidAnswer``) leaves the state exactly as
it was.
"""

from __future__ import annotations

from resolve.decisions.request import DecisionAnswer, DecisionRequest, validate_answer
from resolve.errors import EngineError, InvalidAnswer
from resolve.events.base import AnswerRecord, append_log
from resolve.state.game import GameState
from resolve.tasks import Done, NeedDecision, Push, Task, TaskResult

# Tasks one call to ``run`` may execute before the engine assumes it is stuck. This guards
# against engine bugs only; mandatory loops in the game itself are 104.4b (M7).
MAX_TASKS_PER_RUN = 1_000_000


def run(state: GameState) -> None:
    """Run tasks until a decision is pending or the game is over."""
    if state.pending is not None:
        raise EngineError("a decision is pending; answer it with submit()")
    executed = 0
    while state.pending is None and state.result is None:
        if not state.tasks:
            raise EngineError("the task stack is empty but the game isn't over")
        if executed >= MAX_TASKS_PER_RUN:
            raise EngineError(f"more than {MAX_TASKS_PER_RUN} tasks ran without a decision")
        task = state.tasks[-1]
        apply_result(state, task, task.run(state))
        executed += 1


def apply_result(state: GameState, task: Task, result: TaskResult) -> None:
    """Act on what ``task`` (the top of the task stack) returned."""
    if not state.tasks or state.tasks[-1] is not task:
        raise EngineError(f"{type(task).__name__} changed the task stack itself")
    match result:
        case Done():
            state.tasks.pop()
        case Push(tasks=tasks):
            state.tasks.pop()
            state.tasks.extend(reversed(tasks))
        case NeedDecision():
            state.player(result.player)  # validates the ID
            state.pending = DecisionRequest(
                id=state.next_request_id,
                player=result.player,
                for_player=result.player,
                kind=result.kind,
                space=result.space,
                prompt=result.prompt,
                rules=result.rules,
                source=result.source,
            )
            state.next_request_id += 1


def submit_answer(state: GameState, answer: DecisionAnswer) -> None:
    """Validate ``answer`` for the pending decision, resume the paused task, and run on."""
    if state.result is not None:
        raise InvalidAnswer("the game is over")
    request = state.pending
    if request is None:
        raise EngineError("no decision is pending (the engine stopped with an error earlier)")
    validate_answer(request, answer)
    task = state.tasks[-1]
    task.check_answer(state, request, answer.value)

    append_log(
        state,
        AnswerRecord(
            request_id=request.id,
            player=request.player,
            kind=request.kind,
            value=answer.value,
            rules=request.rules,
        ),
        (request.player,),
    )
    state.pending = None
    apply_result(state, task, task.resume(state, request, answer.value))
    if state.pending is None and state.result is None:
        run(state)
