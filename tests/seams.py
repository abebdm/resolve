"""Typed helpers for replacing rule-default functions in seam tests (CLAUDE.md, "Rule defaults
are tested through their seam").

``monkeypatch.setattr(defaults, name, function)`` accepts anything. These wrappers give the
replacement a signature, so a lambda's parameters are typed and the replacement can't have the
wrong shape unnoticed.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from resolve.rules import defaults, legality
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.turn import Segment


def patch(
    monkeypatch: pytest.MonkeyPatch, name: str, function: Callable[[GameState, PlayerId], Any]
) -> None:
    """Replace the rule default ``defaults.<name>(state, player)``."""
    monkeypatch.setattr(defaults, name, function)


def patch_card(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    function: Callable[[GameState, PlayerId, ObjectId], Any],
) -> None:
    """Replace ``defaults.<name>(state, player, card)``."""
    monkeypatch.setattr(defaults, name, function)


def patch_object(
    monkeypatch: pytest.MonkeyPatch, name: str, function: Callable[[GameState, ObjectId], Any]
) -> None:
    """Replace ``defaults.<name>(state, obj)``."""
    monkeypatch.setattr(defaults, name, function)


def patch_skip(
    monkeypatch: pytest.MonkeyPatch, function: Callable[[GameState, Segment], bool]
) -> None:
    """Replace ``defaults.is_skipped``."""
    monkeypatch.setattr(defaults, "is_skipped", function)


def patch_loss(
    monkeypatch: pytest.MonkeyPatch,
    function: Callable[[GameState, PlayerId, defaults.LossReason], bool],
) -> None:
    """Replace ``defaults.can_lose_game``."""
    monkeypatch.setattr(defaults, "can_lose_game", function)


def patch_next_turn(
    monkeypatch: pytest.MonkeyPatch, function: Callable[[GameState, PlayerId], defaults.NextTurn]
) -> None:
    """Replace ``defaults.next_turn``."""
    monkeypatch.setattr(defaults, "next_turn", function)


def patch_permissions(
    monkeypatch: pytest.MonkeyPatch,
    function: Callable[[GameState, legality.Action], tuple[legality.Permission, ...]],
) -> None:
    """Replace ``legality.permissions``."""
    monkeypatch.setattr(legality, "permissions", function)
