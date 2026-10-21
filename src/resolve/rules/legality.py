"""STUB (tests first): legality, replaced by the implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.errors import NotImplementedRule
from resolve.state.ids import ObjectId, PlayerId
from resolve.values import Immutable

if TYPE_CHECKING:
    from resolve.state.game import GameState


@dataclass(frozen=True)
class Action(Immutable):
    player: PlayerId


@dataclass(frozen=True)
class PlayLand(Action):
    card: ObjectId


@dataclass(frozen=True)
class Permission(Immutable):
    rule: str
    text: str


@dataclass(frozen=True)
class Prohibition(Immutable):
    rule: str
    text: str


@dataclass(frozen=True)
class Verdict(Immutable):
    allowed: bool
    rules: tuple[str, ...]
    reason: str


def permissions(state: GameState, action: Action) -> tuple[Permission, ...]:
    raise NotImplementedRule("101.2: permissions (M2.1 stub)")


def prohibitions(state: GameState, action: Action) -> tuple[Prohibition, ...]:
    raise NotImplementedRule("101.2: prohibitions (M2.1 stub)")


def allowed(state: GameState, action: Action) -> Verdict:
    raise NotImplementedRule("101.2: allowed (M2.1 stub)")
