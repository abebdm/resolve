"""Legality: one check for every "may a player do this?" question (101.2, design.md §17.2).

Every legality question is an ``Action`` value; so far only ``PlayLandAction``. ``allowed``
works in four steps:

1. it collects the **permissions**: the rules' own (117.1a, 305.1, 601.3, 903.8) and those
   granted by effects;
2. it requires at least one;
3. it collects the **prohibitions** (305.1, 305.2b, 305.3; later hexproof, shroud, protection,
   "can't be countered", and static abilities);
4. any applicable prohibition wins (101.2). Adding or removing abilities is not a prohibition
   (101.2a).

Casting, targeting, countering and destroying join in M2.3 to M2.8; attacking and blocking in
M3; activation and special actions in M4.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.engine import defaults
from resolve.errors import EngineError
from resolve.state.ids import ObjectId, PlayerId
from resolve.values import Immutable

if TYPE_CHECKING:
    from resolve.state.game import GameState


@dataclass(frozen=True)
class PlayLandAction(Immutable):
    """``player`` plays the land card ``card`` as a special action (305.1, 116.2a)."""

    player: PlayerId
    card: ObjectId


Action = PlayLandAction


@dataclass(frozen=True)
class Ground(Immutable):
    """One permission or one prohibition: why, and the CR rules behind it."""

    rules: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class Verdict(Immutable):
    """The answer of ``allowed``: whether the action is legal, and the reasons and rules that
    decided it (the permissions that allow it, or the prohibitions that forbid it)."""

    ok: bool
    reasons: tuple[str, ...]
    rules: tuple[str, ...]


def permissions(state: GameState, action: Action) -> tuple[Ground, ...]:
    """What lets the action's player do it now (101.2): the rules' own permissions and the
    ones effects grant."""
    match action:
        case PlayLandAction(player=player, card=card):
            if card in defaults.land_play_options(state, player):
                return (
                    Ground(
                        ("305.1", "116.2a"),
                        "a land card in a zone the player may play lands from, at a time they may",
                    ),
                )
            return ()
    raise EngineError(f"{action!r} isn't a legality question")


def prohibitions(state: GameState, action: Action) -> tuple[Ground, ...]:
    """What forbids the action now (101.2): "can't" rules and effects."""
    match action:
        case PlayLandAction(player=player):
            turn = state.turn
            found: list[Ground] = []
            if turn is None:
                return ()
            if player != turn.active_player:
                # 305.3: a player can't play a land, for any reason, during another player's turn.
                found.append(Ground(("305.3",), "it isn't the player's turn"))
            elif not turn.in_main_phase or state.stack:
                # 305.1, 116.2a: only during a main phase of their turn with an empty stack.
                found.append(Ground(("305.1", "116.2a"), "not a main phase with an empty stack"))
            if player == turn.active_player and turn.lands_played >= defaults.land_plays_allowed(
                state, player
            ):
                # 305.2b: a player can't play a land, for any reason, once the lands they have
                # played reach the number they can play.
                found.append(Ground(("305.2b",), "the player has played all the lands they can"))
            return tuple(found)
    raise EngineError(f"{action!r} isn't a legality question")


def allowed(state: GameState, action: Action) -> Verdict:
    """Whether the action is legal now, and why (101.2): at least one permission and no
    prohibition. A prohibition wins over every permission."""
    granted = permissions(state, action)
    forbidden = prohibitions(state, action)
    if forbidden:
        return Verdict(False, _reasons(forbidden), _rules(forbidden))
    if not granted:
        return Verdict(False, ("no rule or effect lets the player play this land now",), ())
    return Verdict(True, _reasons(granted), _rules(granted))


def _reasons(grounds: tuple[Ground, ...]) -> tuple[str, ...]:
    return tuple(ground.reason for ground in grounds)


def _rules(grounds: tuple[Ground, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(rule for ground in grounds for rule in ground.rules))
