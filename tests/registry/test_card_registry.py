"""Tests for the card registry (resolve.cards.registry)."""

from __future__ import annotations

import copy
import importlib
import pickle
import sys
import textwrap
from pathlib import Path

import pytest

from resolve.cards.registry import (
    CardDefinition,
    CardRegistry,
    DuplicateDefinitionError,
    RegistryError,
    UnimplementedCardError,
    collect_definitions,
    default_registry,
)
from resolve.data.cards import load_card_excerpt, parse_card
from tests import scryfall_fixtures as fx


def test_register_and_look_up_by_exact_name() -> None:
    elves = CardDefinition("Llanowar Elves")
    registry = CardRegistry([elves])
    assert registry.get("Llanowar Elves") is elves
    assert "Llanowar Elves" in registry
    assert "llanowar elves" not in registry
    assert len(registry) == 1


def test_empty_registry() -> None:
    registry = CardRegistry()
    assert len(registry) == 0
    assert registry.names() == ()
    assert 42 not in registry


def test_names_are_sorted() -> None:
    registry = CardRegistry([CardDefinition("Forest"), CardDefinition("Arcane Signet")])
    registry.register(CardDefinition("Command Tower"))
    assert registry.names() == ("Arcane Signet", "Command Tower", "Forest")


def test_registering_a_name_twice_is_an_error() -> None:
    registry = CardRegistry([CardDefinition("Forest")])
    with pytest.raises(DuplicateDefinitionError, match="Forest"):
        registry.register(CardDefinition("Forest"))
    assert len(registry) == 1


def test_unimplemented_card_is_refused_not_approximated() -> None:
    registry = CardRegistry([CardDefinition("Forest")])
    with pytest.raises(UnimplementedCardError) as caught:
        registry.get("Plains")
    assert caught.value.name == "Plains"
    assert str(caught.value) == "card 'Plains' is not implemented"
    assert isinstance(caught.value, KeyError)


def test_single_faced_card_is_implemented_when_its_name_is_registered() -> None:
    card = parse_card(fx.LLANOWAR_ELVES)
    assert not CardRegistry().is_implemented(card)
    assert CardRegistry([CardDefinition("Llanowar Elves")]).is_implemented(card)


def test_multi_faced_card_needs_every_face() -> None:
    """Multi-faced cards are registered per face (design.md §11)."""
    card = parse_card(fx.TRANSFORM_CARD)
    registry = CardRegistry([CardDefinition("Test Daybreaker")])
    assert not registry.is_implemented(card)
    assert registry.missing_faces(card) == ("Test Nightfall",)
    registry.register(CardDefinition("Test Nightfall"))
    assert registry.is_implemented(card)
    assert registry.missing_faces(card) == ()


def test_full_multi_faced_name_does_not_count_as_its_faces() -> None:
    card = parse_card(fx.SPLIT_CARD)
    registry = CardRegistry([CardDefinition("Test Spark // Test Frost")])
    assert registry.missing_faces(card) == ("Test Spark", "Test Frost")


def test_definitions_survive_deepcopy_and_pickle() -> None:
    definition = CardDefinition("Forest")
    assert copy.deepcopy(definition) == definition
    assert pickle.loads(pickle.dumps(definition)) == definition


def test_default_registry_loads_the_definitions_package() -> None:
    registry = default_registry()
    assert isinstance(registry, CardRegistry)
    assert len(registry.names()) == len(set(registry.names()))


# --- Collecting definitions from a package ------------------------------------------------------


def prepend_sys_path(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    monkeypatch.setattr(sys, "path", [str(path), *sys.path])
    importlib.invalidate_caches()


def make_package(root: Path, name: str, modules: dict[str, str]) -> None:
    package = root / name
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    for module, source in modules.items():
        (package / f"{module}.py").write_text(textwrap.dedent(source), encoding="utf-8")


def test_collects_definitions_in_sorted_module_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_package(
        tmp_path,
        "defs_sorted",
        {
            "zeta": """
                from resolve.cards.registry import CardDefinition
                DEFINITIONS = [CardDefinition("Zeta Card")]
            """,
            "alpha": """
                from resolve.cards.registry import CardDefinition
                DEFINITIONS = (CardDefinition("Alpha One"), CardDefinition("Alpha Two"))
            """,
        },
    )
    prepend_sys_path(monkeypatch, tmp_path)
    names = [d.name for d in collect_definitions("defs_sorted")]
    assert names == ["Alpha One", "Alpha Two", "Zeta Card"]


def test_module_without_definitions_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_package(tmp_path, "defs_missing", {"empty": "X = 1\n"})
    prepend_sys_path(monkeypatch, tmp_path)
    with pytest.raises(RegistryError, match="must define a DEFINITIONS sequence"):
        collect_definitions("defs_missing")


def test_definitions_must_not_be_a_string(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    make_package(tmp_path, "defs_string", {"bad": "DEFINITIONS = 'Forest'\n"})
    prepend_sys_path(monkeypatch, tmp_path)
    with pytest.raises(RegistryError, match="must define a DEFINITIONS sequence"):
        collect_definitions("defs_string")


def test_non_definition_entries_are_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_package(tmp_path, "defs_wrong_type", {"bad": "DEFINITIONS = ['Forest']\n"})
    prepend_sys_path(monkeypatch, tmp_path)
    with pytest.raises(RegistryError, match="non-CardDefinition"):
        collect_definitions("defs_wrong_type")


def test_same_card_defined_in_two_modules_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = """
        from resolve.cards.registry import CardDefinition
        DEFINITIONS = [CardDefinition("Forest")]
    """
    make_package(tmp_path, "defs_duplicate", {"a": source, "b": source})
    prepend_sys_path(monkeypatch, tmp_path)
    with pytest.raises(DuplicateDefinitionError):
        CardRegistry(collect_definitions("defs_duplicate"))


def test_every_registered_nonbasic_card_is_in_the_committed_excerpt() -> None:
    """The fuzz decks are built from ``tools/excerpts/cards.json`` (no snapshot needed), so every
    registered card but the basic lands (``basic_lands.json``) must be in it, and nothing else."""
    root = Path(__file__).resolve().parents[2] / "tools" / "excerpts"
    registry = default_registry()
    basics = {card.name for card in load_card_excerpt(root / "basic_lands.json").cards()}
    excerpt = load_card_excerpt(root / "cards.json")
    names = {name for card in excerpt.cards() for name in card.face_names}
    assert names == set(registry.names()) - basics
