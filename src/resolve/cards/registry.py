"""The card registry: which cards the engine implements, by exact name (design.md §11).

A card definition is registered under the exact Oracle name it implements. A multi-faced card is
registered per face, so it counts as implemented only when every face has a definition.

Definitions live in modules under ``resolve.cards.definitions``. Each module exposes a
``DEFINITIONS`` sequence; ``default_registry()`` collects them in sorted module order. Nothing is
registered as an import side effect, so tests can build their own registries freely.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from resolve.data.cards import CardData


@dataclass(frozen=True)
class CardDefinition:
    """How one card (or one face of a multi-faced card) behaves.

    Only the name exists so far. The fields that describe behavior (abilities, costs, static
    effects) are added with the engine primitives in later milestones. A definition is pure data
    and refers to behavior through the registry, never by storing functions (design.md §4).
    """

    name: str


class RegistryError(Exception):
    """A problem with the set of registered card definitions."""


class DuplicateDefinitionError(RegistryError):
    def __init__(self, name: str) -> None:
        super().__init__(f"card {name!r} is registered more than once")
        self.name = name


class UnimplementedCardError(RegistryError, KeyError):
    """The engine has no definition for this card (it is never approximated)."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name

    def __str__(self) -> str:
        return f"card {self.name!r} is not implemented"


class CardRegistry:
    """Card definitions by exact card (or face) name."""

    def __init__(self, definitions: Iterable[CardDefinition] = ()) -> None:
        self._definitions: dict[str, CardDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: CardDefinition) -> None:
        if definition.name in self._definitions:
            raise DuplicateDefinitionError(definition.name)
        self._definitions[definition.name] = definition

    def __len__(self) -> int:
        return len(self._definitions)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._definitions

    def get(self, name: str) -> CardDefinition:
        try:
            return self._definitions[name]
        except KeyError:
            raise UnimplementedCardError(name) from None

    def names(self) -> tuple[str, ...]:
        """All registered names, sorted."""
        return tuple(sorted(self._definitions))

    def missing_faces(self, card: CardData) -> tuple[str, ...]:
        """The faces of ``card`` that have no definition, in face order."""
        return tuple(name for name in card.face_names if name not in self._definitions)

    def is_implemented(self, card: CardData) -> bool:
        return not self.missing_faces(card)


def collect_definitions(package: str = "resolve.cards.definitions") -> list[CardDefinition]:
    """Import every module in ``package`` (sorted by name) and gather its ``DEFINITIONS``."""
    root = importlib.import_module(package)
    definitions: list[CardDefinition] = []
    module_names = sorted(info.name for info in pkgutil.iter_modules(root.__path__))
    for module_name in module_names:
        module = importlib.import_module(f"{package}.{module_name}")
        module_definitions: object = getattr(module, "DEFINITIONS", None)
        if not isinstance(module_definitions, Sequence) or isinstance(module_definitions, str):
            raise RegistryError(f"{module.__name__} must define a DEFINITIONS sequence")
        for definition in module_definitions:  # pyright: ignore[reportUnknownVariableType]
            if not isinstance(definition, CardDefinition):
                raise RegistryError(
                    f"{module.__name__}.DEFINITIONS contains a non-CardDefinition: {definition!r}"
                )
            definitions.append(definition)
    return definitions


def default_registry() -> CardRegistry:
    """A registry holding every definition in ``resolve.cards.definitions``."""
    return CardRegistry(collect_definitions())
