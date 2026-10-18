"""Per-player views of the game (design.md §9).

Agents only ever see a ``PlayerView``: a frozen snapshot holding what one player may know.

- **Libraries** appear as a count only (401.3). Library objects keep their IDs through shuffles
  (shuffling isn't a zone change, 400.7), so showing those IDs would reveal where a once-seen card
  went, and the initial IDs follow decklist order.
- **Hands** show the owner their cards (402.3). Other players see stable placeholder IDs with no
  name, and may count them.
- **Public zones** (400.2) show every object.
- **The pending decision**: everyone sees who is deciding and what kind of decision it is; only
  the deciding player gets the request itself.
- **The log**: the entries this player may see, and the redacted form of those hidden from them
  that have one (a draw shows the new hand object but not the library object, design.md §9).

Names are the printed card names. Nothing can change a name yet; once the layer system exists
(M5), views will show characteristics computed through it.
"""

from __future__ import annotations

from dataclasses import dataclass

from resolve.decisions.kinds import DecisionKind
from resolve.decisions.request import DecisionRequest
from resolve.errors import NotImplementedRule
from resolve.events.base import LogEntry
from resolve.state.game import GameObject, GameResult, GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.zones import ZoneKind
from resolve.values import Immutable


@dataclass(frozen=True)
class ObjectView(Immutable):
    """An object as one player sees it; ``name`` is ``None`` when its identity is hidden."""

    id: ObjectId
    name: str | None
    owner: PlayerId
    controller: PlayerId | None


@dataclass(frozen=True)
class PlayerSummary(Immutable):
    """What a viewer can see of one player and their own zones."""

    id: PlayerId
    life: int
    library_size: int
    hand: tuple[ObjectView, ...]
    graveyard: tuple[ObjectView, ...]  # last = top


@dataclass(frozen=True)
class WaitingFor(Immutable):
    """Who the game is waiting for, and for what kind of decision."""

    player: PlayerId
    kind: DecisionKind


@dataclass(frozen=True)
class PlayerView(Immutable):
    """Everything ``viewer`` may know about the game right now."""

    viewer: PlayerId
    players: tuple[PlayerSummary, ...]
    battlefield: tuple[ObjectView, ...]
    stack: tuple[ObjectView, ...]  # last = top
    exile: tuple[ObjectView, ...]
    command: tuple[ObjectView, ...]
    starting_player: PlayerId | None
    waiting_for: WaitingFor | None
    request: DecisionRequest | None  # only when ``viewer`` is the one deciding
    log: tuple[LogEntry, ...]
    result: GameResult | None


def is_known_to(obj: GameObject, viewer: PlayerId) -> bool:
    """Whether ``viewer`` knows the identity of ``obj`` (400.2, 402.3)."""
    if obj.zone.kind.is_public:
        return True
    if obj.zone.kind is ZoneKind.HAND and obj.owner == viewer:
        return True
    return viewer in obj.known_to


def view_for(state: GameState, viewer: PlayerId) -> PlayerView:
    """The game as ``viewer`` may see it."""
    state.player(viewer)  # validates the ID

    def show(ids: list[ObjectId]) -> tuple[ObjectView, ...]:
        return tuple(_object_view(state, state.objects[obj], viewer) for obj in ids)

    pending = state.pending
    return PlayerView(
        viewer=viewer,
        players=tuple(
            PlayerSummary(
                id=player.id,
                life=player.life,
                library_size=len(player.library),
                hand=show(player.hand),
                graveyard=show(player.graveyard),
            )
            for player in state.players
        ),
        battlefield=show(state.battlefield),
        stack=show(state.stack),
        exile=show(state.exile),
        command=show(state.command),
        starting_player=state.starting_player,
        waiting_for=None if pending is None else WaitingFor(pending.player, pending.kind),
        request=pending if pending is not None and pending.player == viewer else None,
        log=tuple(
            shown for entry in state.event_log if (shown := entry.shown_to(viewer)) is not None
        ),
        result=state.result,
    )


def _object_view(state: GameState, obj: GameObject, viewer: PlayerId) -> ObjectView:
    name: str | None = None
    if is_known_to(obj, viewer):
        if obj.card is None:
            raise NotImplementedRule("111.1: viewing objects not represented by a card")
        name = state.cards[obj.card].data.name
    return ObjectView(obj.id, name, obj.owner, obj.controller)
