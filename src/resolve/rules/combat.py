"""Combat rules that read the game state (506-511; design.md §17.18).

- ``defending_players``: who is attacked this combat (506.2, 802.2).
- ``attack_targets``: what an attacker may attack (506.3, 508.1b).
- ``attack_declaration``: the declaration of attackers compiled into a ``ChooseAssignment``
  (508.1a-b, 802.3): its items are the creatures that may attack something, each item's choices
  what it may attack, all checked by ``legality.allowed(AttackAction)``.

Declaring blockers, dividing damage and the declaration-wide restrictions and requirements
arrive in M3.3 to M3.5. Leaving combat is ``resolve.state.combat.remove_from_combat``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from resolve.decisions.spaces import ChooseAssignment, ObjectOption, Option, PlayerOption
from resolve.errors import EngineError
from resolve.state.combat import AttackPlayer, AttackTarget
from resolve.state.game import apnap_order
from resolve.state.ids import ObjectId, PlayerId

if TYPE_CHECKING:
    from resolve.state.game import GameState


def defending_players(state: GameState) -> tuple[PlayerId, ...]:
    """The defending players as the combat phase begins, in APNAP order (101.4).

    506.2: in a two-player game, the nonactive player. 802.2: in a multiplayer game, every
    opponent of the attacking player (the attack multiple players option, Commander's default,
    903.2). That every opponent defends is a deliberate non-parameter, not a rule default
    (docs/decisions.md 2026-10-18): the "attack left/right" options (803) would change the
    procedure, not a value. Players who have left the game aren't opponents in it (800.4a).
    """
    turn = state.turn
    if turn is None:
        raise EngineError("defending players exist only during a turn's combat phase (506.2)")
    return tuple(player for player in apnap_order(state) if player != turn.active_player)


def attack_targets(state: GameState) -> tuple[AttackTarget, ...]:
    """What may be attacked this combat, in APNAP order (506.3, 508.1b): each defending player
    still in the game (800.4a). Their planeswalkers and the battles they protect join in M4."""
    turn = state.turn
    if turn is None or turn.combat is None:
        raise EngineError("there is nothing to attack outside a combat (506.1)")
    return tuple(
        AttackPlayer(player)
        for player in turn.combat.defending_players
        if not state.player(player).left_game
    )


def target_option(target: AttackTarget) -> Option:
    """The option that stands for ``target`` in a declaration."""
    return PlayerOption(target.player)


def option_target(option: Option) -> AttackTarget:
    """The attack target an option of a declaration stands for (``target_option``'s inverse)."""
    if not isinstance(option, PlayerOption):
        raise EngineError(f"{option!r} isn't something a creature can attack")
    return AttackPlayer(option.player)


def attack_declaration(state: GameState) -> ChooseAssignment | None:
    """The declaration of attackers as a ``ChooseAssignment`` (508.1a-b; design.md §17.18).

    Its items are the creatures the attacking player controls, in battlefield order, that may
    attack at least one target (``legality.allowed(AttackAction)``: 508.1a, 302.6, 702.3b), each
    with the targets it may attack (``attack_targets``, 508.1b, 802.3) and a maximum of 1 (a
    creature attacks one player, planeswalker or battle). ``None`` when no creature may attack:
    the declaration has one possible answer, no attackers, so it isn't asked (design.md §6).
    """
    from resolve.rules import legality

    turn = state.turn
    if turn is None or turn.combat is None:
        raise EngineError("attackers are declared only during a combat (508.1)")
    attacker = turn.active_player
    targets = attack_targets(state)
    items: list[Option] = []
    choices: list[tuple[Option, ...]] = []
    for obj in state.battlefield:
        allowed = tuple(
            target_option(target)
            for target in targets
            if legality.allowed(state, legality.AttackAction(attacker, obj, target)).allowed
        )
        if allowed:
            items.append(ObjectOption(obj))
            choices.append(allowed)
    if not items:
        return None
    return ChooseAssignment(tuple(items), tuple(choices), (1,) * len(items))


def declared_attacks(
    space: ChooseAssignment, picks: tuple[tuple[int, ...], ...]
) -> tuple[tuple[ObjectId, AttackTarget], ...]:
    """The attacks a validated answer to ``attack_declaration``'s space declares: each chosen
    creature and what it attacks, in item order (508.1a-b)."""
    attacks: list[tuple[ObjectId, AttackTarget]] = []
    for item, choices, chosen in zip(space.items, space.choices, picks, strict=True):
        if not isinstance(item, ObjectOption):
            raise EngineError(f"{item!r} isn't a creature")
        attacks.extend((item.object, option_target(choices[index])) for index in chosen)
    return tuple(attacks)
