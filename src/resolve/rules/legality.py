"""Legality: whether a player may take an action (101.2, design.md §17.2).

Every legality question is an ``Action`` value. ``allowed(state, action)`` works in four steps:

1. ``permissions`` collects what allows the action: the rules' own (for playing a land, 305.1 and
   116.2a) and those effects grant.
2. At least one permission is required.
3. ``prohibitions`` collects what forbids it: the rules' own "can't" (for playing a land, the
   limit of 305.2b) and those effects impose.
4. Any applicable prohibition wins (101.2). Adding or removing abilities is not a prohibition
   (101.2a).

Playing a land, casting a spell, targeting (``TargetAction``, through
``resolve.rules.targeting.target_problem``), destroying (``DestroyAction``), countering
(``CounterAction``) and attacking (``AttackAction``, 508.1a) exist so far; blocking joins them
in M3.3, and activating
abilities in M4 (until then a mana ability's own conditions decide: 602.5 in
``ActivatedManaAbility.can_activate``). A function that asks the question calls
``legality.allowed`` through the module, so a test or an effect that replaces ``permissions`` or
``prohibitions`` is obeyed everywhere.

The keyword prohibitions read abilities only through computed characteristics (a permanent's)
or ``defaults.player_abilities`` (a player's), so abilities that effects grant (M5) need no
change here:

- targeting: shroud (702.18a), hexproof (702.11b-c), hexproof from a quality (702.11d) and
  protection (702.16b, 702.16j), on a permanent or a player; a spell on the stack keeps none of
  them (113.6: a permanent's abilities function on the battlefield);
- destroying: indestructible (702.12b);
- countering: "can't be countered" (113.6g);
- attacking: defender (702.3b).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.cards.keywords import (
    Defender,
    Hexproof,
    Indestructible,
    Protection,
    Shroud,
    has_keyword,
)
from resolve.cards.keywords.qualities import Everything
from resolve.cards.primitives.base import Ability
from resolve.cards.primitives.statics import CantBeCountered
from resolve.cards.primitives.targets import TargetSpec
from resolve.data.types import CardType
from resolve.effects.characteristics import (
    Characteristics,
    characteristics,
    variant_characteristics,
)
from resolve.errors import EngineError, NotImplementedRule
from resolve.rules import defaults
from resolve.state.combat import AttackPlayer, AttackTarget
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.spell import CastPermission, CastVariant, Target, TargetObject, TargetPlayer
from resolve.state.zones import Zone, ZoneKind
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
class CastAction(Action):
    """``player`` casts the card ``card`` as ``variant`` under ``permission`` (601.3, 601.3e).

    Asked before the card moves (601.3: whether they may begin), and again for the spell on the
    stack once its proposal is complete (601.2e, 601.6), judged as if it were still in the zone it
    came from.
    """

    card: ObjectId
    variant: CastVariant
    permission: CastPermission


@dataclass(frozen=True)
class Targeter(Immutable):
    """A spell or ability choosing or checking its targets (115.1): ``obj``, the spell (or, from
    M4, the ability) on the stack, or the card about to become one; ``controller``, who controls
    it (109.5); ``characteristics``, which protection and "hexproof from" judge it by (the
    spell's own, or an ability's source's last known information, 113.7a; 702.16b, 702.11d)."""

    controller: PlayerId
    obj: ObjectId
    characteristics: Characteristics


@dataclass(frozen=True)
class TargetAction(Action):
    """``targeter`` chooses (601.2c) or keeps (608.2b) ``candidate`` as a target for the instance
    of "target" ``spec``. ``player`` is the targeter's controller."""

    targeter: Targeter
    spec: TargetSpec
    candidate: Target


@dataclass(frozen=True)
class DestroyAction(Action):
    """The permanent ``obj`` is destroyed (701.8a) by an effect ``player`` controls; for the
    state-based action of lethal damage (704.5g), which no player controls, ``player`` is the
    permanent's controller."""

    obj: ObjectId


@dataclass(frozen=True)
class CounterAction(Action):
    """The spell ``spell`` is countered (701.6a) by a spell or ability ``player`` controls."""

    spell: ObjectId


@dataclass(frozen=True)
class AttackAction(Action):
    """``player``, the attacking player (506.2), declares ``creature`` as an attacker attacking
    ``target`` (508.1a-b, 802.3), during a combat (``TurnState.combat``)."""

    creature: ObjectId
    target: AttackTarget


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
    if isinstance(action, CastAction):
        return _cast_permissions(state, action)
    if isinstance(action, TargetAction):
        return _target_permissions(state, action)
    if isinstance(action, DestroyAction):
        return _destroy_permissions(state, action)
    if isinstance(action, CounterAction):
        return _counter_permissions(state, action)
    if isinstance(action, AttackAction):
        return _attack_permissions(state, action)
    raise EngineError(f"no rule of legality covers {action!r}")


def prohibitions(state: GameState, action: Action) -> tuple[Prohibition, ...]:
    """Everything that forbids ``action`` now."""
    if isinstance(action, PlayLand):
        return _land_play_prohibitions(state, action)
    if isinstance(action, CastAction):
        # 101.2: "can't cast" effects (Kutzil's Flanker, M5; split second, M9) forbid it here.
        return ()
    if isinstance(action, TargetAction):
        return _target_prohibitions(state, action)
    if isinstance(action, DestroyAction):
        return _destroy_prohibitions(state, action)
    if isinstance(action, CounterAction):
        return _counter_prohibitions(state, action)
    if isinstance(action, AttackAction):
        return _attack_prohibitions(state, action)
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
    if isinstance(action, CastAction):
        return ("601.3", "117.1a")
    if isinstance(action, TargetAction):
        return ("115.1", "115.2")
    if isinstance(action, DestroyAction):
        return ("701.8a",)
    if isinstance(action, CounterAction):
        return ("701.6a",)
    if isinstance(action, AttackAction):
        return ("508.1a", "506.2")
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


def _cast_permissions(state: GameState, action: CastAction) -> tuple[Permission, ...]:
    # 601.3: a rule or effect allows the cast: the permission applies to the card where it is
    # (``defaults.cast_permissions``), the card is a spell it allows (a mana value limit, such as
    # Rishkar's Expertise's "with mana value 5 or less") and its timing allows casting the
    # variant now (117.1a, 608.2g). 601.3e: both are judged on the variant's characteristics.
    if action.card not in state.objects:
        return ()
    if action.permission not in defaults.cast_permissions(state, action.player, action.card):
        return ()
    limit = action.permission.mana_value_at_most
    if limit is not None:
        chars = variant_characteristics(state, action.card, action.variant)
        if chars.mana_value > limit:  # 202.3: from the printed mana cost
            return ()
    if not defaults.may_cast_now(
        state, action.player, action.card, action.variant, action.permission
    ):
        return ()
    return (
        Permission(action.permission.rule, f"cast a spell from the {action.permission.zone.value}"),
    )


def _target_permissions(state: GameState, action: TargetAction) -> tuple[Permission, ...]:
    # 115.1: the spell's text says what it may target. In order: the kind and zone (115.2, 115.4;
    # 800.4a; 608.2b: an object that left its zone is a new object, so its old ID is gone), the
    # filter, and 115.5 (not itself).
    spec, you = action.spec, action.targeter.controller
    match action.candidate:
        case TargetPlayer(player=player):
            if spec.players is None or state.player(player).left_game:
                return ()
            if not spec.players.matches(state, player, you):
                return ()
            return (Permission("115.1", f"target {spec.players.text}s"),)
        case TargetObject(object=obj):
            game_object = state.objects.get(obj)
            if game_object is None:
                return ()
            if game_object.zone.kind is ZoneKind.BATTLEFIELD:
                if spec.objects is None or not spec.objects.matches(state, obj, you):
                    return ()
                return (Permission("115.2", f"target a {spec.objects.text}"),)
            if game_object.zone.kind is ZoneKind.STACK:
                if spec.spells is None or not spec.spells.matches(state, obj, you):
                    return ()
                return (Permission("115.2", "target a spell"),)
            return ()  # 115.2: no spec targets cards in other zones yet (M4)


def _destroy_permissions(state: GameState, action: DestroyAction) -> tuple[Permission, ...]:
    # 701.8a: destroying moves a permanent from the battlefield to its owner's graveyard.
    obj = state.objects.get(action.obj)
    if obj is None or obj.zone.kind is not ZoneKind.BATTLEFIELD:
        return ()
    return (Permission("701.8a", "destroy a permanent"),)


def _target_prohibitions(state: GameState, action: TargetAction) -> tuple[Prohibition, ...]:
    targeter = action.targeter
    if action.candidate == TargetObject(targeter.obj):
        # 115.5: a spell or ability on the stack is an illegal target for itself.
        return (Prohibition("115.5", "a spell or ability can't target itself"),)
    found = _candidate_abilities(state, action.candidate)
    if found is None:
        return ()
    abilities, protected = found
    # 102.2-102.3: in a two-player or free-for-all game every other player is an opponent
    # (teams, 810.x, are M9's).
    by_opponent = targeter.controller != protected
    forbidden: list[Prohibition] = []
    for ability in abilities:
        match ability:
            case Shroud():
                forbidden.append(Prohibition("702.18a", "it has shroud"))
            case Hexproof(quality=None) if by_opponent:
                rule = "702.11c" if isinstance(action.candidate, TargetPlayer) else "702.11b"
                forbidden.append(Prohibition(rule, "it has hexproof against its opponents"))
            case Hexproof(quality=quality) if by_opponent and quality is not None:
                if isinstance(action.candidate, TargetPlayer):
                    # 702.11d defines "hexproof from" for a permanent only; no card gives it to a
                    # player.
                    raise NotImplementedRule("702.11d: a player with hexproof from a quality")
                if quality.matches(targeter.characteristics):
                    forbidden.append(Prohibition("702.11d", f"it has {ability.text.lower()}"))
            case Protection(quality=Everything()):
                forbidden.append(Prohibition("702.16j", "it has protection from everything"))
            case Protection(quality=quality) if quality.matches(targeter.characteristics):
                forbidden.append(Prohibition("702.16b", f"it has {ability.text.lower()}"))
            case _:
                pass
    # 702.11h, 702.16m, 702.18b: redundant instances forbid it once.
    return tuple(dict.fromkeys(forbidden))


def _candidate_abilities(
    state: GameState, candidate: Target
) -> tuple[tuple[Ability, ...], PlayerId] | None:
    """The abilities of a target candidate that can stop it being targeted, and who it belongs
    to for hexproof (a permanent's controller, 702.11b; the player, 702.11c): ``None`` for a
    spell on the stack, whose permanent abilities don't function there (113.6)."""
    match candidate:
        case TargetPlayer(player=player):
            return defaults.player_abilities(state, player), player
        case TargetObject(object=obj):
            game_object = state.objects.get(obj)
            if game_object is None or game_object.zone.kind is not ZoneKind.BATTLEFIELD:
                return None
            if game_object.controller is None:
                raise EngineError(f"permanent {obj} has no controller (110.2)")
            return characteristics(state, obj).abilities, game_object.controller


def _destroy_prohibitions(state: GameState, action: DestroyAction) -> tuple[Prohibition, ...]:
    # 702.12b: a permanent with indestructible can't be destroyed (by an effect or by 704.5g).
    if any(isinstance(a, Indestructible) for a in characteristics(state, action.obj).abilities):
        return (Prohibition("702.12b", "it has indestructible"),)
    return ()


def _counter_permissions(state: GameState, action: CounterAction) -> tuple[Permission, ...]:
    # 701.6a: countering a spell removes it from the stack.
    obj = state.objects.get(action.spell)
    if obj is None or obj.zone.kind is not ZoneKind.STACK or obj.spell is None:
        return ()
    return (Permission("701.6a", "counter a spell"),)


def _counter_prohibitions(state: GameState, action: CounterAction) -> tuple[Prohibition, ...]:
    # 113.6g: "This spell can't be countered." functions on the stack.
    if any(isinstance(a, CantBeCountered) for a in characteristics(state, action.spell).abilities):
        return (Prohibition("113.6g", "it can't be countered"),)
    return ()


def _attack_permissions(state: GameState, action: AttackAction) -> tuple[Permission, ...]:
    # 508.1a: during a combat, the active player (the attacking player, 506.2) may declare an
    # untapped creature they control that isn't a battle and isn't summoning sick (302.6;
    # haste, 702.10b, is read by ``summoning_sick``), attacking a defending player still in
    # the game (506.2, 802.2, 800.4a). 506.3: only a creature can attack. These are the
    # permission's conditions, not prohibitions: "can attack as though it didn't have
    # defender" or "as though it were untapped" effects (M5) add a permission.
    turn = state.turn
    combat = None if turn is None else turn.combat
    if turn is None or combat is None or action.player != turn.active_player:
        return ()
    obj = state.objects.get(action.creature)
    if obj is None or obj.zone.kind is not ZoneKind.BATTLEFIELD:
        return ()
    if obj.controller != action.player or obj.tapped:
        return ()
    types = characteristics(state, action.creature).card_types
    if CardType.CREATURE not in types or CardType.BATTLE in types:
        return ()
    if defaults.summoning_sick(state, action.creature, defaults.SicknessPurpose.ATTACK):
        return ()
    match action.target:
        case AttackPlayer(player=player):
            if player not in combat.defending_players or state.player(player).left_game:
                return ()
    return (
        Permission("508.1a", "attack with an untapped creature controlled since the turn began"),
    )


def _attack_prohibitions(state: GameState, action: AttackAction) -> tuple[Prohibition, ...]:
    # 702.3b: a creature with defender can't attack (redundant instances forbid it once). The
    # other restrictions on one creature arrive with their cards: "can't attack (unless ...)"
    # and Ghostly Prison's cost (M3.5).
    if has_keyword(characteristics(state, action.creature), Defender):
        return (Prohibition("702.3b", "it has defender"),)
    return ()
