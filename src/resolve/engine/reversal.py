"""Reversing an illegal action and the mana abilities activated while taking it (733.1).

An action whose payment can't be completed is reversed (``CastSpell`` for spells,
``ActivateManaAbility`` for a mana ability with a mana cost). The player chooses which of the
mana abilities they activated meanwhile to reverse too; the rest stand. This module holds what
both share:

- ``activations_made``: the mana abilities activated while paying, in the order they began,
  those activated while paying for one of them included (605.3a), and without those already
  reversed (a failed activation in the middle of the action, whose kept abilities still count).
- ``check_kept``: 733.1 forbids reversing an ability whose mana was spent on a kept mana ability
  ("unless mana from those abilities ... was spent on another mana ability that wasn't
  reversed"). The kept abilities' mana events are replayed on the pool as it was at the
  checkpoint: a kept payment (``ManaSpent``) that finds its units missing spent a reversed
  ability's mana. Units are identical values (type, source, restriction); when a payment could
  have spent either of two identical units, one there before the action and one a reversed
  ability added, it is taken to have spent the one that was there, as identical mana is
  interchangeable (docs/decisions.md).
- ``reverse_to``: restore the checkpoint, then make each kept activation's own events again,
  exactly as recorded and in log order (``Event.redo``), without activating anything again.

An activation's own events are the log entries between its start and its end, minus those of
the activations made while paying for it (each has its own).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from resolve.decisions.spaces import ManaActivationOption
from resolve.errors import EngineError, InvalidAnswer
from resolve.events.base import Event
from resolve.events.mana import ManaAdded, ManaSpent
from resolve.state.checkpoint import Checkpoint, restore_checkpoint
from resolve.state.game import Player
from resolve.state.ids import PlayerId

if TYPE_CHECKING:
    from resolve.engine.mana import ActivateManaAbility
    from resolve.engine.payment import PayCosts
    from resolve.state.game import GameState


def activations_made(payment: PayCosts | None) -> list[ActivateManaAbility]:
    """The mana abilities activated while making ``payment`` and not reversed, in the order they
    began (an activation before those made while paying for it)."""
    made: list[ActivateManaAbility] = []
    if payment is None:
        return made
    for activation in payment.activations:
        if not activation.reversed:
            made.append(activation)
        made += activations_made(activation.payment)
    return made


def options(activations: Sequence[ActivateManaAbility]) -> tuple[ManaActivationOption, ...]:
    """The options of the ``REVERSE_MANA_ABILITIES`` decision, one per activation."""
    return tuple(
        ManaActivationOption(number, activation.source, activation.index)
        for number, activation in enumerate(activations)
    )


def own_events(state: GameState, activation: ActivateManaAbility) -> list[tuple[int, Event]]:
    """The events ``activation`` itself caused, with their log indices, in log order.

    Entries of the activations made while paying for it are left out (they have their own), as
    are answers and events that are no player's action (a concession, 800.4a).
    """
    if activation.log_from is None or activation.log_to is None:
        raise EngineError(f"the activation of ability {activation.index} hasn't finished")
    children = [] if activation.payment is None else activation.payment.activations
    nested = [(child.log_from, child.log_to) for child in children]
    events: list[tuple[int, Event]] = []
    for index in range(activation.log_from, activation.log_to):
        if any(
            start is not None and end is not None and start <= index < end for start, end in nested
        ):
            continue
        record = state.event_log[index].record
        if isinstance(record, Event) and not record.outside_actions:
            events.append((index, record))
    return events


def check_kept(
    state: GameState,
    checkpoint: Checkpoint,
    player: PlayerId,
    activations: Sequence[ActivateManaAbility],
    kept: Sequence[int],
) -> None:
    """Refuse to keep activations whose payment spent mana of a reversed one (733.1).

    ``kept`` are positions in ``activations``.
    """
    pool = list(_player(checkpoint, player).mana_pool)
    events = sorted(
        (index, number, event)
        for number in kept
        for index, event in own_events(state, activations[number])
    )
    for _, number, event in events:
        if isinstance(event, ManaAdded) and event.player == player:
            pool += event.mana
        elif isinstance(event, ManaSpent) and event.player == player:
            for unit in event.mana:
                if unit not in pool:
                    activation = activations[number]
                    raise InvalidAnswer(
                        f"ability {activation.index} of object {activation.source} is kept, but "
                        "its cost was paid with mana from an ability being reversed: keep that "
                        "one too, or reverse both (733.1)"
                    )
                pool.remove(unit)


def reverse_to(
    state: GameState,
    checkpoint: Checkpoint,
    activations: Sequence[ActivateManaAbility],
    kept: Sequence[int],
) -> None:
    """Reverse the action back to ``checkpoint``, keeping the results of the activations at the
    positions ``kept`` (733.1); the others are marked reversed."""
    redo = sorted(
        (index, event) for number in kept for index, event in own_events(state, activations[number])
    )
    restore_checkpoint(state, checkpoint)
    # 733.1: the kept mana abilities' results stand exactly as they happened.
    for _, event in redo:
        event.redo(state)
    for number, activation in enumerate(activations):
        if number not in kept:
            activation.reversed = True


def _player(checkpoint: Checkpoint, player: PlayerId) -> Player:
    players: list[Player] = checkpoint.values["players"]
    for record in players:
        if record.id == player:
            return record
    raise EngineError(f"player {player} isn't in the checkpoint")
