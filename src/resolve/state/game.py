"""The game state: players, cards, objects and zones (design.md §4).

``GameState`` is mutable pure data: tasks change it in place, and AI search clones it with
``copy.deepcopy``. It holds no functions, generators, sets or open files, so a deep copy or a
pickle round-trip at any moment gives an equal, independent state
(``resolve.state.invariants.check_pure_data`` checks this).

Values that never change (``Card``, ``CardData``, ``CardDefinition``, ``Zone``, events, requests)
are ``Immutable``, so copies of a state share them.

Objects are referred to by ``ObjectId`` everywhere outside ``GameState.objects``, never by
reference: an object that changes zones becomes a new object (400.7).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from resolve.cards.registry import CardDefinition
from resolve.data.cards import CardData
from resolve.errors import EngineError, NotImplementedRule
from resolve.state.config import GameConfig
from resolve.state.ids import CardId, ObjectId, PlayerId
from resolve.state.mana import Mana
from resolve.state.rng import Rng
from resolve.state.spell import CastChoices
from resolve.state.turn import TurnState
from resolve.state.zones import Zone, ZoneKind
from resolve.values import Immutable

if TYPE_CHECKING:
    from resolve.decisions.request import DecisionRequest
    from resolve.events.base import LogEntry
    from resolve.state.last_known import LastKnown
    from resolve.tasks import Task


@dataclass(frozen=True)
class Card(Immutable):
    """One physical card in the game.

    ``owner`` is the player who started the game with it in their deck (108.3). ``data`` is its
    printed Oracle data and ``definitions`` its behavior, one definition per face in face order.
    The card's game objects refer to it by ``CardId``.
    """

    id: CardId
    owner: PlayerId
    data: CardData
    definitions: tuple[CardDefinition, ...]


@dataclass(slots=True)
class GameObject:
    """An object (109.1) in some zone.

    - ``card``: the physical card it represents, or ``None`` for tokens, copies and abilities
      (none exist yet).
    - ``owner``: 108.3. ``controller``: set only on the battlefield and the stack (108.4, 109.4).
    - ``timestamp``: received when it entered its zone (613.7d).
    - ``known_to``: players who know its identity although the zone doesn't show it to them
      (400.2), sorted. The owner of a hand always knows its contents (402.3) without being
      listed here.
    - ``tapped``: its status (110.5). Only permanents have status (110.5d); a new object is
      untapped (110.5b).
    - ``damage``: damage marked on it (120.3, 120.6); only permanents have any, and a new object
      has none (400.7).
    - ``spell``: how it is being (or was) cast, for a spell on the stack (601.2, design.md §17.5);
      ``None`` everywhere else.
    - ``cast_record``: for a permanent that was a spell, how that spell was cast (400.7d).
    - ``entered_turn``: for a permanent, the number of the turn during which it came under its
      controller's control: when it entered the battlefield (0: before the first turn). 302.6
      compares it with ``Player.last_turn_began``; a change of control (M5) sets it again.
    """

    id: ObjectId
    card: CardId | None
    owner: PlayerId
    controller: PlayerId | None
    zone: Zone
    timestamp: int
    known_to: tuple[PlayerId, ...] = ()
    tapped: bool = False
    damage: int = 0
    spell: CastChoices | None = None
    cast_record: CastChoices | None = None
    entered_turn: int = 0


@dataclass(slots=True)
class Player:
    """A player (102.1) and their own zones (400.1). The last element of a pile is its top.

    - ``commanders``: the cards designated as this player's commanders (903.3).
    - ``drew_from_empty_library``: the player attempted to draw from an empty library since
      state-based actions were last checked (121.4, 704.5b).
    - ``lost``: the player has lost the game (104.3, 704.5a, 704.5b).
    - ``left_game``: the player has left the game (104.5, 800.4): after losing, or after a draw
      for them. A player who left owns no objects any more (800.4a).
    - ``mana_pool``: unspent mana, one unit per element, in the order it was added (106.4).
    - ``last_turn_began``: the number of this player's most recent turn that began (302.6), or
      ``None`` before their first turn.
    """

    id: PlayerId
    life: int
    commanders: tuple[CardId, ...] = ()
    library: list[ObjectId] = field(default_factory=list[ObjectId])
    hand: list[ObjectId] = field(default_factory=list[ObjectId])
    graveyard: list[ObjectId] = field(default_factory=list[ObjectId])
    drew_from_empty_library: bool = False
    lost: bool = False
    left_game: bool = False
    mana_pool: list[Mana] = field(default_factory=list[Mana])
    last_turn_began: int | None = None


@dataclass(frozen=True)
class GameResult(Immutable):
    """How the game ended (104.1). No winners means a draw (104.4a)."""

    winners: tuple[PlayerId, ...]

    @property
    def is_draw(self) -> bool:
        """Whether the game was a draw (104.4a)."""
        return not self.winners


@dataclass(slots=True)
class GameState:
    """Everything about one game in progress (design.md §4).

    - ``players``: in seating (clockwise) order, with ``players[i].id == i``. Turn order starts
      with ``starting_player`` and proceeds clockwise (103.1).
    - ``cards`` and ``objects``: every physical card in the game, and every object in any zone.
    - ``battlefield``, ``stack``, ``exile``, ``command``: the shared zones. The stack's top is
      its last element (405.2).
    - ``turn``: the turn in progress (500), or ``None`` before the first turn begins (103.8).
    - ``tasks``: the task stack; the last element runs next (design.md §5).
    - ``pending``: the decision the engine is waiting for, if any. ``result``: set when the game
      is over.
    - ``event_log``: everything that happened, with CR citations.
    - ``extra_turns``: the players who will take extra turns before the normal turn order goes
      on, the next one last (500.7: the most recently created turn is taken first).
    - ``turn_direction``: 1 when turn order proceeds clockwise (103.1), -1 when it is reversed.
    - ``last_known``: objects that left the battlefield or the stack as they last existed there,
      by their old IDs (608.2h, ``resolve.state.last_known``).
    """

    config: GameConfig
    seed: int
    rng: Rng
    players: list[Player]
    cards: dict[CardId, Card] = field(default_factory=dict[CardId, Card])
    objects: dict[ObjectId, GameObject] = field(default_factory=dict[ObjectId, GameObject])
    battlefield: list[ObjectId] = field(default_factory=list[ObjectId])
    stack: list[ObjectId] = field(default_factory=list[ObjectId])
    exile: list[ObjectId] = field(default_factory=list[ObjectId])
    command: list[ObjectId] = field(default_factory=list[ObjectId])
    starting_player: PlayerId | None = None
    turn: TurnState | None = None
    tasks: list[Task] = field(default_factory=list["Task"])
    pending: DecisionRequest | None = None
    result: GameResult | None = None
    event_log: list[LogEntry] = field(default_factory=list["LogEntry"])
    next_object_id: int = 1
    next_timestamp: int = 1
    next_request_id: int = 1
    extra_turns: list[PlayerId] = field(default_factory=list[PlayerId])
    turn_direction: int = 1
    last_known: dict[ObjectId, LastKnown] = field(default_factory=dict[ObjectId, "LastKnown"])

    def player(self, player: PlayerId) -> Player:
        """The player with this ID; ``EngineError`` if there is none."""
        if not 0 <= player < len(self.players):
            raise EngineError(f"no player {player!r} in a {len(self.players)}-player game")
        return self.players[player]

    def object(self, obj: ObjectId) -> GameObject:
        """The object with this ID; ``EngineError`` if it doesn't exist (any more)."""
        try:
            return self.objects[obj]
        except KeyError:
            raise EngineError(f"no object {obj!r}") from None

    def card_of(self, obj: GameObject) -> Card:
        """The physical card an object represents; ``EngineError`` for tokens and abilities."""
        if obj.card is None:
            raise EngineError(f"object {obj.id} isn't represented by a card")
        return self.cards[obj.card]


