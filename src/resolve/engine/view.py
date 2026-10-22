"""Per-player views of the game (design.md §9).

Agents only ever see a ``PlayerView``: a frozen snapshot holding what one player may know.

- **Libraries** appear as a count only (401.3). Library objects keep their IDs through shuffles
  (shuffling isn't a zone change, 400.7), so showing those IDs would reveal where a once-seen card
  went, and the initial IDs follow decklist order.
- **Hands** show the owner their cards (402.3). Other players see stable placeholder IDs with no
  name, and may count them. ``defaults.knows_identity`` decides who knows what, including that a
  player's controller knows what they do (723.4).
- **Public zones** (400.2) show every object, and each spell's record on the stack (601.2).
- **The turn**: its number, the active player, the phase and step, and who holds priority are
  public (``TurnView``), as is whether each player has lost or left the game, each mana pool
  (announced when its player passes, 106.4b) and which permanents are tapped.
- **The pending decision**: everyone sees who is deciding and what kind of decision it is; only
  the deciding player gets the request itself.
- **The log**: the entries this player may see, and the redacted form of those hidden from them
  that have one (a draw shows the new hand object but not the library object, design.md §9).

Names are the printed card names. Nothing can change a name yet; once the layer system exists
(M5), views will show characteristics computed through it.
"""

from __future__ import annotations

from dataclasses import dataclass

from resolve.cards.primitives.abilities import ActivatedManaAbility
from resolve.cards.primitives.effects import AddMana, ManaEffect
from resolve.data.mana_cost import ManaCost
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.request import DecisionRequest
from resolve.effects.characteristics import characteristics
from resolve.engine.payment import PayCosts
from resolve.errors import NotImplementedRule
from resolve.events.base import LogEntry
from resolve.rules import defaults
from resolve.state.game import GameObject, GameResult, GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import Mana, ManaRestriction, ManaType, PaymentPurpose
from resolve.state.zones import ZoneKind
from resolve.state.spell import CastChoices
from resolve.state.turn import Phase, Step
from resolve.values import Immutable


@dataclass(frozen=True)
class ManaOutput(Immutable):
    """The mana a mana ability adds (106.1a, 106.3), as it would now: ``fixed`` units of those
    types, or one unit of a type chosen from ``one_of`` as it resolves (106.1a; nothing at all when
    ``one_of`` is empty and ``fixed`` too, 106.5: Command Tower without a commander, 903.4f).
    ``restriction`` is what that mana may be spent on (106.6)."""

    fixed: tuple[ManaType, ...] = ()
    one_of: tuple[ManaType, ...] = ()
    restriction: ManaRestriction | None = None


@dataclass(frozen=True)
class AbilityView(Immutable):
    """An ability of a permanent, as every player sees it (400.2): its position among the
    object's abilities (what an ``ActivateAbilityOption`` names), its text, the mana part of its
    activation cost (602.2b) and, for a mana ability (605.1a), the mana it adds."""

    index: int
    text: str
    mana_cost: ManaCost | None = None
    mana: ManaOutput | None = None


@dataclass(frozen=True)
class PaymentView(Immutable):
    """A cost being paid (601.2g-h, 602.2b), public like the spell or ability it pays for
    (601.2a, 400.2): ``payer`` pays ``cost`` for ``purpose``. ``spendable`` lists the restrictions
    on mana that allow spending it on this payment (106.6), among those of the payer's mana pool
    and of the mana their permanents' mana abilities add; mana with any other restriction can't
    be spent on it."""

    payer: PlayerId
    cost: ManaCost
    purpose: PaymentPurpose
    spendable: tuple[ManaRestriction, ...] = ()


@dataclass(frozen=True)
class ObjectView(Immutable):
    """An object as one player sees it; ``name`` is ``None`` when its identity is hidden.

    ``tapped`` is a permanent's status (110.5) and ``damage`` the damage marked on it (120.6),
    which everyone sees; ``False`` and 0 off the battlefield. ``spell`` is a spell's record on
    the stack: how it is being cast (601.2), public like the stack itself (400.2). Face-down
    spells, whose record only their controller may see (708.5), arrive in M5.
    """

    id: ObjectId
    name: str | None
    owner: PlayerId
    controller: PlayerId | None
    tapped: bool = False
    damage: int = 0
    spell: CastChoices | None = None
    abilities: tuple[AbilityView, ...] = ()


@dataclass(frozen=True)
class PlayerSummary(Immutable):
    """What a viewer can see of one player and their own zones."""

    id: PlayerId
    life: int
    lost: bool
    left_game: bool
    mana_pool: tuple[Mana, ...]
    library_size: int
    hand: tuple[ObjectView, ...]
    graveyard: tuple[ObjectView, ...]  # last = top


