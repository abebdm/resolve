"""Helpers for tests that declare attackers (508.1) and pass through combat (506-511).

The declaration is a ``ChooseAssignment`` (design.md §17.18): its items are the creatures that may
attack, each item's choices what it may attack. These helpers name creatures and players instead
of indices, as ``casting_support`` does for casting.
"""

from __future__ import annotations

from collections.abc import Mapping

from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import Assignment, ChooseAssignment, ObjectOption, PlayerOption
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


def pass_to(state: GameState, phase: Phase, step: Step | None = None) -> None:
    """Pass priority (``Passer``) until the turn reaches ``phase`` and ``step`` (or the game
    ends)."""

    def reached(state: GameState) -> bool:
        turn = state.turn
        return turn is not None and (turn.phase, turn.step) == (phase, step)

    pass_until(state, reached)
