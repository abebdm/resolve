"""Events of casting and resolving spells (601.2, 608, 733)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from resolve.data.mana_cost import ManaCost
from resolve.errors import EngineError
from resolve.events.base import Event
from resolve.state.game import move_object, players_in_game
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import Mana
from resolve.state.spell import CastChoices, CastPermission, CastVariant
from resolve.state.zones import BATTLEFIELD, STACK, ZoneKind

if TYPE_CHECKING:
    from resolve.state.game import GameState


@dataclass(frozen=True, kw_only=True)
class SpellProposed(Event):
    """``player`` proposes casting ``card`` as ``variant`` under ``permission`` (601.2a): the card
    moves from where it is to the top of the stack, as a new object (400.7, recorded as
    ``spell``) that ``player`` controls, with the record ``CastChoices(variant, permission,
    cast_from)``. Public: everyone sees the card on the stack (400.2)."""

    player: PlayerId
    card: ObjectId
    variant: CastVariant
    permission: CastPermission
    spell: ObjectId | None = None

    def apply(self, state: GameState) -> Event:
        if self.spell is not None:
            raise EngineError("a spell is proposed without its outcome")
        cast_from = state.object(self.card).zone
        if cast_from.kind is ZoneKind.STACK:
            raise EngineError(f"object {self.card} is already on the stack")
        new = move_object(state, self.card, STACK, controller=self.player)
        new.spell = CastChoices(self.variant, self.permission, cast_from)
        return replace(self, spell=new.id)


@dataclass(frozen=True, kw_only=True)
class SpellCast(Event):
    """The spell ``spell`` becomes cast (601.2i), with its locked-in ``total_cost`` (601.2f) and
    the ``mana_spent`` to pay it (601.2h), which its record keeps (400.7d)."""

    player: PlayerId
    spell: ObjectId
    total_cost: ManaCost
    mana_spent: tuple[Mana, ...]

    def apply(self, state: GameState) -> None:
        obj = state.object(self.spell)
        if obj.spell is None or obj.zone.kind is not ZoneKind.STACK:
            raise EngineError(f"object {self.spell} isn't a spell being cast")
        obj.spell = replace(obj.spell, total_cost=self.total_cost, mana_spent=self.mana_spent)


@dataclass(frozen=True, kw_only=True)
class ActionReversed(Event):
    """``player``'s action was illegal and has been reversed (733.1): the game is as it was
    before it, but for the mana abilities the player kept. ``card`` is the card a reversed cast
    returned to its zone (with its old ID), which every player saw on the stack: they know it now
    (400.2). Public."""

    player: PlayerId
    card: ObjectId | None = None

    def apply(self, state: GameState) -> None:
        if self.card is None:
            return
        obj = state.object(self.card)
        seen = [p for p in players_in_game(state) if p != obj.owner]
        obj.known_to = tuple(sorted({*obj.known_to, *seen}))


@dataclass(frozen=True, kw_only=True)
class PermanentSpellResolved(Event):
    """The permanent spell ``spell`` resolves: it becomes a permanent on the battlefield under its
    controller's control (608.3a), as a new object (400.7, recorded as ``permanent``) that keeps
    how its spell was cast (``cast_record``, 400.7d)."""

    spell: ObjectId
    permanent: ObjectId | None = None

    def apply(self, state: GameState) -> Event:
        if self.permanent is not None:
            raise EngineError("a resolution is proposed without its outcome")
        obj = state.object(self.spell)
        if obj.spell is None or obj.zone.kind is not ZoneKind.STACK:
            raise EngineError(f"object {self.spell} isn't a spell on the stack")
        record = obj.spell
        new = move_object(state, self.spell, BATTLEFIELD, controller=obj.controller)
        new.cast_record = record
        return replace(self, permanent=new.id)
