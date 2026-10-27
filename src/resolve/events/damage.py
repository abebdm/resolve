"""Damage (120): the damage event and its results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.data.types import CardType
from resolve.errors import EngineError, NotImplementedRule
from resolve.events.base import Event
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.zones import ZoneKind

if TYPE_CHECKING:
    from resolve.effects.characteristics import Characteristics
    from resolve.state.game import GameState


@dataclass(frozen=True, kw_only=True)
class DamageDealt(Event):
    """``source`` deals damage, all at once (120.4b): ``to_objects`` and ``to_players`` pair each
    recipient with the amount dealt to it, each at least 1 (120.8). Public.

    Applying it processes the damage into its results (120.3, 120.4c), read from the source's
    characteristics (its last known information if it has left its zone, 113.7a, 608.2h) and the
    recipient's:

    - to a player: they lose that much life (120.3a, 119.3);
    - to a creature: that much damage is marked on it (120.3e).

    Protection's prevention (702.16e) belongs to the prevention stage (M6); until then damage it
    would prevent raises ``NotImplementedRule("702.16e")`` here, before anything changes.

    The results that change with the source's abilities plug in here with their keywords:
    infect (120.3b, 120.3d), wither (120.3d) and lifelink (120.3f); none can exist yet. Damage to
    a planeswalker (120.3c) or a battle (120.3h) removes counters, which arrive in M4: until then
    it raises ``NotImplementedRule``. Prevention and replacement (120.4a-b, 615, M6) act on the
    proposed event, before it is applied.
    """

    source: ObjectId
    to_objects: tuple[tuple[ObjectId, int], ...] = ()
    to_players: tuple[tuple[PlayerId, int], ...] = ()

    def apply(self, state: GameState) -> None:
        from resolve.effects.characteristics import characteristics
        from resolve.effects.evaluation import information

        if not self.to_objects and not self.to_players:
            raise EngineError("a damage event needs a recipient")
        if any(amount < 1 for _, amount in (*self.to_objects, *self.to_players)):
            raise EngineError("0 damage isn't dealt (120.8)")
        known = information(state, self.source)
        if known is None:
            raise EngineError(f"nothing is known of the damage source {self.source}")
        _protection_gap(state, known.characteristics, self)
        marked: list[tuple[ObjectId, int]] = []
        for obj, amount in self.to_objects:
            game_object = state.object(obj)
            if game_object.zone.kind is not ZoneKind.BATTLEFIELD:
                raise EngineError(f"object {obj} isn't a permanent (120.1a)")
            types = characteristics(state, obj).card_types
            if CardType.PLANESWALKER in types:
                raise NotImplementedRule("120.3c: damage removing loyalty counters (M4)")
            if CardType.BATTLE in types:
                raise NotImplementedRule("120.3h: damage removing defense counters (M4)")
            if CardType.CREATURE not in types:
                raise EngineError(f"object {obj} can't be dealt damage (120.1a)")
            marked.append((obj, amount))
        for player, _ in self.to_players:
            if state.player(player).left_game:
                raise EngineError(f"player {player} has left the game (800.4a)")
        for obj, amount in marked:
            state.objects[obj].damage += amount  # 120.3e
        for player, amount in self.to_players:
            state.player(player).life -= amount  # 120.3a, 119.3

    @property
    def total(self) -> int:
        """The damage dealt in all (for statistics)."""
        return sum(amount for _, amount in (*self.to_objects, *self.to_players))


def _protection_gap(state: GameState, source: Characteristics, event: DamageDealt) -> None:
    """702.16e: damage a source with the quality would deal to a permanent or player with
    protection from it is prevented (702.16j: from everything, all damage). Prevention is the
    replacement stage's (615, M6), so until then such damage is a gap; damage from any other
    source is dealt as normal."""
    from resolve.cards.keywords import Protection
    from resolve.effects.characteristics import characteristics
    from resolve.rules import defaults

    recipients = [characteristics(state, obj).abilities for obj, _ in event.to_objects]
    recipients += [defaults.player_abilities(state, player) for player, _ in event.to_players]
    for abilities in recipients:
        for ability in abilities:
            if isinstance(ability, Protection) and ability.quality.matches(source):
                raise NotImplementedRule(
                    "702.16e: preventing damage from a source with a quality a permanent or "
                    "player has protection from (M6)"
                )
