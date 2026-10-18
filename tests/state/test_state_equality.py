"""State equality is complete, so the fuzz harness's ``==`` checks mean what they say.

The harness (``tools/fuzz.py``) compares states with ``==`` to check copies, resumption and
replays (design.md §5, §12). A dataclass field with ``compare=False``, or a dataclass with
``eq=False``, would hide a difference from every one of those checks, so none may exist in the
engine.
"""

from __future__ import annotations

import dataclasses
import importlib
import inspect
import pkgutil

import resolve


def engine_dataclasses() -> list[type]:
    """Every dataclass defined in the ``resolve`` package."""
    found: dict[str, type] = {}
    for info in pkgutil.walk_packages(resolve.__path__, "resolve."):
        module = importlib.import_module(info.name)
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if cls.__module__ == info.name and dataclasses.is_dataclass(cls):
                found[f"{cls.__module__}.{cls.__qualname__}"] = cls
    return [found[name] for name in sorted(found)]


def test_the_scan_finds_the_state_classes() -> None:
    names = {cls.__name__ for cls in engine_dataclasses()}
    assert {"GameState", "Player", "GameObject", "Rng", "StartGame", "ApplyEvents"} <= names


def test_every_engine_dataclass_compares_every_field() -> None:
    hidden = [
        f"{cls.__qualname__}.{field.name}"
        for cls in engine_dataclasses()
        for field in dataclasses.fields(cls)
        if not field.compare
    ]
    no_eq = [
        cls.__qualname__
        for cls in engine_dataclasses()
        if not cls.__dataclass_params__.eq  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
    ]
    assert hidden == [] and no_eq == []
