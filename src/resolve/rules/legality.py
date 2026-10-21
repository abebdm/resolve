"""Legality: whether a player may take an action (101.2, design.md §17.2).

Every legality question is an ``Action`` value. ``allowed(state, action)`` works in four steps:

1. ``permissions`` collects what allows the action: the rules' own (for playing a land, 305.1 and
   116.2a) and those effects grant.
2. At least one permission is required.
3. ``prohibitions`` collects what forbids it: the rules' own "can't" (for playing a land, the
   limit of 305.2b) and those effects impose.
4. Any applicable prohibition wins (101.2). Adding or removing abilities is not a prohibition
   (101.2a).

Only playing a land exists so far; casting, activating, targeting, countering and destroying join
it from M2.3 to M2.8, and attacking and blocking in M3. A function that asks the question calls
``legality.allowed`` through the module, so a test or an effect that replaces ``permissions`` or
``prohibitions`` is obeyed everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.data.types import CardType
from resolve.effects.characteristics import characteristics
from resolve.errors import EngineError
from resolve.rules import defaults
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.zones import Zone
from resolve.values import Immutable

if TYPE_CHECKING:
    from resolve.state.game import GameState


@dataclass(frozen=True)
class Action(Immutable):
    """Something ``player`` may or may not do (101.2); subclasses name what."""

    player: PlayerId


@dataclass(frozen=True)
class PlayLand(Action):
    """``player`` plays the land card ``card`` (305.1), a special action (116.2a)."""

    card: ObjectId


@dataclass(frozen=True)
class Permission(Immutable):
    """A rule or effect that allows an action: the CR ``rule`` and what it lets the player do."""

    rule: str
    text: str


@dataclass(frozen=True)
class Prohibition(Immutable):
    """A rule or effect that forbids an action: the CR ``rule`` and what it forbids."""

    rule: str
    text: str


@dataclass(frozen=True)
class Verdict(Immutable):
    """The answer to ``allowed``: whether the action is legal, the CR rules behind the answer and
    a sentence saying why."""

    allowed: bool
    rules: tuple[str, ...]
    reason: str


def permissions(state: GameState, action: Action) -> tuple[Permission, ...]:
    """Everything that allows ``action`` now."""
    if isinstance(action, PlayLand):
        return _land_play_permissions(state, action)
    raise EngineError(f"no rule of legality covers {action!r}")


def prohibitions(state: GameState, action: Action) -> tuple[Prohibition, ...]:
    """Everything that forbids ``action`` now."""
    if isinstance(action, PlayLand):
        return _land_play_prohibitions(state, action)
    raise EngineError(f"no rule of legality covers {action!r}")


def allowed(state: GameState, action: Action) -> Verdict:
    """Whether ``action`` is legal: a permission and no prohibition (101.2)."""
    granted = permissions(state, action)
    if not granted:
        return Verdict(False, _basis(action), "nothing allows it")
    forbidden = prohibitions(state, action)
    if forbidden:
        # 101.2: when a rule or effect allows and another prohibits, the prohibition wins.
        rules = dict.fromkeys(("101.2", *(p.rule for p in forbidden)))
        reason = "a prohibition applies: " + "; ".join(p.text for p in forbidden)
        return Verdict(False, tuple(rules), reason)
    return Verdict(True, tuple(dict.fromkeys(p.rule for p in granted)), "allowed")


def _basis(action: Action) -> tuple[str, ...]:
    """The rules that would allow ``action``, cited when nothing does."""
    if isinstance(action, PlayLand):
        return ("305.1", "116.2a")
    return ("101.2",)


def _land_play_permissions(state: GameState, action: PlayLand) -> tuple[Permission, ...]:
    # 305.1: a player who has priority may play a land card from their hand during a main phase
    # of their turn when the stack is empty (116.2a: a special action). 305.3: never during
    # another player's turn. 305.9: only a land card; a land can't be cast.
    obj = state.objects.get(action.card)
    if (
        obj is not None
        and obj.zone == Zone.hand(action.player)
        and characteristics(state, action.card).is_a(CardType.LAND)
        and defaults.has_sorcery_timing(state, action.player)
    ):
        return (Permission("305.1", "play a land from the hand in their main phase"),)
    return ()


def _land_play_prohibitions(state: GameState, action: PlayLand) -> tuple[Prohibition, ...]:
    # 305.2a-b: a player can't play a land if the lands they've played this turn (their own turn:
    # 305.3) are as many as the lands they can play this turn.
    turn = state.turn
    played = 0 if turn is None else turn.lands_played
    if played >= defaults.land_plays_allowed(state, action.player):
        return (Prohibition("305.2b", "they have played all the lands they can this turn"),)
    return ()
