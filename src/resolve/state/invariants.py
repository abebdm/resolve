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
from resolve.state.checkpoint import Checkpoint
from resolve.state.game import GameObject, GameState, Player, zone_list
from resolve.state.rng import Rng
from resolve.state.turn import TURN_SEQUENCE, Step, gives_priority
from resolve.state.zones import Zone, ZoneKind
from resolve.values import Immutable

_SCALARS = (type(None), bool, int, float, str, Enum)
# Deeper than any legitimate state; stops the walk if a reference cycle ever appears.
_MAX_DEPTH = 100


# A path into a value, built only when a problem is reported: the walks below visit every node of
# the state, event log included, before every fuzz decision, and formatting a path string for
# each node was most of their cost. A path is the root's name, or (parent, separator, key).
type _Path = str | tuple[_Path, str, object]

# Field names per dataclass type; ``dataclasses.fields`` is slow to call for every node.
_FIELD_NAMES: dict[type, tuple[str, ...]] = {}


def _field_names(cls: type) -> tuple[str, ...]:
    names = _FIELD_NAMES.get(cls)
    if names is None:
        names = tuple(field.name for field in dataclasses.fields(cls))
        _FIELD_NAMES[cls] = names
    return names


def _render(path: _Path) -> str:
    parts: list[str] = []
    while isinstance(path, tuple):
        path, separator, key = path
        parts.append(f"[{key!r}]" if separator == "[r" else f"{separator}{key}")
        if separator == "[":
            parts[-1] += "]"
    parts.append(path)
    return "".join(reversed(parts))


def state_impurities(state: GameState, *, log_from: int = 0) -> list[str]:
    """Everything in ``state`` that isn't pure data, or holds an object or player by reference.

    With ``log_from``, the event log's entries before that index aren't walked: the caller
    (the fuzz harness) has checked them already and checks they haven't changed since.
    """
    problems: list[str] = []
    _walk_pure(state, "state", 0, problems, None, log_from)
    return problems


def _walk_pure(
    value: object,
    path: _Path,
    depth: int,
    problems: list[str],
    allowed: type | None,
    log_from: int = 0,
) -> None:
    # ``allowed``: GameObject inside ``state.objects``, Player inside ``state.players``.
    if depth > _MAX_DEPTH:
        problems.append(f"{_render(path)}: nested too deeply (a reference cycle?)")
        return
    if isinstance(value, _SCALARS):
        return
    if isinstance(value, GameObject) and allowed is not GameObject:
        problems.append(f"{_render(path)}: holds a GameObject by reference; store its ObjectId")
    if isinstance(value, Player) and allowed is not Player:
        problems.append(f"{_render(path)}: holds a Player by reference; store its PlayerId")
    if isinstance(value, list | tuple):
        items: list[object] | tuple[object, ...] = value  # pyright: ignore[reportUnknownVariableType]
        for index, item in enumerate(items):
            _walk_pure(item, (path, "[", index), depth + 1, problems, allowed)
    elif isinstance(value, dict):
        mapping: dict[object, object] = value  # pyright: ignore[reportUnknownVariableType]
        for key, item in mapping.items():
            if not isinstance(key, int | str | Enum) or isinstance(key, bool):
                problems.append(f"{_render(path)}: dict key {key!r} isn't an int, str or enum")
            _walk_pure(item, (path, "[r", key), depth + 1, problems, allowed)
    elif dataclasses.is_dataclass(value) and not isinstance(value, type):
        names = _field_names(type(value))
        attributes = getattr(value, "__dict__", None)
        if attributes is not None and attributes.keys() - names:
            extra = sorted(name for name in attributes if name not in names)
            if extra:
                problems.append(
                    f"{_render(path)}: attributes outside the dataclass fields: {extra}"
                )
        for name in names:
            inner = allowed
            item = getattr(value, name)
            if depth == 0 and isinstance(value, GameState):
                inner = {"objects": GameObject, "players": Player}.get(name)
            if isinstance(value, Checkpoint) and name == "values":
                # A checkpoint holds copies of the state's objects and players (733.1).
                _walk_checkpoint(item, (path, ".", name), depth + 1, problems)
                continue
                if name == "event_log" and log_from and isinstance(item, list):
                    log: list[object] = item  # pyright: ignore[reportUnknownVariableType]
                    for index in range(log_from, len(log)):
                        where = ((path, ".", name), "[", index)
                        _walk_pure(log[index], where, depth + 2, problems, inner)
                    continue
            _walk_pure(item, (path, ".", name), depth + 1, problems, inner)
    else:
        problems.append(f"{_render(path)}: {type(value).__qualname__} isn't pure data")


