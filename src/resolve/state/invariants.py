"""Checks that a game state is well-formed (design.md §4, §14).

Tests call these, and the fuzz harness (``tools/fuzz.py``) calls them before every decision.

- ``state_impurities``: anything in the state that isn't pure data. Pure data means ``None``,
  ``bool``, ``int``, ``float``, ``str``, enums, lists, tuples, dicts with ``int``/``str``/enum
  keys, and dataclass instances whose fields are pure data (and that have no other attributes).
  Functions, generators, sets, ``random.Random``, classes and open files are reported. So is a
  ``GameObject`` or ``Player`` held anywhere except ``state.objects`` or ``state.players``: tasks
  and events must store IDs, not references.
- ``mutable_parts``: anything inside a value that would break ``Immutable``'s promise. Deeply
  immutable means scalars, enums, tuples and frozen ``Immutable`` dataclasses only.
- ``invariant_violations``: zone bookkeeping and counters (400.1, 400.3, 109.4, 613.7d), and the
  turn and priority bookkeeping (500.1, 117.3, 117.4).

Each returns a list of problems, each naming where it is (``state.tasks[0].events``); empty means
fine. The ``check_*`` functions raise ``EngineError`` listing them.
"""

from __future__ import annotations

import dataclasses
from enum import Enum

from resolve.decisions.kinds import DecisionKind
from resolve.errors import EngineError
from resolve.state.game import GameObject, GameState, Player, zone_list
from resolve.state.rng import Rng
from resolve.state.turn import TURN_SEQUENCE, Step, gives_priority
from resolve.state.zones import Zone, ZoneKind
from resolve.values import Immutable

_SCALARS = (type(None), bool, int, float, str, Enum)
# Deeper than any legitimate state; stops the walk if a reference cycle ever appears.
_MAX_DEPTH = 100


def _dataclass_fields(value: object) -> list[tuple[str, object]]:
    return [(f.name, getattr(value, f.name)) for f in dataclasses.fields(value)]  # pyright: ignore[reportArgumentType]


def state_impurities(state: GameState) -> list[str]:
    """Everything in ``state`` that isn't pure data, or holds an object or player by reference."""
    problems: list[str] = []
    _walk_pure(state, "state", 0, problems)
    return problems


def _walk_pure(value: object, path: str, depth: int, problems: list[str]) -> None:
    if depth > _MAX_DEPTH:
        problems.append(f"{path}: nested too deeply (a reference cycle?)")
        return
    if isinstance(value, _SCALARS):
        return
    if isinstance(value, GameObject) and not path.startswith("state.objects["):
        problems.append(f"{path}: holds a GameObject by reference; store its ObjectId")
    if isinstance(value, Player) and not path.startswith("state.players["):
        problems.append(f"{path}: holds a Player by reference; store its PlayerId")
    if isinstance(value, list | tuple):
        items: list[object] | tuple[object, ...] = value  # pyright: ignore[reportUnknownVariableType]
        for index, item in enumerate(items):
            _walk_pure(item, f"{path}[{index}]", depth + 1, problems)
    elif isinstance(value, dict):
        mapping: dict[object, object] = value  # pyright: ignore[reportUnknownVariableType]
        for key, item in mapping.items():
            if not isinstance(key, int | str | Enum) or isinstance(key, bool):
                problems.append(f"{path}: dict key {key!r} isn't an int, str or enum")
            _walk_pure(item, f"{path}[{key!r}]", depth + 1, problems)
    elif dataclasses.is_dataclass(value) and not isinstance(value, type):
        fields = _dataclass_fields(value)
        names = [name for name, _ in fields]
        extra = sorted(name for name in getattr(value, "__dict__", {}) if name not in names)
        if extra:
            problems.append(f"{path}: attributes outside the dataclass fields: {extra}")
        for name, item in fields:
            _walk_pure(item, f"{path}.{name}", depth + 1, problems)
    else:
        problems.append(f"{path}: {type(value).__qualname__} isn't pure data")


