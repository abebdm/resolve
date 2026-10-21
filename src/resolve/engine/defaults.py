"""Rule defaults (CLAUDE.md rule 12, design.md §17.1): one function for each value or procedure a
card or effect could change.

Engine code never writes these defaults as literals; it calls the function here, which reads the
game state and cites its CR rule. Each function is the one place effects plug in, even while no
effect can modify it yet (M5 and later). Callers use ``defaults.<function>(...)`` (not a
``from`` import), so a test can replace a function with ``monkeypatch`` and check that the
engine obeys it everywhere (the seam tests, ``tests/rules/test_rule_default_seams.py``).

The procedures of the rules themselves (117.3a priority order, 101.4 APNAP order, the 103.1
chooser) are not defaults and stay where they are.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from resolve.data.types import CardType
from resolve.decisions.spaces import NamedOption
from resolve.effects.characteristics import characteristics
from resolve.errors import EngineError, NotImplementedRule
from resolve.state.game import is_multiplayer, next_in_turn_order
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import Mana
from resolve.state.turn import TURN_SEQUENCE, Segment, Step, TurnState

if TYPE_CHECKING:
    from resolve.cards.primitives.base import Ability
    from resolve.state.game import GameState

KEEP = NamedOption("keep")
MULLIGAN = NamedOption("mulligan")

# Card types of spells (301.1, 302.1, 303.1, 304.1, 306.1, 307.1, 310.1; 308.1 for kindreds).
SPELL_TYPES = (
    CardType.ARTIFACT,
    CardType.BATTLE,
    CardType.CREATURE,
    CardType.ENCHANTMENT,
    CardType.INSTANT,
    CardType.PLANESWALKER,
    CardType.SORCERY,
)


class LossReason(Enum):
    """Why a player would lose the game; the value is the state-based action's CR rule."""

    ZERO_LIFE = "704.5a"
    EMPTY_LIBRARY = "704.5b"


@dataclass(frozen=True)
class NextTurn:
    """Who takes the next turn (500.7) and the extra turns that remain after it, the next to
    be taken last."""

    player: PlayerId
    extra_turns: tuple[PlayerId, ...]
    extra: bool = False


def _turn(state: GameState) -> TurnState:
    if state.turn is None:
        raise EngineError("there is no turn in progress")
    return state.turn


# --- playing lands and casting (305, 117.1a) -------------------------------------------------


def land_plays_allowed(state: GameState, player: PlayerId) -> int:
    """How many lands ``player`` can play this turn (305.2): one. Continuous effects may
    increase this number (305.2); 305.2a-b compare it with the lands already played."""
    return 1


def has_sorcery_timing(state: GameState, player: PlayerId) -> bool:
    """Whether ``player`` has sorcery timing (117.1a, 307.1): it is their turn, a main phase
    and the stack is empty."""
    turn = state.turn
    return (
        turn is not None and player == turn.active_player and turn.in_main_phase and not state.stack
    )


def land_play_options(state: GameState, player: PlayerId) -> tuple[ObjectId, ...]:
    """The land cards ``player`` may play now, by zone and timing (305.1, 116.2a): lands in
    their hand, with sorcery timing. The number of land plays (305.2) is checked by
    ``legality.allowed``; effects that let a player play lands from other zones add them here.
    """
    if not has_sorcery_timing(state, player):
        return ()
    return tuple(
        obj
        for obj in state.player(player).hand
        if CardType.LAND in characteristics(state, obj).card_types
    )


def may_cast_now(state: GameState, player: PlayerId, obj: ObjectId) -> bool:
    """Whether ``player`` may cast the card ``obj`` at this time (117.1a): an instant whenever
    they have priority (304.1), any other spell only with sorcery timing (301.1, 302.1, 307.1,
    ...). Flash (702.8, M2.8) and other timing permissions plug in here. A land is never cast
    (305.9)."""
    types = characteristics(state, obj).card_types
    if CardType.LAND in types or not any(card_type in SPELL_TYPES for card_type in types):
        return False
    return CardType.INSTANT in types or has_sorcery_timing(state, player)


# --- the turn (402.2, 500, 502.3, 504.1) -----------------------------------------------------


def maximum_hand_size(state: GameState, player: PlayerId) -> int | None:
    """``player``'s maximum hand size (402.2): seven; ``None`` means no maximum."""
    return 7


def draw_step_draws(state: GameState, player: PlayerId) -> int:
    """How many cards the active player draws in their draw step (504.1): one."""
    return 1


def turn_structure(state: GameState, player: PlayerId) -> tuple[Segment, ...]:
    """The segments of ``player``'s turn, in order (500.1): the five phases and their steps.

    The turn in progress keeps what remains as data (``TurnState.segments``), so effects can
    insert phases and steps (500.8-500.10) or end the turn (724).
    """
    return TURN_SEQUENCE


