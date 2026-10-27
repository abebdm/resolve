"""Rule defaults: the values and procedures the CR gives by default and effects can change.

CLAUDE.md rule 12 forbids writing such a default as a literal in engine code. Each one comes from
one function here that reads the game state, cites its rule and is the single place effects plug
into (design.md §17.1), even while nothing can change it yet. Engine code calls them through the
module (``defaults.maximum_hand_size(state, player)``), never ``from ... import``, so a test (or
an effect) that replaces a function is obeyed everywhere.

The functions and their defaults:

| Function                         | CR                   | Default                              |
|----------------------------------|----------------------|--------------------------------------|
| ``land_plays_allowed``           | 305.2                | one land per turn                    |
| ``land_play_options``            | 305.1                | lands in the hand, sorcery timing    |
| ``cast_permissions``             | 601.3, 903.8         | from the hand; commanders            |
| ``cast_options``                 | 601.3, 117.1a        | each permission and layout variant   |
| ``has_sorcery_timing``           | 117.1a, 307.1        | own main phase, empty stack          |
| ``may_cast_now``                 | 117.1a, 702.8a       | instants and flash any time, others  |
|                                  |                      | sorcery                              |
| ``resolved_spell_destination``   | 608.2n               | the owner's graveyard                |
| ``maximum_hand_size``            | 402.2                | seven                                |
| ``draw_step_draws``              | 504.1                | one card                             |
| ``turn_structure``               | 500.1                | the twelve segments of a turn        |
| ``is_skipped``                   | 500.11               | 103.8a and 508.8                     |
| ``next_turn``                    | 500.7, 103.1         | extra turns, then clockwise          |
| ``permanents_that_untap``        | 502.3                | all the player's permanents          |
| ``mana_that_empties``            | 500.5                | all unspent mana                     |
| ``can_lose_game``                | 104.3                | yes                                  |
| ``deciding_player``              | 723.5                | the player themselves                |
| ``knows_identity``               | 400.2, 402.3, 723.4  | zones, owners and controllers        |
| ``can_tap_for_cost``             | 302.6                | the summoning-sickness rule          |
| ``player_abilities``             | 702.11c, 702.18a     | none                                 |
| ``opening_hand_actions``         | 103.6                | none                                 |
| ``mulligan_options``             | 103.5                | keep, mulligan                       |
| ``starting_life`` and others     | 103.4, 103.5, 903.10a| the game's configuration             |
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from resolve.data.types import CardType
from resolve.decisions.spaces import CastSpellOption, NamedOption
from resolve.effects.characteristics import characteristics, is_omen, variant_characteristics
from resolve.errors import EngineError, NotImplementedRule
from resolve.state.game import is_multiplayer, next_in_turn_order
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import Mana
from resolve.state.spell import (
    COMMANDER,
    FROM_HAND,
    NORMAL,
    Alternative,
    AlternativeKind,
    Back,
    CastPermission,
    CastTiming,
    CastVariant,
    Half,
)
from resolve.state.turn import TURN_SEQUENCE, Segment, Step
from resolve.state.zones import Zone, ZoneKind
from resolve.values import Immutable

if TYPE_CHECKING:
    from resolve.cards.primitives.base import Ability
    from resolve.state.game import GameObject, GameState

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
    """Why a player would lose the game, for ``can_lose_game`` (104.3). Conceding (104.3a) isn't
    one: nothing stops a player from conceding."""

    LIFE_TOTAL = "life total"  # 704.5a, 104.3b
    EMPTY_LIBRARY = "empty library"  # 704.5b, 104.3c


@dataclass(frozen=True)
class NextTurn(Immutable):
    """Whose turn comes next, and whether it is an extra turn that ``GameState.extra_turns``
    holds (500.7) rather than the next turn in turn order."""

    player: PlayerId
    extra: bool


# --- Lands and casting ------------------------------------------------------------------------


def land_plays_allowed(state: GameState, player: PlayerId) -> int:
    """How many lands ``player`` can play this turn (305.2): normally one.

    305.2a-b compare it with the lands they have played already (``TurnState.lands_played``).
    Explore and Wayward Swordtooth change it (M5).
    """
    return 1


def land_play_options(state: GameState, player: PlayerId) -> tuple[ObjectId, ...]:
    """The lands ``player`` may play now, in hand order (305.1, 116.2a).

    A land card in the hand, which ``legality.allowed`` permits. Playing lands from other zones
    ("play lands from the top of your library", M5) adds candidates here.
    """
    from resolve.rules import legality

    options: list[ObjectId] = []
    for obj in state.player(player).hand:
        if (
            characteristics(state, obj).is_a(CardType.LAND)
            and legality.allowed(state, legality.PlayLand(player, obj)).allowed
        ):
            options.append(obj)
    return tuple(options)


def cast_permissions(
    state: GameState, player: PlayerId, obj: ObjectId
) -> tuple[CastPermission, ...]:
    """The rules' permissions for ``player`` to cast the card ``obj`` from where it is (601.3):
    from their hand (``FROM_HAND``; 601.2a), and a commander they own from the command zone
    (``COMMANDER``; 903.8). Effects that allow casting from other zones (M2.10, M4) add theirs.

    A spell whose proposal is being checked (601.2e) is judged from the zone it was cast from.
    """
    game_object = state.objects[obj]
    zone = game_object.zone if game_object.spell is None else game_object.spell.cast_from
    if game_object.owner != player:
        return ()
    if zone == Zone.hand(player):
        return (FROM_HAND,)
    if zone.kind is ZoneKind.COMMAND and game_object.card in state.player(player).commanders:
        return (COMMANDER,)
    return ()


def cast_options(state: GameState, player: PlayerId) -> tuple[CastSpellOption, ...]:
    """The spells ``player`` may begin to cast now (601.3, 117.1a): for each card in any zone but
    the stack and the battlefield (their hand first in hand order, then the command zone, the
    graveyards, exile and the libraries, top first, then the other players' hands), every
    permission ``cast_permissions`` gives (by default, the hand and their commanders, 903.8) and
    every variant (601.3e) that ``legality.allowed`` permits. ``cast_permissions`` alone decides
    which zones count.

    The variants come from the card's layout: a half of a split card (709.3), either face of a
    modal double-faced card (712.11b), an omen's normal part or its Omen (720.3), an adventurer
    or its Adventure (715.3); every other card is cast normally. Each is checked on its own
    characteristics (601.3e). The cost isn't checked: an unpayable cast is reversed (733). A
    spell that couldn't choose a legal target for every instance of the word "target" isn't
    offered (601.2c, ``targeting.can_choose_targets``): casting it could only be reversed.
    """
    from resolve.rules import legality, targeting

    candidates = [*state.player(player).hand, *state.command]
    for other in state.players:
        candidates += [*reversed(other.graveyard)]
    candidates += state.exile
    for other in state.players:
        candidates += [*reversed(other.library)]
    candidates += [obj for p in state.players if p.id != player for obj in p.hand]
    options: list[CastSpellOption] = []
    for obj in candidates:
        for permission in cast_permissions(state, player, obj):
            for variant in _layout_variants(state, obj):
                action = legality.CastAction(player, obj, variant, permission)
                if legality.allowed(state, action).allowed and targeting.can_choose_targets(
                    state, player, obj, variant
                ):
                    options.append(CastSpellOption(obj, variant, permission))
    return tuple(options)


def _layout_variants(state: GameState, obj: ObjectId) -> tuple[CastVariant, ...]:
    """The ways the card's layout lets it be cast (709.3, 712.11, 715.3, 720.3, 722.3)."""
    data = state.card_of(state.objects[obj]).data
    if data.layout == "split":
        return (Half(0), Half(1))  # 709.3: a half is chosen; fuse (702.102) is M9
    if data.layout == "modal_dfc":
        return (NORMAL, Back())  # 712.11b
    if is_omen(data) and data.is_multi_faced:
        return (NORMAL, Alternative(AlternativeKind.OMEN))  # 720.3
    if data.layout == "adventure" and data.is_multi_faced:
        return (NORMAL, Alternative(AlternativeKind.ADVENTURE))  # 715.3
    # 712.11: a transforming double-faced card is cast front face up; 722.3: a preparation card
    # can't be cast with its inset characteristics.
    return (NORMAL,)


def has_sorcery_timing(
    state: GameState, player: PlayerId, ignoring: ObjectId | None = None
) -> bool:
    """Whether ``player`` has sorcery timing (117.1a, 307.1, 116.2a): it is their own turn, a main
    phase, and the stack is empty. Flash (702.8) and effects that allow actions at other times
    change what can be done without it, not this question.

    ``ignoring`` is a spell whose own proposal is being checked (601.2e): it doesn't count as being
    on the stack.
    """
    turn = state.turn
    stack = [obj for obj in state.stack if obj != ignoring]
    return turn is not None and player == turn.active_player and turn.in_main_phase and not stack


def may_cast_now(
    state: GameState,
    player: PlayerId,
    obj: ObjectId,
    variant: CastVariant = NORMAL,
    permission: CastPermission = FROM_HAND,
) -> bool:
    """Whether the card ``obj`` may be cast as ``variant`` under ``permission`` at this time
    (117.1a): judged on the variant's characteristics (601.3e). With the normal timing, an instant
    whenever the player has priority (304.1), any other spell only with sorcery timing (301.1,
    302.1, 307.1).

    A land is never cast (305.9). A card with flash may be cast any time an instant could
    (702.8a), from whatever zone a permission allows; its flash is read from the variant's
    characteristics, so a granted flash (M5) counts too. "As though it had flash" (601.3b, M6)
    and "during this resolution" (608.2g, M2.10) are permissions' timings.
    """
    from resolve.cards.keywords import Flash, has_keyword

    chars = variant_characteristics(state, obj, variant)
    types = chars.card_types
    if CardType.LAND in types or not any(card_type in SPELL_TYPES for card_type in types):
        return False
    match permission.timing:
        case CastTiming.NORMAL:
            # 601.2e: a spell whose proposal is checked again doesn't stand in its own way.
            proposed = obj if state.objects[obj].spell is not None else None
            if CardType.INSTANT in types or has_keyword(chars, Flash):  # 304.1, 702.8a
                return True
            if proposed is None:
                return has_sorcery_timing(state, player)
            return has_sorcery_timing(state, player, ignoring=proposed)
        case CastTiming.AS_THOUGH_FLASH:
            raise NotImplementedRule("601.3b: casting a spell as though it had flash")
        case CastTiming.DURING_RESOLUTION:
            raise NotImplementedRule("608.2g: casting a spell during a resolution")


def resolved_spell_destination(state: GameState, spell: ObjectId) -> Zone:
    """Where an instant or sorcery spell goes as the final part of its resolution (608.2n): its
    owner's graveyard.

    Adventures (715.3d), Omens (720.3d) and buyback (702.27a) change it; each applies only as the
    spell resolves. A countered spell (701.6a) and one that doesn't resolve (608.2b) always go to
    their owner's graveyard and don't come here; replacement effects (Rest in Peace, flashback's
    exile: M6) change those zone changes in the event pipeline.
    """
    return Zone.graveyard(state.object(spell).owner)


# --- The turn ----------------------------------------------------------------------------------


def maximum_hand_size(state: GameState, player: PlayerId) -> int | None:
    """``player``'s maximum hand size (402.2, 514.1): seven. ``None`` means no maximum
    (Reliquary Tower, M5)."""
    return 7


def draw_step_draws(state: GameState, player: PlayerId) -> int:
    """How many cards the active player draws in their draw step (504.1): one."""
    return 1


def turn_structure(state: GameState, player: PlayerId) -> tuple[Segment, ...]:
    """The phases and steps of ``player``'s turn as it begins (500.1): the twelve segments of
    ``TURN_SEQUENCE``. The turn keeps what remains as data (``TurnState.segments``), so effects
    can add phases and steps during the turn (500.8-500.10)."""
    return TURN_SEQUENCE


def is_skipped(state: GameState, segment: Segment) -> bool:
    """Whether ``segment`` is skipped this turn, so it doesn't begin (500.11).

    - 103.8a: the starting player skips the draw step of their first turn in a two-player game;
      103.8c: in a game that began with more players nobody does.
    - 508.8: with no attackers declared, the declare blockers and combat damage steps are
      skipped. No creature can be declared as an attacker yet (508.1 is a gap when the active
      player controls a creature), so they are always skipped.
    """
    _, step = segment
    if step is Step.DRAW:
        turn = state.turn
        return turn is not None and turn.number == 1 and not is_multiplayer(state)
    return step in (Step.DECLARE_BLOCKERS, Step.COMBAT_DAMAGE)


def next_turn(state: GameState, after: PlayerId) -> NextTurn:
    """Whose turn follows the turn of ``after``, the player whose regular turn it is (500.7).

    Extra turns come first, the most recently created one first (500.7). Otherwise the next
    player in turn order (103.1) among those still in the game; a player who left the game
    doesn't begin a turn (800.4k).
    """
    if state.extra_turns:
        return NextTurn(state.extra_turns[-1], extra=True)
    return NextTurn(next_in_turn_order(state, after), extra=False)


def permanents_that_untap(state: GameState, player: PlayerId) -> tuple[ObjectId, ...]:
    """The permanents that untap as the active player's turn begins (502.3): all the permanents
    ``player`` controls, in battlefield order. "Doesn't untap" effects and exert (M4, M5) remove
    some; phasing (502.1, M9) is a separate action."""
    return tuple(obj for obj in state.battlefield if state.objects[obj].controller == player)


def mana_that_empties(state: GameState, player: PlayerId) -> tuple[Mana, ...]:
    """The mana that empties from ``player``'s pool as a step or phase ends (500.5, 106.4): all
    of it. Upwelling and firebending (M5, M9) keep some."""
    return tuple(state.player(player).mana_pool)


def can_lose_game(state: GameState, player: PlayerId, reason: LossReason) -> bool:
    """Whether ``player`` can lose the game for ``reason`` (104.3): yes. Platinum Angel and
    Laboratory Maniac (M5, M6) change it. Conceding (104.3a) can't be stopped."""
    return True


# --- Who decides and who sees ------------------------------------------------------------------


def deciding_player(state: GameState, player: PlayerId) -> PlayerId:
    """The player who makes the decisions that ``player`` is asked to make (723.5): ``player``
    themselves. While another player controls them (Mindslaver, Word of Command: 723.1, M9),
    that player decides. 723.6: they still can't make them concede."""
    return player


def knows_identity(state: GameState, obj: GameObject, viewer: PlayerId) -> bool:
    """Whether ``viewer`` knows the identity of ``obj`` (400.2, 402.3, 723.4).

    Cards in public zones are known to everyone (400.2), a hand to its owner (402.3), and any
    card to the players listed in its ``known_to``. 723.4: what a controlled player would know
    is known to the player who controls them too.
    """
    if _knows(obj, viewer):
        return True
    return any(
        _knows(obj, other.id)
        for other in state.players
        if other.id != viewer and deciding_player(state, other.id) == viewer
    )


def _knows(obj: GameObject, viewer: PlayerId) -> bool:
    if obj.zone.kind.is_public:
        return True
    if obj.zone == Zone.hand(viewer):
        return True
    return viewer in obj.known_to


# --- Costs and abilities -----------------------------------------------------------------------


def can_tap_for_cost(state: GameState, obj: ObjectId) -> bool:
    """Whether the permanent ``obj`` may be tapped to pay a cost (302.6, 602.5a): a creature's
    {T} ability needs it to have been under its controller's control continuously since their
    most recent turn began. That is, it came under that control (``entered_turn``) during a turn
    before the one their most recent turn began in (``last_turn_began``); before a player's first
    turn none of their creatures can. Anything else that isn't a creature may (302.6). Haste
    (702.10, M3) plugs in here.

    It is for a permanent's own {T} in an ability's cost (``TapSelfCost``); {Q} (M9) needs the
    same. Tapping creatures for other costs (convoke 702.51, improvise, crew 702.122, "tap an
    untapped creature you control") ignores summoning sickness and must not call it. M3's attack
    half of 302.6 shares the "controlled since the turn began" test.
    """
    if not characteristics(state, obj).is_a(CardType.CREATURE):
        return True
    permanent = state.object(obj)
    if permanent.controller is None:
        return False
    last_turn = state.player(permanent.controller).last_turn_began
    return last_turn is not None and permanent.entered_turn < last_turn


def player_abilities(state: GameState, player: PlayerId) -> tuple[Ability, ...]:
    """The abilities ``player`` has as a player (702.11c: hexproof, 702.18a: shroud, ...): none.
    Leyline of Sanctity and Shalai (M2.8, M5) give them."""
    return ()


# --- Starting the game -------------------------------------------------------------------------


def opening_hand_actions(state: GameState, player: PlayerId) -> tuple[ObjectId, ...]:
    """The cards in ``player``'s opening hand they may take an action with (103.6, Leylines, M5;
    companion, M9): none."""
    return ()


def mulligan_options(state: GameState, player: PlayerId) -> tuple[NamedOption, ...]:
    """What ``player`` may do with their opening hand (103.5): keep it or take a mulligan.

    They can take mulligans "until their opening hand would be zero cards, after which they may
    not take further mulligans": with no cards in hand, only keeping is left.
    """
    if not state.player(player).hand:
        return (KEEP,)
    return (KEEP, MULLIGAN)


def starting_life(state: GameState, player: PlayerId) -> int:
    """``player``'s starting life total (103.4): the game's configuration, 20 in a regular game
    and 40 in Commander (103.4c)."""
    return state.config.starting_life


def starting_hand_size(state: GameState, player: PlayerId) -> int:
    """The number of cards in ``player``'s opening hand (103.5): the game's configuration."""
    return state.config.starting_hand_size


def commander_damage_threshold(state: GameState) -> int:
    """The combat damage from one commander that makes a player lose (903.10a, 104.3j): 21.
    The check itself arrives in M7."""
    if state.config.commander is None:
        raise EngineError("this game has no Commander rules (903)")
    return state.config.commander.damage_threshold
