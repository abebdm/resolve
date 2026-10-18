"""Immutable value types are deeply immutable, so copies of a state may share them.

``Immutable.__deepcopy__`` returns the value itself (docs/decisions.md 2026-10-18). That is only
safe if nothing inside it can change, so every subclass must be a frozen dataclass whose fields
hold only scalars, enums, tuples and other ``Immutable`` values. These tests check every subclass
in the engine from its field types, and check real values at run time.
"""

from __future__ import annotations

import copy
import dataclasses
import importlib
import pickle
import pkgutil
import types
from enum import Enum
from typing import Any, Union, get_args, get_origin, get_type_hints

import pytest

import resolve
from resolve.cards.registry import CardDefinition
from resolve.data.cards import CardData, CardFace, Ruling, parse_card
from resolve.decisions.spaces import ChooseOne, ObjectOption, Pick, PlayerOption
from resolve.engine.api import submit
from resolve.errors import NotImplementedRule
from resolve.events.game import LibraryShuffled
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.invariants import check_immutable, mutable_parts
from resolve.values import Immutable
from tests import engine_support
from tests import scryfall_fixtures as fx
from tests.game_fixtures import DAYBREAKER, answer, start


def _import_all_engine_modules() -> None:
    for info in pkgutil.walk_packages(resolve.__path__, "resolve."):
        importlib.import_module(info.name)


def _all_subclasses(cls: type) -> list[type]:
    found: list[type] = []
    for sub in cls.__subclasses__():
        found.append(sub)
        found.extend(_all_subclasses(sub))
    return sorted(dict.fromkeys(found), key=lambda c: f"{c.__module__}.{c.__qualname__}")


_import_all_engine_modules()
IMMUTABLE_TYPES = _all_subclasses(Immutable)


def type_problems(tp: Any) -> list[str]:
    """Why an annotation allows a mutable value (empty if it doesn't)."""
    if tp in (int, str, bool, float, type(None)):
        return []
    supertype = getattr(tp, "__supertype__", None)
    if supertype is not None:  # a NewType
        return type_problems(supertype)
    if isinstance(tp, type) and issubclass(tp, Enum | Immutable):
        return []
    origin = get_origin(tp)
    if origin is tuple or origin in (Union, types.UnionType):
        return [
            problem for arg in get_args(tp) if arg is not Ellipsis for problem in type_problems(arg)
        ]
    return [f"{tp!r} isn't a scalar, enum, tuple or Immutable type"]


def class_problems(cls: type) -> list[str]:
    """Why a class isn't a deeply immutable frozen dataclass."""
    name = cls.__name__
    params = getattr(cls, "__dataclass_params__", None)
    if params is None or not params.frozen:
        return [f"{name} isn't a frozen dataclass"]
    hints = get_type_hints(cls)
    return [
        f"{name}.{field.name}: {problem}"
        for field in dataclasses.fields(cls)
        for problem in type_problems(hints[field.name])
    ]


def test_the_expected_value_types_are_immutable() -> None:
    assert engine_support.Marker in IMMUTABLE_TYPES, "event types defined in tests are checked too"
    names = {cls.__qualname__ for cls in IMMUTABLE_TYPES}
    expected = {
        "Card", "CardData", "CardFace", "CardDefinition", "Event", "LibraryShuffled",
        "DecisionRequest", "DecisionAnswer", "AnswerSpace", "ChooseOne", "ChooseSubset",
        "ChooseOrder", "ChooseNumber", "Distribute", "Pick", "PickMany", "Order", "Number",
        "Amounts", "PlayerOption", "ObjectOption", "LogEntry", "AnswerRecord", "GameConfig",
        "Zone", "GameResult", "Deck", "DeckCard", "PlayerView", "ObjectView",
    }  # fmt: skip
    assert expected <= names


