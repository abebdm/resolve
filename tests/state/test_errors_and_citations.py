"""NotImplementedRule and the CR citation format (CLAUDE.md rules 1 and 2)."""

from __future__ import annotations

import copy
import pickle

import pytest

from resolve.citations import check_rules, is_rule_reference
from resolve.errors import NotImplementedRule


def test_not_implemented_rule_names_the_rule_and_what_is_missing() -> None:
    gap = NotImplementedRule("613.7m: ordering simultaneous timestamps")
    assert gap.rule == "613.7m"
    assert gap.what == "ordering simultaneous timestamps"
    assert str(gap) == "613.7m: ordering simultaneous timestamps"


@pytest.mark.parametrize(
    "message",
    ["opening hands", "103.5 opening hands", "103.5:", "103.5: ", "x103.5: hands", "1.2: hands"],
)
def test_not_implemented_rule_refuses_messages_without_a_rule(message: str) -> None:
    with pytest.raises(ValueError, match="<CR number>: <what>"):
        NotImplementedRule(message)


def test_not_implemented_rule_is_not_a_builtin_not_implemented_error() -> None:
    """It mustn't be caught by handlers meant for abstract methods."""
    assert not issubclass(NotImplementedRule, NotImplementedError)


def test_not_implemented_rule_survives_copy_and_pickle() -> None:
    gap = NotImplementedRule("103.5: opening hands")
    for clone in (copy.deepcopy(gap), pickle.loads(pickle.dumps(gap))):
        assert (clone.rule, clone.what) == ("103.5", "opening hands")


@pytest.mark.parametrize("text", ["103", "103.1", "701.24a", "903.10a", "613.7m", "704.5aa"])
def test_valid_rule_references(text: str) -> None:
    assert is_rule_reference(text)


@pytest.mark.parametrize("text", ["", "10", "1034", "099.1", "103.", "103.1A", "103.0", "103.1abc"])
def test_invalid_rule_references(text: str) -> None:
    assert not is_rule_reference(text)


def test_check_rules_needs_a_non_empty_tuple_of_references() -> None:
    check_rules(("103.1",))
    for bad in ((), ["103.1"], ("103.1", 5)):
        with pytest.raises(ValueError, match="CR citation"):
            check_rules(bad)  # pyright: ignore[reportArgumentType] (deliberately the wrong type)