def mutable_parts(value: object, path: str = "value") -> list[str]:
    """Everything inside ``value`` that isn't deeply immutable."""
    problems: list[str] = []
    _walk_immutable(value, path, 0, problems)
    return problems


def _walk_immutable(value: object, path: str, depth: int, problems: list[str]) -> None:
    if depth > _MAX_DEPTH:
        problems.append(f"{path}: nested too deeply (a reference cycle?)")
        return
    if isinstance(value, _SCALARS):
        return
    if isinstance(value, tuple):
        items: tuple[object, ...] = value  # pyright: ignore[reportUnknownVariableType]
        for index, item in enumerate(items):
            _walk_immutable(item, f"{path}[{index}]", depth + 1, problems)
    elif isinstance(value, Immutable):
        if not dataclasses.is_dataclass(value) or not type(value).__dataclass_params__.frozen:  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
            problems.append(f"{path}: {type(value).__qualname__} isn't a frozen dataclass")
            return
        for name, item in _dataclass_fields(value):
            _walk_immutable(item, f"{path}.{name}", depth + 1, problems)
    else:
        problems.append(f"{path}: {type(value).__qualname__} isn't immutable")


def invariant_violations(state: GameState) -> list[str]:
    """Bookkeeping errors in ``state``: zones, IDs, counters and the decision state."""
    problems: list[str] = []
    for index, player in enumerate(state.players):
        if player.id != index:
            problems.append(f"state.players[{index}] has id {player.id}")

    zones = [Zone.library(p.id) for p in state.players]
    zones += [Zone.hand(p.id) for p in state.players]
    zones += [Zone.graveyard(p.id) for p in state.players]
    zones += [Zone(kind) for kind in ZoneKind if not kind.is_per_player]
    seen: dict[int, Zone] = {}
    for zone in zones:
        for obj_id in zone_list(state, zone):
            if obj_id in seen:
                problems.append(f"object {obj_id} is listed in the {seen[obj_id]} and the {zone}")
                continue
            seen[obj_id] = zone
            obj = state.objects.get(obj_id)
            if obj is None:
                problems.append(f"the {zone} lists object {obj_id}, which doesn't exist")
            elif obj.zone != zone:
                problems.append(f"object {obj_id} is listed in the {zone} but says {obj.zone}")

    for obj_id, obj in state.objects.items():
        where = f"object {obj_id}"
        if obj.id != obj_id:
            problems.append(f"{where} is stored under the wrong key (its id is {obj.id})")
        if obj_id not in seen:
            problems.append(f"{where} isn't listed in any zone")
        if not 1 <= obj.id < state.next_object_id:
            problems.append(f"{where}: id isn't below next_object_id {state.next_object_id}")
        if not 1 <= obj.timestamp < state.next_timestamp:
            problems.append(f"{where}: timestamp isn't below next_timestamp")
        if not 0 <= obj.owner < len(state.players):
            problems.append(f"{where}: owner {obj.owner} isn't a player")
        if obj.zone.kind.is_per_player and obj.zone.owner != obj.owner:
            problems.append(f"{where} is in the {obj.zone}, not its owner's (400.3)")
        has_controller = obj.zone.kind in (ZoneKind.BATTLEFIELD, ZoneKind.STACK)
        if has_controller != (obj.controller is not None):
            problems.append(
                f"{where}: controller {obj.controller} in the {obj.zone} (108.4, 109.4)"
            )
        if obj.card is not None:
            card = state.cards.get(obj.card)
            if card is None:
                problems.append(f"{where}: card {obj.card} doesn't exist")
            elif card.owner != obj.owner:
                problems.append(f"{where}: owner {obj.owner} differs from its card's owner")
        if list(obj.known_to) != sorted(dict.fromkeys(obj.known_to)):
            problems.append(f"{where}: known_to isn't sorted and unique")
        if obj.damage < 0:
            problems.append(f"{where} has negative damage {obj.damage}")
        if obj.damage and obj.zone.kind is not ZoneKind.BATTLEFIELD:
            problems.append(f"{where} has damage in the {obj.zone}: only permanents (120.6)")
        if obj.tapped and obj.zone.kind is not ZoneKind.BATTLEFIELD:
            problems.append(f"{where} is tapped in the {obj.zone}: only permanents (110.5d)")
    for player in state.players:
        for unit in player.mana_pool:
            if unit.source is not None and not 1 <= unit.source < state.next_object_id:
                problems.append(f"player {player.id}'s mana has an unknown source {unit.source}")

    for card_id, card in state.cards.items():
        if card.id != card_id:
            problems.append(f"card {card_id} is stored under the wrong key (its id is {card.id})")

    problems += _turn_violations(state)

    if state.pending is not None and not state.tasks:
        problems.append("a decision is pending but the task stack is empty")
    if state.pending is not None and state.result is not None:
        problems.append("a decision is pending but the game is over")
    if state.pending is not None and state.pending.id >= state.next_request_id:
        problems.append("the pending request's id isn't below next_request_id")
    for index, entry in enumerate(state.event_log):
        if entry.index != index:
            problems.append(f"state.event_log[{index}] has index {entry.index}")
    if not isinstance(state.rng, Rng):  # pyright: ignore[reportUnnecessaryIsInstance]
        problems.append("state.rng isn't an Rng")
    return problems


