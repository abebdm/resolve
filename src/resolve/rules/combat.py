"""Combat rules that read the game state (506-511; design.md §17.18).

- ``defending_players``: who is attacked this combat (506.2, 802.2).
- ``attack_targets``: what an attacker may attack (506.3, 508.1b).
- ``attack_declaration``: the declaration of attackers compiled into a ``ChooseAssignment``
  (508.1a-b, 802.3): its items are the creatures that may attack something, each item's choices
  what it may attack, all checked by ``legality.allowed(AttackAction)``.

- ``block_declaration``: one defending player's declaration of blockers compiled into a
  ``ChooseAssignment`` (509.1a-b, 802.4a-b): its items are their creatures that may block
  something, each item's choices the attackers it may block (``legality.allowed(BlockAction)``),
  its maximum ``defaults.blocks_allowed``, its constraints menace's (702.111b,
  ``minimum_blockers``).
- ``damage_recipients``: what each attacking and blocking creature may assign its combat damage
  to (510.1b-d).

The other declaration-wide restrictions and the requirements arrive in M3.5. Leaving combat is
``resolve.state.combat.remove_from_combat``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from resolve.cards.keywords import Menace, has_keyword
from resolve.decisions.spaces import (
    ChooseAssignment,
    NoneOrAtLeast,
    ObjectOption,
    Option,
    PlayerOption,
)
from resolve.effects.characteristics import characteristics
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


def block_declaration(state: GameState, player: PlayerId) -> ChooseAssignment | None:
    """The declaration of the defending player ``player``'s blockers as a ``ChooseAssignment``
    (509.1a-b; design.md §17.18).

    Its items are the creatures ``player`` controls, in battlefield order, that may block at
    least one attacker (``legality.allowed(BlockAction)``: 509.1a, 802.4a, and the restrictions
    on one blocker and one attacker, 509.1b: evasion, protection, "can't be blocked", Champion of
    Lambholt's); each item's choices are the attackers it may block, in declaration order; its
    maximum is ``defaults.blocks_allowed`` (1, 509.1a; ``None``, any number: Palace Guard), at
    most its number of choices. Other players' attackers and blockers are ignored (802.4b).

    The restrictions on the whole declaration are its constraints (509.1b): an attacker with
    menace is blocked by none or by at least two creatures (702.111b, ``NoneOrAtLeast``). An
    attacker that fewer of ``player``'s creatures may block than its minimum can't be blocked in
    any legal declaration, so it is no item's choice (and has no constraint).

    ``None`` when no creature may block: the declaration has one possible answer, no blockers,
    so it isn't asked (design.md §6). A creature allowed to block none (a maximum of 0) isn't an
    item.
    """
    from resolve.rules import defaults, legality

    turn = state.turn
    if turn is None or turn.combat is None:
        raise EngineError("blockers are declared only during a combat (509.1)")
    attackers = tuple(turn.combat.attackers)
    able: list[tuple[ObjectId, tuple[ObjectId, ...], int | None]] = []
    for obj in state.battlefield:
        allowed = tuple(
            attacker
            for attacker in attackers
            if legality.allowed(state, legality.BlockAction(player, obj, attacker)).allowed
        )
        limit = defaults.blocks_allowed(state, obj)
        if allowed and (limit is None or limit > 0):
            # A creature allowed to block none doesn't count toward a minimum either.
            able.append((obj, allowed, limit))
    minimums = {
        attacker: minimum
        for attacker in attackers
        if (minimum := minimum_blockers(state, attacker)) is not None
    }
    # An attacker fewer creatures may block than its minimum is no one's choice.
    blockable = {
        attacker: sum(attacker in allowed for _, allowed, _ in able) >= minimums.get(attacker, 1)
        for attacker in attackers
    }
    items: list[Option] = []
    choices: list[tuple[Option, ...]] = []
    maxima: list[int] = []
    for obj, allowed, limit in able:
        kept = tuple(ObjectOption(attacker) for attacker in allowed if blockable[attacker])
        if not kept:
            continue
        maximum = len(kept) if limit is None else min(limit, len(kept))
        items.append(ObjectOption(obj))
        choices.append(kept)
        maxima.append(maximum)
    if not items:
        return None
    offered = {choice for own in choices for choice in own}
    constraints = tuple(
        NoneOrAtLeast(ObjectOption(attacker), minimum)
        for attacker, minimum in minimums.items()
        if ObjectOption(attacker) in offered
    )
    return ChooseAssignment(tuple(items), tuple(choices), tuple(maxima), constraints)


def minimum_blockers(state: GameState, attacker: ObjectId) -> int | None:
    """The fewest creatures that may block ``attacker`` if any do, or ``None`` for no minimum
    (one blocker is enough): 2 for menace (702.111b; several instances are redundant, 702.111c),
    read from its computed characteristics."""
    if has_keyword(characteristics(state, attacker), Menace):
        return 2
    return None


def declared_blocks(
    space: ChooseAssignment, picks: tuple[tuple[int, ...], ...]
) -> tuple[tuple[ObjectId, tuple[ObjectId, ...]], ...]:
    """The blocks a validated answer to ``block_declaration``'s space declares: each chosen
    blocker and the attackers it blocks, in item order and, for each, in the attackers' order
    (509.1a, 509.1g). Creatures that block nothing aren't listed."""
    blocks: list[tuple[ObjectId, tuple[ObjectId, ...]]] = []
    for item, choices, chosen in zip(space.items, space.choices, picks, strict=True):
        if not chosen:
            continue
        if not isinstance(item, ObjectOption):
            raise EngineError(f"{item!r} isn't a creature")
        blocked: list[ObjectId] = []
        for index in chosen:
            choice = choices[index]
            if not isinstance(choice, ObjectOption):
                raise EngineError(f"{choice!r} isn't an attacking creature")
            blocked.append(choice.object)
        blocks.append((item.object, tuple(blocked)))
    return tuple(blocks)


def damage_recipients(state: GameState) -> tuple[tuple[ObjectId, tuple[Option, ...]], ...]:
    """What each creature in combat may assign its combat damage to (510.1b-d): each attacking
    creature, in declaration order, then each blocking creature, in declaration order, with its
    possible recipients (an empty tuple: it assigns no combat damage).

    - An unblocked attacker: the player it attacks (510.1b); nothing if it attacks nothing
      (506.4c) or a player who has left the game (800.4e).
    - A blocked attacker: the creatures blocking it now, in the order they were declared
      (510.1c); nothing if none is left. Trample (702.19b-d, M3.6) adds what it attacks.
    - A blocker: the attackers it blocks now, in the order chosen (510.1d); nothing if none is
      left.

    How much each assigns (510.1a) is ``defaults.combat_damage_amount``; the caller drops those
    that assign 0 or less.
    """
    turn = state.turn
    if turn is None or turn.combat is None:
        raise EngineError("combat damage is assigned only during a combat (510.1)")
    combat = turn.combat
    recipients: list[tuple[ObjectId, tuple[Option, ...]]] = []
    for attacker, record in combat.attackers.items():
        if record.blocked is None:
            raise EngineError(f"attacker {attacker} is neither blocked nor unblocked (509.1h)")
        if record.blocked:
            options: tuple[Option, ...] = tuple(
                ObjectOption(blocker) for blocker in combat.blockers_of(attacker)
            )
        elif record.target is None or state.player(record.target.player).left_game:
            options = ()
        else:
            options = (target_option(record.target),)
        recipients.append((attacker, options))
    for blocker, block in combat.blockers.items():
        recipients.append((blocker, tuple(ObjectOption(a) for a in block.blocking)))
    return tuple(recipients)