def _walk_checkpoint(values: object, path: _Path, depth: int, problems: list[str]) -> None:
    if not isinstance(values, dict):
        problems.append(f"{_render(path)}: a checkpoint's values aren't a dict")
        return
    mapping: dict[object, object] = values  # pyright: ignore[reportUnknownVariableType]
    for key, item in mapping.items():
        inner = (
            {"objects": GameObject, "players": Player}.get(key) if isinstance(key, str) else None
        )
        _walk_pure(item, (path, "[r", key), depth + 1, problems, inner)


def mutable_parts(value: object, path: str = "value") -> list[str]:
    """Everything inside ``value`` that isn't deeply immutable."""
    problems: list[str] = []
    _walk_immutable(value, path, 0, problems)
    return problems


def _walk_immutable(value: object, path: _Path, depth: int, problems: list[str]) -> None:
    if depth > _MAX_DEPTH:
        problems.append(f"{_render(path)}: nested too deeply (a reference cycle?)")
        return
    if isinstance(value, _SCALARS):
        return
    if isinstance(value, tuple):
        items: tuple[object, ...] = value  # pyright: ignore[reportUnknownVariableType]
        for index, item in enumerate(items):
            _walk_immutable(item, (path, "[", index), depth + 1, problems)
    elif isinstance(value, Immutable):
        cls = type(value)
        if not dataclasses.is_dataclass(value) or not cls.__dataclass_params__.frozen:  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
            problems.append(f"{_render(path)}: {cls.__qualname__} isn't a frozen dataclass")
            return
        for name in _field_names(cls):
            _walk_immutable(getattr(value, name), (path, ".", name), depth + 1, problems)
    else:
        problems.append(f"{_render(path)}: {type(value).__qualname__} isn't immutable")


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
        if player.left_game:
            if any(obj.owner == player.id for obj in state.objects.values()):
                problems.append(f"player {player.id} left the game but owns objects (800.4a)")
            if player.mana_pool:
                problems.append(f"player {player.id} left the game but has mana")
            if state.pending is not None and player.id in (
                state.pending.player,
                state.pending.for_player,
            ):
                problems.append(f"player {player.id} left the game but is asked a decision")
        if player.left_game and not player.lost and state.result is None:
            problems.append(f"player {player.id} left a game in progress without losing")
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
        elif state.player(turn.priority).left_game:
            problems.append(f"player {turn.priority} holds priority but has left the game")
    if any(not 0 <= p < count for p in turn.passed) or len(set(turn.passed)) != len(turn.passed):
        problems.append(f"the players who passed {turn.passed} aren't distinct players")
    if turn.priority is not None and turn.priority in turn.passed:
        problems.append(f"player {turn.priority} holds priority but already passed (117.4)")
    if turn.lands_played < 0:
        problems.append("lands played this turn is negative")
    for segment in turn.segments:
        if segment not in TURN_SEQUENCE:
            problems.append(f"{segment} isn't a step of a turn (500.1)")
    if any(not 0 <= p < count for p in state.extra_turns):
        problems.append(f"the extra turns {state.extra_turns} aren't players' turns (500.7)")
    if state.turn_direction not in (1, -1):
        problems.append(f"turn order's direction {state.turn_direction} isn't 1 or -1 (103.1)")
    if pending is not None and pending.kind is DecisionKind.PRIORITY_ACTION:
        if turn.priority != pending.for_player:
            problems.append(
                f"player {pending.for_player} is asked for a priority action, but "
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