def _turn_violations(state: GameState) -> list[str]:
    """The turn's bookkeeping (500.1, 117): a real segment, real players, consistent priority."""
    problems: list[str] = []
    turn = state.turn
    pending = state.pending
    if turn is None:
        if pending is not None and pending.kind is DecisionKind.PRIORITY_ACTION:
            problems.append("priority is asked outside a turn")
        return problems
    count = len(state.players)
    if turn.number < 1:
        problems.append(f"turn number {turn.number} isn't positive")
    if state.starting_player is None:
        problems.append("a turn is in progress but no starting player was chosen (103.1)")
    if not 0 <= turn.active_player < count:
        problems.append(f"the active player {turn.active_player} isn't a player")
    if turn.segment not in TURN_SEQUENCE:
        problems.append(f"{turn.segment} isn't a step of a turn (500.1)")
    if turn.priority is not None:
        if not 0 <= turn.priority < count:
            problems.append(f"the priority holder {turn.priority} isn't a player")
        elif state.player(turn.priority).lost:
            problems.append(f"player {turn.priority} holds priority but has left the game")
    if any(not 0 <= p < count for p in turn.passed) or len(set(turn.passed)) != len(turn.passed):
        problems.append(f"the players who passed {turn.passed} aren't distinct players")
    if turn.priority is not None and turn.priority in turn.passed:
        problems.append(f"player {turn.priority} holds priority but already passed (117.4)")
    if turn.lands_played < 0:
        problems.append("lands played this turn is negative")
    if pending is not None and pending.kind is DecisionKind.PRIORITY_ACTION:
        if turn.priority != pending.player:
            problems.append(
                f"player {pending.player} is asked for a priority action, but "
                f"{turn.priority} holds priority"
            )
        if not gives_priority(turn.step) and turn.step is not Step.CLEANUP:
            problems.append(f"priority is asked in the {turn.step} step (502.4)")
    return problems


def _raise_if(problems: list[str], what: str) -> None:
    if problems:
        raise EngineError(f"{what}:\n" + "\n".join(f"- {problem}" for problem in problems))


def check_pure_data(state: GameState) -> None:
    """Raise ``EngineError`` if ``state`` holds anything that isn't pure data."""
    _raise_if(state_impurities(state), "the game state isn't pure data")


def check_immutable(value: object) -> None:
    """Raise ``EngineError`` if ``value`` isn't deeply immutable."""
    _raise_if(mutable_parts(value), "the value isn't deeply immutable")


def check_invariants(state: GameState) -> None:
    """Raise ``EngineError`` if ``state`` breaks a bookkeeping invariant."""
    _raise_if(invariant_violations(state), "the game state is inconsistent")
