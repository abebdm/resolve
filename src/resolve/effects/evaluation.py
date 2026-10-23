"""Evaluating references and values (608.2h, 113.7a, design.md §17.9).

Every reference (``resolve.cards.primitives.refs``) and value (``resolve.cards.primitives.values``)
in a definition is resolved here, and only here, against a ``Context``: the spell or ability
whose text it is, its controller, its targets, and when the evaluation happens (``Timing``).

- **On resolution** (608.2h), each effect evaluates what it needs once, as it applies: an
  object still in the zone it was expected in gives its current information; one that has left
  gives its last known information (``GameState.last_known``). The context's targets are only
  those still legal (608.2b): an illegal target is neither affected nor a source of
  information, so a value that needs one can't be determined (``None``) and that part of the
  effect doesn't happen.
- **On announcement** (601.2b, 113.7a), for activated abilities (M4) and X (M2.7).
- **Continuously**, for static abilities (M5).

107.1b: values may be negative here; an effect that uses one as an amount uses 0 instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from resolve.cards.primitives.refs import (
    ControllerOf,
    EachCreature,
    EachOpponent,
    ObjectRef,
    PlayerRef,
    TargetRef,
    ThisObject,
    You,
)
from resolve.cards.primitives.values import Fixed, PowerOf, Value
from resolve.data.types import CardType
from resolve.effects.characteristics import characteristics
from resolve.errors import EngineError
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.last_known import LastKnown, snapshot
from resolve.state.spell import Target, TargetObject, TargetPlayer
from resolve.values import Immutable

if TYPE_CHECKING:
    from resolve.state.game import GameState


class Timing(Enum):
    """When a value is evaluated (design.md §17.9)."""

    ANNOUNCEMENT = "announcement"  # 601.2b, 113.7a
    RESOLUTION = "resolution"  # 608.2h


@dataclass(frozen=True)
class Context(Immutable):
    """What a definition's references mean now: ``obj`` is the spell (or ability) whose text is
    evaluated (``ThisObject``), ``controller`` its controller (``You``, 109.5), ``targets`` its
    targets per instance of "target" (on resolution, the legal ones only, 608.2b), ``timing``
    when."""

    timing: Timing
    obj: ObjectId
    controller: PlayerId
    targets: tuple[tuple[Target, ...], ...] = ()


def information(state: GameState, obj: ObjectId) -> LastKnown | None:
    """What is known of ``obj`` (608.2h): its current information while it exists, else its last
    known information from the battlefield or the stack; ``None`` for an object that left
    otherwise (with its owner, 800.4a)."""
    game_object = state.objects.get(obj)
    if game_object is None:
        return state.last_known.get(obj)
    return snapshot(state, game_object)


def _targets(context: Context, ref: TargetRef) -> tuple[Target, ...]:
    if ref.index >= len(context.targets):
        raise EngineError(f"the text refers to target {ref.index}, which wasn't chosen")
    return context.targets[ref.index]


def objects(state: GameState, ref: ObjectRef, context: Context) -> tuple[ObjectId, ...]:
    """The objects ``ref`` refers to: the spell itself, or the objects among its targets."""
    match ref:
        case ThisObject():
            return (context.obj,)
        case TargetRef():
            return tuple(t.object for t in _targets(context, ref) if isinstance(t, TargetObject))


def players(state: GameState, ref: PlayerRef, context: Context) -> tuple[PlayerId, ...]:
    """The players ``ref`` refers to who are still in the game (800.4a): you, the controllers of
    objects (as they last existed, 608.2h), or the players among the targets."""
    found: list[PlayerId] = []
    match ref:
        case You():
            found.append(context.controller)
        case ControllerOf(object=obj_ref):
            for obj in objects(state, obj_ref, context):
                known = information(state, obj)
                if known is not None and known.controller is not None:
                    found.append(known.controller)
        case TargetRef():
            targets = _targets(context, ref)
            found += [t.player for t in targets if isinstance(t, TargetPlayer)]
    unique = dict.fromkeys(found)
    return tuple(p for p in unique if not state.player(p).left_game)


def each_creature(state: GameState, group: EachCreature, context: Context) -> tuple[ObjectId, ...]:
    """The creatures on the battlefield now (608.2h), in battlefield order, but the exception."""
    excepted = () if group.except_ is None else objects(state, group.except_, context)
    return tuple(
        obj
        for obj in state.battlefield
        if obj not in excepted and characteristics(state, obj).is_a(CardType.CREATURE)
    )


def each_opponent(state: GameState, group: EachOpponent, context: Context) -> tuple[PlayerId, ...]:
    """The controller's opponents still in the game (102.2, 800.4a), in turn order."""
    from resolve.state.game import players_in_game

    return tuple(p for p in players_in_game(state) if p != context.controller)


def evaluate(state: GameState, value: Value, context: Context) -> int | None:
    """The number ``value`` stands for now, or ``None`` if it can't be determined (608.2b: it
    needs information about an illegal target)."""
    match value:
        case Fixed(value=number):
            return number
        case PowerOf(object=ref):
            found = objects(state, ref, context)
            if not found:
                return None
            if len(found) > 1:
                raise EngineError(f"{value!r} refers to {len(found)} objects")
            known = information(state, found[0])
            return None if known is None else known.characteristics.power
