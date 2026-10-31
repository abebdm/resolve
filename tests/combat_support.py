"""Helpers for tests that declare attackers (508.1) and blockers (509.1), assign combat damage
(510.1) and pass through combat (506-511).

A declaration is a ``ChooseAssignment`` (design.md §17.18): its items are the creatures that may
attack (or block), each item's choices what it may attack (or the attackers it may block). A
damage assignment is a ``DistributeEach``: one part per creature with a choice, its recipients the
creatures (or players) it may assign damage to. These helpers name creatures and players instead
of indices, as ``casting_support`` does for casting.
"""

from __future__ import annotations

from collections.abc import Mapping

from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import (
    Amounts,
    AmountsEach,
    Assignment,
    ChooseAssignment,
    DistributeEach,
    ObjectOption,
    Option,
    PlayerOption,
)
from resolve.engine.api import submit
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.turn import Phase, Step
from tests.game_fixtures import answer, pass_until, request_of


def attack_space(state: GameState) -> ChooseAssignment:
    """The pending declaration of attackers' space (508.1)."""
    request = request_of(state)
    assert request.kind is DecisionKind.DECLARE_ATTACKERS, request.kind
    assert isinstance(request.space, ChooseAssignment)
    return request.space


def may_attack(state: GameState) -> tuple[ObjectId, ...]:
    """The creatures the pending declaration offers as attackers, in its order."""
    items: list[ObjectId] = []
    for item in attack_space(state).items:
        assert isinstance(item, ObjectOption)
        items.append(item.object)
    return tuple(items)


def attack_targets(state: GameState, creature: ObjectId) -> tuple[PlayerId, ...]:
    """What ``creature`` may attack in the pending declaration (508.1b, 802.3)."""
    space = attack_space(state)
    index = may_attack(state).index(creature)
    players: list[PlayerId] = []
    for choice in space.choices[index]:
        assert isinstance(choice, PlayerOption)
        players.append(choice.player)
    return tuple(players)


def attack_answer(state: GameState, attacks: Mapping[ObjectId, PlayerId]) -> Assignment:
    """The ``Assignment`` that declares ``attacks`` (each attacker and the player it attacks)."""
    space = attack_space(state)
    items = may_attack(state)
    unknown = [creature for creature in attacks if creature not in items]
    assert not unknown, f"{unknown} can't attack; the declaration offers {items}"
    picks: list[tuple[int, ...]] = []
    for creature, choices in zip(items, space.choices, strict=True):
        if creature in attacks:
            picks.append((choices.index(PlayerOption(attacks[creature])),))
        else:
            picks.append(())
    return Assignment(tuple(picks))


def declare_attackers(state: GameState, attacks: Mapping[ObjectId, PlayerId]) -> None:
    """Answer the pending declaration with ``attacks`` (empty: no creature attacks)."""
    submit(state, answer(state, attack_answer(state, attacks)))


def block_space(state: GameState) -> ChooseAssignment:
    """The pending declaration of blockers' space (509.1)."""
    request = request_of(state)
    assert request.kind is DecisionKind.DECLARE_BLOCKERS, request.kind
    assert isinstance(request.space, ChooseAssignment)
    return request.space


def may_block(state: GameState) -> tuple[ObjectId, ...]:
    """The creatures the pending declaration of blockers offers as blockers, in its order."""
    items: list[ObjectId] = []
    for item in block_space(state).items:
        assert isinstance(item, ObjectOption)
        items.append(item.object)
    return tuple(items)


def blockable(state: GameState, blocker: ObjectId) -> tuple[ObjectId, ...]:
    """The attackers ``blocker`` may block in the pending declaration (509.1a, 802.4a)."""
    space = block_space(state)
    index = may_block(state).index(blocker)
    attackers: list[ObjectId] = []
    for choice in space.choices[index]:
        assert isinstance(choice, ObjectOption)
        attackers.append(choice.object)
    return tuple(attackers)


def block_answer(state: GameState, blocks: Mapping[ObjectId, tuple[ObjectId, ...]]) -> Assignment:
    """The ``Assignment`` that declares ``blocks`` (each blocker and the attackers it blocks)."""
    space = block_space(state)
    items = may_block(state)
    unknown = [creature for creature in blocks if creature not in items]
    assert not unknown, f"{unknown} can't block; the declaration offers {items}"
    picks: list[tuple[int, ...]] = []
    for creature, choices in zip(items, space.choices, strict=True):
        chosen = blocks.get(creature, ())
        picks.append(tuple(sorted(choices.index(ObjectOption(a)) for a in chosen)))
    return Assignment(tuple(picks))


def declare_blockers(state: GameState, blocks: Mapping[ObjectId, tuple[ObjectId, ...]]) -> None:
    """Answer the pending declaration of blockers with ``blocks`` (empty: no creature blocks)."""
    submit(state, answer(state, block_answer(state, blocks)))


def damage_space(state: GameState) -> DistributeEach:
    """The pending combat damage assignment's space (510.1)."""
    request = request_of(state)
    assert request.kind is DecisionKind.ASSIGN_COMBAT_DAMAGE, request.kind
    assert isinstance(request.space, DistributeEach)
    return request.space


def damage_sources(state: GameState) -> tuple[ObjectId, ...]:
    """The creatures whose damage the pending assignment divides, in its order."""
    sources: list[ObjectId] = []
    for source in damage_space(state).sources:
        assert isinstance(source, ObjectOption)
        sources.append(source.object)
    return tuple(sources)


def damage_recipients(state: GameState, source: ObjectId) -> tuple[Option, ...]:
    """The recipients among which ``source``'s damage is divided in the pending assignment."""
    space = damage_space(state)
    return space.parts[damage_sources(state).index(source)].recipients


def damage_answer(
    state: GameState, assignment: Mapping[ObjectId, Mapping[Option, int]]
) -> AmountsEach:
    """The ``AmountsEach`` giving each source the amounts of ``assignment`` (unnamed recipients
    get 0); every source of the pending assignment must be named."""
    space = damage_space(state)
    sources = damage_sources(state)
    assert set(assignment) == set(sources), f"name every source of {sources}"
    each: list[Amounts] = []
    for source, part in zip(sources, space.parts, strict=True):
        amounts = assignment[source]
        unknown = [r for r in amounts if r not in part.recipients]
        assert not unknown, f"{unknown} isn't a recipient of {source}'s damage"
        each.append(Amounts(tuple(amounts.get(r, 0) for r in part.recipients)))
    return AmountsEach(tuple(each))


def assign_damage(state: GameState, assignment: Mapping[ObjectId, Mapping[Option, int]]) -> None:
    """Answer the pending combat damage assignment (``damage_answer``)."""
    submit(state, answer(state, damage_answer(state, assignment)))


def pass_to(state: GameState, phase: Phase, step: Step | None = None) -> None:
    """Pass priority (``Passer``) until the turn reaches ``phase`` and ``step`` (or the game
    ends)."""

    def reached(state: GameState) -> bool:
        turn = state.turn
        return turn is not None and (turn.phase, turn.step) == (phase, step)

    pass_until(state, reached)
