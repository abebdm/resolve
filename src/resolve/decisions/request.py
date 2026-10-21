"""Decision requests and answers (design.md §6).

The engine asks a question with a ``DecisionRequest`` and an agent answers with a
``DecisionAnswer``. A request contains only what its deciding player may know.
"""

from __future__ import annotations

from dataclasses import dataclass

from resolve.citations import check_rules
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import AnswerSpace, AnswerValue
from resolve.errors import InvalidAnswer
from resolve.state.ids import ObjectId, PlayerId
from resolve.values import Immutable


@dataclass(frozen=True)
class DecisionRequest(Immutable):
    """A question the engine is waiting for a player to answer.

    - ``id``: unique within the game; the answer must echo it, so a stale answer is refused.
    - ``player``: who answers. ``for_player``: whose decision it is by the rules. They differ
      when another player makes the decision for them (723.5, 723.8, 723.9); only ``player``
      may answer, and resources used are ``for_player``'s (723.5a).
    - ``kind`` and ``space``: what is asked, and which answers are accepted.
    - ``prompt``: a short English description for text interfaces.
    - ``rules``: the CR rules that call for this decision.
    - ``source``: the object the decision is about, if any.
    """

    id: int
    player: PlayerId
    for_player: PlayerId
    kind: DecisionKind
    space: AnswerSpace
    prompt: str
    rules: tuple[str, ...]
    source: ObjectId | None = None

    def __post_init__(self) -> None:
        check_rules(self.rules)


@dataclass(frozen=True)
class DecisionAnswer(Immutable):
    """A player's answer to the request with id ``request_id``."""

    request_id: int
    player: PlayerId
    value: AnswerValue


def validate_answer(request: DecisionRequest, answer: DecisionAnswer) -> None:
    """Check that ``answer`` answers ``request`` and lies in its answer space.

    This is the structural half of validation; the asking task checks the rest
    (``Task.check_answer``). Raises ``InvalidAnswer``.
    """
    if not isinstance(answer, DecisionAnswer):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise InvalidAnswer(f"expected a DecisionAnswer, got {answer!r}")
    if answer.request_id != request.id:
        raise InvalidAnswer(
            f"answer is for request {answer.request_id!r}, but request {request.id} is pending"
        )
    if answer.player != request.player:
        raise InvalidAnswer(
            f"player {answer.player!r} answered, but the decision is player {request.player}'s"
        )
    request.space.validate(answer.value)