def zone_list(state: GameState, zone: Zone) -> list[ObjectId]:
    """The list holding the contents of ``zone`` (mutable: callers may change it)."""
    match zone.kind:
        case ZoneKind.LIBRARY | ZoneKind.HAND | ZoneKind.GRAVEYARD:
            assert zone.owner is not None
            player = state.player(zone.owner)
            if zone.kind is ZoneKind.LIBRARY:
                return player.library
            return player.hand if zone.kind is ZoneKind.HAND else player.graveyard
        case ZoneKind.BATTLEFIELD:
            return state.battlefield
        case ZoneKind.STACK:
            return state.stack
        case ZoneKind.EXILE:
            return state.exile
        case ZoneKind.COMMAND:
            return state.command


def turn_order(state: GameState) -> tuple[PlayerId, ...]:
    """All players in turn order, starting with the starting player (103.1).

    Turn order proceeds clockwise, which is seating order (103.1); ``GameState.turn_direction``
    is -1 once something reverses it. Every player is included, those who left the game too.
    """
    if state.starting_player is None:
        raise EngineError("turn order isn't defined before the starting player is chosen (103.1)")
    first = state.starting_player
    count = len(state.players)
    step = state.turn_direction
    return tuple(PlayerId((first + step * offset) % count) for offset in range(count))


def is_multiplayer(state: GameState) -> bool:
    """Whether the game began with more than two players (100.1b).

    Seats are never removed, so the number of seats is the number of players the game began with.
    """
    return len(state.players) > 2