@dataclass(frozen=True)
class TurnView(Immutable):
    """The turn in progress, which every player can see (500, 117): ``step`` is ``None`` in a
    main phase, and ``priority`` is ``None`` when nobody holds priority."""

    number: int
    active_player: PlayerId
    phase: Phase
    step: Step | None
    priority: PlayerId | None


@dataclass(frozen=True)
class WaitingFor(Immutable):
    """Who the game is waiting for, and for what kind of decision."""

    player: PlayerId
    kind: DecisionKind
    for_player: PlayerId


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
    turn: TurnView | None
    waiting_for: WaitingFor | None
    request: DecisionRequest | None  # only when ``viewer`` is the one deciding
    log: tuple[LogEntry, ...]
    result: GameResult | None
    payments: tuple[PaymentView, ...] = ()  # outermost first


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
                lost=player.lost,
                left_game=player.left_game,
                mana_pool=tuple(player.mana_pool),
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
        turn=_turn_view(state),
        waiting_for=None
        if pending is None
        else WaitingFor(pending.player, pending.kind, pending.for_player),
        request=pending if pending is not None and pending.player == viewer else None,
        log=tuple(shown for entry in state.event_log if (shown := _shown(state, entry, viewer))),
        result=state.result,
        payments=tuple(
            _payment_view(state, payment)
            for task in state.tasks  # the bottom first: the outermost action
            if (payment := task.payment_under_way()) is not None
        ),
    )


def _payment_view(state: GameState, payment: PayCosts) -> PaymentView:
    """A payment under way, with the restrictions that allow spending mana on it (106.6): those
    of the payer's pool, then those of the mana their permanents' mana abilities add, each
    once, in that order."""
    restrictions: list[ManaRestriction] = []
    candidates = [unit.restriction for unit in state.player(payment.payer).mana_pool]
    for obj in state.battlefield:
        if state.objects[obj].controller == payment.payer:
            for ability in characteristics(state, obj).abilities:
                if isinstance(ability, ActivatedManaAbility) and not isinstance(
                    ability.effect, AddMana
                ):
                    candidates.append(ability.effect.restriction)
    for restriction in candidates:
        if restriction is not None and restriction not in restrictions:
            restrictions.append(restriction)
    return PaymentView(
        payment.payer,
        payment.cost,
        payment.purpose,
        tuple(r for r in restrictions if r.allows(state, payment.purpose)),
    )


def _ability_views(state: GameState, obj: GameObject) -> tuple[AbilityView, ...]:
    """A permanent's abilities (400.2: the battlefield is public); none for other objects."""
    if obj.zone.kind is not ZoneKind.BATTLEFIELD or obj.controller is None:
        return ()
    views: list[AbilityView] = []
    for index, ability in enumerate(characteristics(state, obj.id).abilities):
        if isinstance(ability, ActivatedManaAbility):
            cost = ability.mana_cost
            views.append(
                AbilityView(
                    index,
                    ability.text,
                    None if cost is None else cost.mana,
                    _mana_output(state, obj.id, obj.controller, ability.effect),
                )
            )
        else:
            views.append(AbilityView(index, ability.text))
    return tuple(views)


def _mana_output(
    state: GameState, source: ObjectId, controller: PlayerId, effect: ManaEffect
) -> ManaOutput:
    """The mana ``effect`` would add for ``controller`` now (106.1a, 903.4)."""
    if isinstance(effect, AddMana):
        return ManaOutput(fixed=effect.mana)
    colors = effect.colors(state, source, controller)
    return ManaOutput(
        one_of=tuple(ManaType(color.value) for color in colors), restriction=effect.restriction
    )


def _shown(state: GameState, entry: LogEntry, viewer: PlayerId) -> LogEntry | None:
    """The log entry as ``viewer`` sees it: in full if it is visible to them or, while they
    control another player, to that player (723.4); otherwise as ``LogEntry.shown_to`` gives it."""
    seen = entry.shown_to(viewer)
    if seen is entry:
        return seen
    for other in state.players:
        if (
            other.id != viewer
            and defaults.deciding_player(state, other.id) == viewer
            and entry.is_visible_to(other.id)
        ):
            return entry
    return seen


def _turn_view(state: GameState) -> TurnView | None:
    turn = state.turn
    if turn is None:
        return None
    return TurnView(turn.number, turn.active_player, turn.phase, turn.step, turn.priority)


def _object_view(state: GameState, obj: GameObject, viewer: PlayerId) -> ObjectView:
    name: str | None = None
    abilities: tuple[AbilityView, ...] = ()
    if defaults.knows_identity(state, obj, viewer):
        if obj.card is None:
            raise NotImplementedRule("111.1: viewing objects not represented by a card")
        name = state.cards[obj.card].data.name
        abilities = _ability_views(state, obj)
    return ObjectView(
        obj.id, name, obj.owner, obj.controller, obj.tapped, obj.damage, obj.spell, abilities
    )
