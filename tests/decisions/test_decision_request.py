"""Decision requests, answers and their structural validation (design.md §6)."""

from __future__ import annotations

import pytest

from resolve.decisions.kinds import DecisionKind
from resolve.decisions.request import DecisionAnswer, DecisionRequest, validate_answer
from resolve.decisions.spaces import ChooseNumber, Number, Pick
from resolve.errors import InvalidAnswer
from resolve.state.ids import PlayerId

REQUEST = DecisionRequest(
    id=7,
    player=PlayerId(1),
    kind=DecisionKind.CHOOSE_X,
    space=ChooseNumber(0, 3),
    prompt="Choose X.",
    rules=("107.3a",),
)


def test_a_matching_answer_in_the_space_is_valid() -> None:
    validate_answer(REQUEST, DecisionAnswer(7, PlayerId(1), Number(3)))


@pytest.mark.parametrize(
    ("answer", "message"),
    [
        (DecisionAnswer(6, PlayerId(1), Number(1)), "request 6"),
        (DecisionAnswer(7, PlayerId(0), Number(1)), "player 0"),
        (DecisionAnswer(7, PlayerId(1), Number(4)), "at most 3"),
        (DecisionAnswer(7, PlayerId(1), Pick(0)), "Number"),
    ],
)
def test_invalid_answers_are_rejected(answer: DecisionAnswer, message: str) -> None:
    with pytest.raises(InvalidAnswer, match=message):
        validate_answer(REQUEST, answer)


def test_an_answer_must_be_a_decision_answer() -> None:
    with pytest.raises(InvalidAnswer, match="DecisionAnswer"):
        validate_answer(REQUEST, Number(1))  # type: ignore[arg-type]


@pytest.mark.parametrize("rules", [(), ("ten",), ("103.1", "1.1")])
def test_requests_must_cite_the_rules_that_ask_for_them(rules: tuple[str, ...]) -> None:
    with pytest.raises(ValueError, match="CR citation"):
        DecisionRequest(1, PlayerId(0), DecisionKind.MAY, ChooseNumber(0, 1), "?", rules)


def test_decision_kinds_have_distinct_values() -> None:
    values = [kind.value for kind in DecisionKind]
    assert len(values) == len(set(values))
    assert DecisionKind.CHOOSE_STARTING_PLAYER in DecisionKind