def is_skipped(state: GameState, segment: Segment) -> bool:
    """Whether the turn in progress skips this step or phase (500.11).

    - 103.8a: in a two-player game, the starting player skips the draw step of their first turn
      (103.8c: nobody does in a game that began with more than two players).
    - 508.8: with no attackers declared, the declare blockers and combat damage steps are
      skipped. No creature can be declared as an attacker yet (508.1 raises
      ``NotImplementedRule`` whenever the active player controls a creature).
    """
    _, step = segment
    if step is Step.DRAW:
        return _turn(state).number == 1 and not is_multiplayer(state)
    return step in (Step.DECLARE_BLOCKERS, Step.COMBAT_DAMAGE)


def next_turn(state: GameState) -> NextTurn:
    """Who takes the turn after the one in progress (103.1, 500.7, 800.4k).

    Extra turns come first, the last one created first (500.7); one for a player who has left
    the game is not taken (800.4k). Otherwise it is the player after the last regular turn's
    player in turn order (103.1, 500.7), which ``GameState.turn_direction`` can reverse.
    """
    remaining = list(state.extra_turns)
    while remaining:
        candidate = remaining.pop()
        if not state.player(candidate).left_game:
            return NextTurn(candidate, tuple(remaining), extra=True)
    # 500.7: an extra turn doesn't change turn order; the regular turns go on from the last one.
    last = state.regular_turn_player
    after = _turn(state).active_player if last is None else last
    return NextTurn(next_in_turn_order(state, after), ())


def permanents_that_untap(state: GameState, player: PlayerId) -> tuple[ObjectId, ...]:
    """The permanents ``player`` untaps in their untap step (502.3): all they control, in
    battlefield order. "Doesn't untap" effects (M4, M5) remove permanents here."""
    return tuple(obj for obj in state.battlefield if state.objects[obj].controller == player)


def mana_that_empties(state: GameState, player: PlayerId) -> tuple[Mana, ...]:
    """The mana in ``player``'s pool that empties as a step or phase ends (500.5, 106.4): all of
    it. Effects that keep mana (M5) remove units here."""
    return tuple(state.player(player).mana_pool)


# --- ending the game (104.3), the start of the game (103) -------------------------------------


def can_lose_game(state: GameState, player: PlayerId, reason: LossReason) -> bool:
    """Whether ``player`` can lose the game for ``reason`` (104.3): yes. A player who can't
    lose stays in (Platinum Angel, M5; Laboratory Maniac, M6). Conceding (104.3a) is always
    possible."""
    return True


def opening_hand_actions(state: GameState, player: PlayerId) -> tuple[ObjectId, ...]:
    """The cards in ``player``'s opening hand that let them take an action before the game
    begins (103.6): none. A non-empty result is a rules gap until M5 (Leylines) and M9."""
    return ()


def mulligan_options(state: GameState, player: PlayerId) -> tuple[NamedOption, ...]:
    """What ``player`` may declare about their opening hand (103.5): keep it or mulligan."""
    return (KEEP, MULLIGAN)


def starting_life(state: GameState, player: PlayerId) -> int:
    """``player``'s starting life total (103.4, 103.4c): the game's setting."""
    return state.config.starting_life


def starting_hand_size(state: GameState, player: PlayerId) -> int:
    """The number of cards in ``player``'s opening hand (103.5): the game's setting."""
    return state.config.starting_hand_size


def commander_damage_threshold(state: GameState, player: PlayerId) -> int | None:
    """The combat damage from a single commander that makes ``player`` lose (903.10a): the
    game's setting; ``None`` outside a Commander game."""
    commander = state.config.commander
    return None if commander is None else commander.damage_threshold


# --- costs and abilities (302.6, 702) ---------------------------------------------------------


def can_tap_for_cost(state: GameState, obj: ObjectId) -> bool:
    """Whether the permanent ``obj`` may be tapped to pay a cost (302.6, 602.5a): a creature's
    {T} ability needs it to have been controlled continuously since its controller's most
    recent turn began. That isn't tracked until M2.4, so a creature raises
    ``NotImplementedRule``."""
    if characteristics(state, obj).is_a(CardType.CREATURE):
        raise NotImplementedRule("302.6: the {T} abilities of creatures (summoning sickness)")
    return True


def player_abilities(state: GameState, player: PlayerId) -> tuple[Ability, ...]:
    """The abilities ``player`` has (702.11c, 702.18a: a player with hexproof or shroud): none.
    Effects that give a player an ability add it here."""
    return ()


# --- who decides and who sees (723) -------------------------------------------------------------


def deciding_player(state: GameState, player: PlayerId) -> PlayerId:
    """The player who makes ``player``'s decisions (723.5, 723.8, 723.9): ``player`` themselves.
    An effect that lets another player control them (Mindslaver, M9) names that player here."""
    return player
