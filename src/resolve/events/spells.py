"""Events of casting and resolving spells (601.2, 608, 733): proposing and casting, targets,
resolving or not resolving, and reversal."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from resolve.data.mana_cost import ManaCost
from resolve.effects.characteristics import characteristics
from resolve.errors import EngineError
from resolve.events.base import Event
from resolve.state.game import move_object, players_in_game
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import Mana
from resolve.state.spell import CastChoices, CastPermission, CastVariant, Target
from resolve.state.zones import BATTLEFIELD, STACK, Zone, ZoneKind

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
    the ``mana_spent`` to pay it (601.2h), which its record keeps (400.7d). As applied, ``name``
    is the spell's name as it became cast (public: it is on the stack, 400.2)."""

    player: PlayerId
    spell: ObjectId
    total_cost: ManaCost
    mana_spent: tuple[Mana, ...]
    name: str | None = None

    def apply(self, state: GameState) -> Event:
        obj = state.object(self.spell)
        if obj.spell is None or obj.zone.kind is not ZoneKind.STACK:
            raise EngineError(f"object {self.spell} isn't a spell being cast")
        obj.spell = replace(obj.spell, total_cost=self.total_cost, mana_spent=self.mana_spent)
        return replace(self, name=characteristics(state, self.spell).name)


@dataclass(frozen=True, kw_only=True)
class ActionReversed(Event):
    """``player``'s action was illegal and has been reversed (733.1): the game is as it was
    before it, but for the mana abilities the player kept, whose results stand (``kept``: their
    sources, in activation order). ``card`` is the card a reversed cast returned to its zone (with
    its old ID), which every player saw on the stack: they know it now (400.2). ``source`` is the
    source of a reversed mana ability activation (602.2b). Public."""

    player: PlayerId
    card: ObjectId | None = None
    kept: tuple[ObjectId, ...] = ()
    source: ObjectId | None = None

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


@dataclass(frozen=True, kw_only=True)
class BecameTargets(Event):
    """The objects and players chosen for the spell ``spell`` become its targets (601.2c):
    ``targets`` holds them per instance of the word "target", in the order of its text, and
    joins its record. Public: targets are announced (601.2c). Abilities that trigger on becoming
    a target (ward, M4) trigger here. A spell that chose no target at all isn't targeted
    (115.6)."""

    spell: ObjectId
    targets: tuple[tuple[Target, ...], ...]

    def apply(self, state: GameState) -> None:
        obj = state.object(self.spell)
        if obj.spell is None or obj.zone.kind is not ZoneKind.STACK:
            raise EngineError(f"object {self.spell} isn't a spell being cast")
        if obj.spell.targets:
            raise EngineError(f"spell {self.spell} already has its targets")
        obj.spell = replace(obj.spell, targets=self.targets)


@dataclass(frozen=True, kw_only=True)
class SpellDidNotResolve(Event):
    """Every target of the spell ``spell`` is illegal as it would resolve, so it doesn't resolve
    (608.2b): it is removed from the stack and put into its owner's graveyard, as a new object
    (400.7, recorded as ``moved``), and none of its effects happen. Public."""

    spell: ObjectId
    moved: ObjectId | None = None

    def apply(self, state: GameState) -> Event:
        if self.moved is not None:
            raise EngineError("a spell is proposed to fail without its outcome")
        obj = state.object(self.spell)
        if obj.spell is None or obj.zone.kind is not ZoneKind.STACK:
            raise EngineError(f"object {self.spell} isn't a spell on the stack")
        moved = move_object(state, self.spell, Zone.graveyard(obj.owner))
        return replace(self, moved=moved.id)


@dataclass(frozen=True, kw_only=True)
class SpellResolved(Event):
    """The instant or sorcery spell ``spell`` has followed its instructions (608.2c); as the
    final part of its resolution it is put into ``destination`` (608.2n: its owner's graveyard
    by default, ``defaults.resolved_spell_destination``), as a new object (400.7, recorded as
    ``moved``). If it left the stack while resolving it still resolved fully, and nothing moves
    (608.2m): ``destination`` is ``None``. Public."""

    spell: ObjectId
    destination: Zone | None
    moved: ObjectId | None = None

    def apply(self, state: GameState) -> Event | None:
        if self.moved is not None:
            raise EngineError("a resolution is proposed without its outcome")
        if self.destination is None:
            if self.spell in state.objects and self.spell in state.stack:
                raise EngineError(f"spell {self.spell} is still on the stack")
            return None
        obj = state.object(self.spell)
        if obj.spell is None or obj.zone.kind is not ZoneKind.STACK:
            raise EngineError(f"object {self.spell} isn't a spell on the stack")
        controller = obj.controller if self.destination.kind in _CONTROLLED else None
        moved = move_object(state, self.spell, self.destination, controller=controller)
        return replace(self, moved=moved.id)


# Zones whose objects have a controller (108.4, 110.2): a spell put there keeps its controller.
_CONTROLLED = (ZoneKind.BATTLEFIELD, ZoneKind.STACK)
