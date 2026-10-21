"""STUB (tests first): the rule-default functions of M2.1; replaced by the implementation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from resolve.decisions.spaces import NamedOption
from resolve.errors import NotImplementedRule
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import Mana
from resolve.state.turn import Segment
from resolve.values import Immutable

if TYPE_CHECKING:
    from resolve.cards.primitives.base import Ability
    from resolve.state.game import GameObject, GameState

KEEP = NamedOption("keep")
MULLIGAN = NamedOption("mulligan")


def _unbuilt(name: str) -> NotImplementedRule:
    return NotImplementedRule(f"101.2: {name} (M2.1 stub)")


class LossReason(Enum):
    LIFE_TOTAL = "life total"
    EMPTY_LIBRARY = "empty library"


@dataclass(frozen=True)
class NextTurn(Immutable):
    player: PlayerId
    extra: bool


def land_plays_allowed(state: GameState, player: PlayerId) -> int:
    raise _unbuilt("land_plays_allowed")


def land_play_options(state: GameState, player: PlayerId) -> tuple[ObjectId, ...]:
    raise _unbuilt("land_play_options")


def cast_options(state: GameState, player: PlayerId) -> tuple[ObjectId, ...]:
    raise _unbuilt("cast_options")


def has_sorcery_timing(state: GameState, player: PlayerId) -> bool:
    raise _unbuilt("has_sorcery_timing")


def may_cast_now(state: GameState, player: PlayerId, obj: ObjectId) -> bool:
    raise _unbuilt("may_cast_now")


def maximum_hand_size(state: GameState, player: PlayerId) -> int | None:
    raise _unbuilt("maximum_hand_size")


def draw_step_draws(state: GameState, player: PlayerId) -> int:
    raise _unbuilt("draw_step_draws")


def turn_structure(state: GameState, player: PlayerId) -> tuple[Segment, ...]:
    raise _unbuilt("turn_structure")


def is_skipped(state: GameState, segment: Segment) -> bool:
    raise _unbuilt("is_skipped")


def next_turn(state: GameState, after: PlayerId) -> NextTurn:
    raise _unbuilt("next_turn")


def permanents_that_untap(state: GameState, player: PlayerId) -> tuple[ObjectId, ...]:
    raise _unbuilt("permanents_that_untap")


def mana_that_empties(state: GameState, player: PlayerId) -> tuple[Mana, ...]:
    raise _unbuilt("mana_that_empties")


def can_lose_game(state: GameState, player: PlayerId, reason: LossReason) -> bool:
    raise _unbuilt("can_lose_game")


def deciding_player(state: GameState, player: PlayerId) -> PlayerId:
    raise _unbuilt("deciding_player")


def knows_identity(state: GameState, obj: GameObject, viewer: PlayerId) -> bool:
    raise _unbuilt("knows_identity")


def can_tap_for_cost(state: GameState, obj: ObjectId) -> bool:
    raise _unbuilt("can_tap_for_cost")


def player_abilities(state: GameState, player: PlayerId) -> tuple[Ability, ...]:
    raise _unbuilt("player_abilities")


def opening_hand_actions(state: GameState, player: PlayerId) -> tuple[ObjectId, ...]:
    raise _unbuilt("opening_hand_actions")


def mulligan_options(state: GameState, player: PlayerId) -> tuple[NamedOption, ...]:
    raise _unbuilt("mulligan_options")


def starting_life(state: GameState, player: PlayerId) -> int:
    raise _unbuilt("starting_life")


def starting_hand_size(state: GameState, player: PlayerId) -> int:
    raise _unbuilt("starting_hand_size")


def commander_damage_threshold(state: GameState) -> int:
    raise _unbuilt("commander_damage_threshold")