def players_in_game(state: GameState) -> tuple[PlayerId, ...]:
    """The players still in the game, in turn order (104.5, 800.4); in seating order before the
    starting player is chosen (103.1)."""
    seats = (
        tuple(p.id for p in state.players) if state.starting_player is None else turn_order(state)
    )
    return tuple(player for player in seats if not state.player(player).left_game)


def apnap_order(state: GameState) -> tuple[PlayerId, ...]:
    """The players still in the game in APNAP order (101.4): the active player first, then the
    others in turn order. Before the first turn the starting player counts as active (101.4e).
    """
    in_game = players_in_game(state)
    active = state.starting_player if state.turn is None else state.turn.active_player
    if active is None:
        return in_game  # before 103.1: seating order
    if active not in in_game:
        # 800.4j: a turn can continue after its active player left; start from the next player.
        if not in_game:
            return ()
        active = next_in_turn_order(state, active)
    start = in_game.index(active)
    return in_game[start:] + in_game[:start]


def next_in_turn_order(state: GameState, player: PlayerId) -> PlayerId:
    """The player after ``player`` in turn order (103.1), among those still in the game.

    ``player`` itself may have left the game; ``EngineError`` if nobody else is still in it.
    """
    count = len(state.players)
    for offset in range(1, count + 1):
        candidate = PlayerId((player + state.turn_direction * offset) % count)
        if candidate != player and not state.player(candidate).left_game:
            return candidate
    raise EngineError(f"no player after player {player} is still in the game")


def new_timestamp(state: GameState) -> int:
    """Allocate the next timestamp (613.7)."""
    timestamp = state.next_timestamp
    state.next_timestamp += 1
    return timestamp


def _destination(owner: PlayerId, zone: Zone, controller: PlayerId | None) -> Zone:
    """The zone an object actually goes to, after checking the move is possible."""
    if zone.kind.is_per_player and zone.owner != owner:
        # 400.3: an object that would go to another player's library, hand or graveyard goes to
        # its owner's instead.
        zone = Zone(zone.kind, owner)
    if zone.kind is ZoneKind.COMMAND and controller is not None:
        raise NotImplementedRule("109.4c: objects with a controller in the command zone (emblems)")
    has_controller = zone.kind in (ZoneKind.BATTLEFIELD, ZoneKind.STACK)
    if has_controller != (controller is not None):
        needs = "need" if has_controller else "have no"
        raise EngineError(f"objects in the {zone} {needs} controller")
    return zone


def create_object(
    state: GameState,
    *,
    card: CardId | None,
    owner: PlayerId,
    zone: Zone,
    controller: PlayerId | None = None,
    bottom: bool = False,
) -> GameObject:
    """Create a new object on top of ``zone`` (or at its bottom), with a new ID and timestamp.

    400.7, 613.7d. A permanent records the turn it entered (``entered_turn``, 302.6). A
    per-player zone of another player means the owner's zone of that kind (400.3).
    """
    zone = _destination(owner, zone, controller)
    obj = GameObject(
        id=ObjectId(state.next_object_id),
        card=card,
        owner=owner,
        controller=controller,
        zone=zone,
        timestamp=new_timestamp(state),
    )
    if zone.kind is ZoneKind.BATTLEFIELD:
        # 302.6: the turn it came under its controller's control (0: before the first turn).
        obj.entered_turn = 0 if state.turn is None else state.turn.number
    state.next_object_id += 1
    state.objects[obj.id] = obj
    if bottom:
        zone_list(state, zone).insert(0, obj.id)
    else:
        zone_list(state, zone).append(obj.id)
    return obj


def move_object(
    state: GameState,
    obj_id: ObjectId,
    zone: Zone,
    *,
    controller: PlayerId | None = None,
    bottom: bool = False,
) -> GameObject:
    """Move an object to the top (or the bottom) of ``zone``; it becomes a new object (400.7).

    The new object has a new ID and timestamp (613.7d) and no memory of the old one: no
    knowledge carries over (an event that moves a card players saw records that itself). An
    object going to another player's library, hand or graveyard goes to its owner's (400.3); one
    put from the command zone into it still becomes a new object (400.10). The old object is
    removed from the game state. Nothing is changed if the move isn't allowed. Only events call
    this.

    An object leaving the battlefield or the stack leaves its last known information behind
    (``GameState.last_known``, 608.2h).
    """
    from resolve.state.last_known import snapshot

    old = state.object(obj_id)
    zone = _destination(old.owner, zone, controller)
    if old.zone.kind in (ZoneKind.BATTLEFIELD, ZoneKind.STACK) and old.card is not None:
        # Objects without a card (copies, abilities on the stack: M4, M5) have no characteristics
        # to compute yet, so their last known information arrives with them.
        state.last_known[obj_id] = snapshot(state, old)
    zone_list(state, old.zone).remove(obj_id)
    del state.objects[obj_id]
    return create_object(
        state, card=old.card, owner=old.owner, zone=zone, controller=controller, bottom=bottom
    )