@pytest.mark.parametrize("cls", IMMUTABLE_TYPES, ids=lambda cls: cls.__qualname__)
def test_every_immutable_type_is_a_deeply_immutable_frozen_dataclass(cls: type) -> None:
    assert class_problems(cls) == []


@pytest.mark.parametrize("cls", IMMUTABLE_TYPES, ids=lambda cls: cls.__qualname__)
def test_no_immutable_type_overrides_copying(cls: type) -> None:
    assert issubclass(cls, Immutable)
    assert cls.__deepcopy__ is Immutable.__deepcopy__
    assert cls.__copy__ is Immutable.__copy__


def test_the_type_check_catches_mutable_fields() -> None:
    @dataclasses.dataclass(frozen=True)
    class HasList:
        items: list[int]

    @dataclasses.dataclass(frozen=True)
    class HasDictInTuple:
        items: tuple[dict[str, int], ...]

    @dataclasses.dataclass
    class NotFrozen:
        value: int

    assert class_problems(HasList) != []
    assert class_problems(HasDictInTuple) != []
    assert class_problems(NotFrozen) == ["NotFrozen isn't a frozen dataclass"]
    assert type_problems(int | None) == []
    assert type_problems(tuple[PlayerId, ...]) == []
    assert type_problems(set[int]) != []


def test_copies_of_immutable_values_are_the_values_themselves() -> None:
    state = start(2)
    values: list[object] = [
        state.cards[next(iter(state.cards))],
        DAYBREAKER.data,
        DAYBREAKER.data.faces[0],
        CardDefinition("Forest"),
        LibraryShuffled(player=PlayerId(0), rules=("701.24a",)),
        state.pending,
        ChooseOne((PlayerOption(PlayerId(0)),)),
        Pick(0),
        state.config,
    ]
    for value in values:
        assert copy.deepcopy(value) is value
        assert copy.copy(value) is value
        assert pickle.loads(pickle.dumps(value)) == value
        check_immutable(value)


def test_the_runtime_check_catches_mutable_contents() -> None:
    """Frozen dataclasses don't check field types, so a list could be passed in at run time."""
    bad_space = ChooseOne([ObjectOption(ObjectId(1))])  # pyright: ignore[reportArgumentType]
    assert mutable_parts(bad_space) == ["value.options: list isn't immutable"]
    bad_pick = Pick({1})  # pyright: ignore[reportArgumentType]
    assert mutable_parts(bad_pick, "pick") == ["pick.index: set isn't immutable"]
    assert mutable_parts((1, [2])) == ["value[1]: list isn't immutable"]
    assert mutable_parts(start(2)) != []


def test_a_state_and_its_copy_share_card_data_but_not_mutable_parts() -> None:
    state = start(2)
    clone = copy.deepcopy(state)
    for card_id, card in state.cards.items():
        assert clone.cards[card_id] is card
        assert clone.cards[card_id].data is card.data
    assert clone.pending is state.pending
    assert clone.config is state.config
    assert clone.players[0] is not state.players[0]
    assert clone.players[0].library is not state.players[0].library
    assert clone.objects[ObjectId(1)] is not state.objects[ObjectId(1)]
    assert clone.tasks[0] is not state.tasks[0]
    assert clone.rng is not state.rng
    assert clone == state


def test_log_entries_are_shared_between_copies() -> None:
    state = start(2)
    with pytest.raises(NotImplementedRule):
        submit(state, answer(state, Pick(0)))
    clone = copy.deepcopy(state)
    assert all(a is b for a, b in zip(clone.event_log, state.event_log, strict=True))


def test_card_data_in_the_state_carries_no_rulings() -> None:
    """Rulings stay in the CardDatabase; they are for writing tests, not for playing."""
    for cls in (CardData, CardFace, CardDefinition):
        hints = get_type_hints(cls)
        assert all("Ruling" not in repr(hint) for hint in hints.values()), cls
    assert not any(isinstance(value, Ruling) for value in vars(parse_card(fx.FOREST)).values())
