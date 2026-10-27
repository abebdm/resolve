"""Effects (609): what an ability or spell does when it resolves.

Mana abilities' effects (``AddMana``, ``AddManaOfAnyColor``, 605.1a) give their events
directly. Spells' effects are ``Effect`` values (``DealDamage``, ``Destroy``, ``Exile``,
``GainLife``, ``DrawCards``, ``CounterSpell``, ``ReturnToHand``, ``TapAll``), applied one at a time in the order written (608.2c) by
``resolve.engine.resolution.ResolveSpell``; each evaluates its references and values as it
applies (608.2h, ``resolve.effects.evaluation``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.cards.primitives.base import Effect
from resolve.cards.primitives.refs import (
    EachCreature,
    EachOpponent,
    ObjectRef,
    Phrasing,
    PlayerRef,
    TargetRef,
    ThisObject,
    You,
)
from resolve.cards.primitives.values import Fixed, PowerOf, Value, X
from resolve.data.types import CardType, Color
from resolve.events.mana import ManaAdded
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import Mana, ManaRestriction, ManaType
from resolve.values import Immutable

if TYPE_CHECKING:
    from resolve.effects.evaluation import Context
    from resolve.events.base import Event
    from resolve.state.game import GameState
    from resolve.tasks import Task


@dataclass(frozen=True)
class AddMana(Immutable):
    """ "Add [mana]": the controller adds this mana to their mana pool (106.3, 106.4).

    The mana's source is the object whose ability produced it (106.3).
    """

    mana: tuple[ManaType, ...]

    def __post_init__(self) -> None:
        if not self.mana:
            raise ValueError("AddMana needs at least one mana")

    def events(self, state: GameState, source: ObjectId, player: PlayerId) -> tuple[Event, ...]:
        """The events of this effect, for ``player`` resolving ``source``'s ability."""
        added = tuple(Mana(mana_type, source) for mana_type in self.mana)
        return (ManaAdded(player=player, mana=added, rules=("106.3", "106.4")),)

    @property
    def text(self) -> str:
        """The effect as printed, such as ``"Add {G}."``."""
        return "Add " + "".join(mana_type.symbol for mana_type in self.mana) + "."


@dataclass(frozen=True)
class AddManaOfAnyColor(Immutable):
    """ "Add one mana of any color" (106.1a, 106.3), with the color chosen as the ability resolves.

    - ``commander_identity``: "... of any color in your commander's color identity" (903.4): only
      the colors of the identity of the controller's commanders (combined, if they have two). With
      no commander that quality is undefined (903.4f), and a commander whose identity has no
      color gives no color to choose: either way the ability adds no mana (106.5; Command Tower's
      and Arcane Signet's rulings), but it is still activated and its costs still paid.
    - ``restriction``: what the mana may be spent on (106.6), such as Ixalli's Lorekeeper's.

    ``colors`` lists the colors the controller may choose, in WUBRG order (105.1); the engine asks
    only when there are two or more (``CHOOSE_COLOR``).
    """

    commander_identity: bool = False
    restriction: ManaRestriction | None = None

    def colors(self, state: GameState, source: ObjectId, player: PlayerId) -> tuple[Color, ...]:
        """The colors ``player`` may choose for this mana now (903.4, 903.4f)."""
        if not self.commander_identity:
            return tuple(Color)
        from resolve.rules.commander import commander_color_identity

        return commander_color_identity(state, player) or ()  # 903.4f: undefined, no color

    def events(
        self, state: GameState, source: ObjectId, player: PlayerId, color: Color | None
    ) -> tuple[Event, ...]:
        """The events of this effect with ``color`` chosen; none if no color could be (106.5)."""
        if color is None:
            return ()
        mana = Mana(ManaType(color.value), source, self.restriction)
        return (ManaAdded(player=player, mana=(mana,), rules=("106.1a", "106.3", "106.4")),)

    @property
    def text(self) -> str:
        """The effect as printed, such as ``"Add one mana of any color."``."""
        text = "Add one mana of any color"
        text += " in your commander's color identity." if self.commander_identity else "."
        return text if self.restriction is None else f"{text} {self.restriction.text}"


ManaEffect = AddMana | AddManaOfAnyColor
"""What a mana ability's effect can be (605.1a)."""


# --- Effects of spells (609) -------------------------------------------------------------------

_THIS_OBJECT = ThisObject()
_YOU = You()
_ONE = Fixed(1)


@dataclass(frozen=True)
class DealDamage(Effect):
    """ "[Source] deals [amount] damage to [recipients]" (120.2b): one damage event, the amount
    evaluated as it applies (608.2h), dealt by ``source`` (the spell itself, or an object it
    names: "target creature you control deals damage", 120.1) to every recipient at once.

    Recipients are references (targets) and groups (``EachCreature``, ``EachOpponent``), each
    object or player once. Damage can only be dealt to a creature, planeswalker or battle
    (120.1a) or a player still in the game (800.4a). 120.8: 0 damage isn't dealt at all, and
    107.1b: a negative amount is 0. Its results (120.3) are the event's (``DamageDealt``).
    """

    amount: Value
    to: tuple[DamageRecipient, ...]
    source: ObjectRef = _THIS_OBJECT

    def __post_init__(self) -> None:
        if not self.to:
            raise ValueError("DealDamage needs at least one recipient")

    def tasks(self, state: GameState, context: Context) -> tuple[Task, ...]:
        from resolve.effects import evaluation
        from resolve.events.damage import DamageDealt
        from resolve.events.pipeline import ApplyEvents

        sources = evaluation.objects(state, self.source, context)
        amount = evaluation.evaluate(state, self.amount, context)
        if not sources or amount is None:
            return ()  # 608.2b: information about an illegal target can't be determined
        amount = max(amount, 0)  # 107.1b
        if amount == 0:
            return ()  # 120.8
        objects: list[ObjectId] = []
        players: list[PlayerId] = []
        for recipient in self.to:
            found_objects, found_players = _recipients(state, recipient, context)
            objects += [obj for obj in found_objects if obj not in objects]
            players += [player for player in found_players if player not in players]
        if not objects and not players:
            return ()
        (source,) = sources
        event = DamageDealt(
            source=source,
            to_objects=tuple((obj, amount) for obj in objects),
            to_players=tuple((player, amount) for player in players),
            rules=("120.2b", "120.3"),
        )
        return (ApplyEvents((event,)),)

    def describe(self, phrasing: Phrasing) -> str:
        """``"this spell deals 2 damage to any target"``, ``"target creature you control deals
        damage equal to its power to each other creature and each opponent"``."""
        source = phrasing.object(self.source)
        match self.amount:
            case Fixed(value=number):
                amount = f"{number} damage"
            case X():
                amount = "X damage"
            case PowerOf() as power:
                amount = f"damage equal to {power.describe(phrasing)}"
        recipients = [_recipient_text(r, self.source, phrasing) for r in self.to]
        return f"{source} deals {amount} to {_listed(recipients)}"


@dataclass(frozen=True)
class Destroy(Effect):
    """ "Destroy [objects]" (701.8a): each permanent referred to, once even if several
    references name it (Decimate's shared target), moves to its owner's graveyard, all at once.
    A permanent that can't be destroyed (``legality.allowed(DestroyAction)``: indestructible,
    702.12b, M2.8) stays."""

    objects: tuple[ObjectRef, ...]

    def __post_init__(self) -> None:
        if not self.objects:
            raise ValueError("Destroy needs at least one object")

    def tasks(self, state: GameState, context: Context) -> tuple[Task, ...]:
        from resolve.events.permanents import PermanentDestroyed
        from resolve.events.pipeline import ApplyEvents
        from resolve.rules import legality

        events = [
            PermanentDestroyed(obj=obj, rules=("701.8a",))
            for obj in _permanents(state, self.objects, context)
            if legality.allowed(state, legality.DestroyAction(context.controller, obj)).allowed
        ]
        return (ApplyEvents(tuple(events)),) if events else ()

    def describe(self, phrasing: Phrasing) -> str:
        """``"destroy target artifact, target creature, target enchantment, and target land"``."""
        return "destroy " + _listed([phrasing.object(ref) for ref in self.objects], comma=True)


@dataclass(frozen=True)
class Exile(Effect):
    """ "Exile [objects]" (701.13a): each object referred to moves to the exile zone, as a new
    object (400.7), all at once."""

    objects: tuple[ObjectRef, ...]

    def __post_init__(self) -> None:
        if not self.objects:
            raise ValueError("Exile needs at least one object")

    def tasks(self, state: GameState, context: Context) -> tuple[Task, ...]:
        from resolve.effects import evaluation
        from resolve.events.permanents import ObjectExiled
        from resolve.events.pipeline import ApplyEvents

        found: list[ObjectId] = []
        for ref in self.objects:
            found += [o for o in evaluation.objects(state, ref, context) if o not in found]
        events = [
            ObjectExiled(obj=obj, rules=("701.13a",)) for obj in found if obj in state.objects
        ]
        return (ApplyEvents(tuple(events)),) if events else ()

    def describe(self, phrasing: Phrasing) -> str:
        """``"exile target creature"``."""
        return "exile " + _listed([phrasing.object(ref) for ref in self.objects])


@dataclass(frozen=True)
class GainLife(Effect):
    """ "[Player] gains [amount] life" (119.3): the amount evaluated as it applies (608.2h; 0 if
    negative, 107.1b). Gaining 0 life is no life gain event at all (119.10)."""

    player: PlayerRef
    amount: Value

    def tasks(self, state: GameState, context: Context) -> tuple[Task, ...]:
        from resolve.effects import evaluation
        from resolve.events.life import LifeGained
        from resolve.events.pipeline import ApplyEvents

        amount = evaluation.evaluate(state, self.amount, context)
        if amount is None or amount <= 0:
            return ()  # 608.2b; 107.1b; 119.10
        gainers = evaluation.players(state, self.player, context)
        events = [LifeGained(player=p, amount=amount, rules=("119.3",)) for p in gainers]
        return (ApplyEvents(tuple(events)),) if events else ()

    def describe(self, phrasing: Phrasing) -> str:
        """``"its controller gains life equal to its power"``, ``"you gain 3 life"``."""
        player = phrasing.player(self.player)
        verb = "gain" if player == "you" else "gains"
        match self.amount:
            case Fixed(value=number):
                return f"{player} {verb} {number} life"
            case X():
                return f"{player} {verb} X life"
            case PowerOf() as power:
                return f"{player} {verb} life equal to {power.describe(phrasing)}"


@dataclass(frozen=True)
class DrawCards(Effect):
    """ "[Player] draws [count] cards" (121.1): each player referred to draws, one card at a time
    (121.2), the count evaluated as it applies (608.2h; 0 if negative, 107.1b)."""

    count: Value = _ONE
    player: PlayerRef = _YOU

    def tasks(self, state: GameState, context: Context) -> tuple[Task, ...]:
        from resolve.effects import evaluation
        from resolve.engine.drawing import DrawCards as Draw

        count = evaluation.evaluate(state, self.count, context)
        if count is None or count <= 0:
            return ()
        players = evaluation.players(state, self.player, context)
        return tuple(Draw(player, count, ("121.1", "121.2")) for player in players)

    def describe(self, phrasing: Phrasing) -> str:
        """``"draw a card"``, ``"target player draws two cards"``."""
        player = phrasing.player(self.player)
        match self.count:
            case Fixed(value=1):
                cards = "a card"
            case Fixed() | X() as count:
                cards = f"{count.word} cards"
            case PowerOf() as power:
                cards = f"cards equal to {power.describe(phrasing)}"
        return f"draw {cards}" if player == "you" else f"{player} draws {cards}"


@dataclass(frozen=True)
class CounterSpell(Effect):
    """ "Counter [spells]" (701.6a): each spell referred to that is still on the stack is removed
    from it and put into its owner's graveyard (``SpellCountered``); it doesn't resolve and none
    of its effects happen, and its costs aren't refunded (701.6b). A spell that can't be
    countered (``legality.allowed(CounterAction)``: 113.6g, ``CantBeCountered``) stays, though
    it could be targeted (101.2)."""

    spells: tuple[ObjectRef, ...]

    def __post_init__(self) -> None:
        if not self.spells:
            raise ValueError("CounterSpell needs at least one spell")

    def tasks(self, state: GameState, context: Context) -> tuple[Task, ...]:
        from resolve.errors import NotImplementedRule

        raise NotImplementedRule("701.6a: countering a spell")

    def describe(self, phrasing: Phrasing) -> str:
        """``"counter target spell"``."""
        return "counter " + _listed([phrasing.object(ref) for ref in self.spells])


@dataclass(frozen=True)
class ReturnToHand(Effect):
    """ "Return [permanents] to [their] owner's hand": each permanent referred to moves to its
    owner's hand (400.3: a card goes only to its owner's hand), as a new object (400.7), all at
    once."""

    objects: tuple[ObjectRef, ...]

    def __post_init__(self) -> None:
        if not self.objects:
            raise ValueError("ReturnToHand needs at least one object")

    def tasks(self, state: GameState, context: Context) -> tuple[Task, ...]:
        from resolve.errors import NotImplementedRule

        raise NotImplementedRule("400.3: returning a permanent to its owner's hand")

    def describe(self, phrasing: Phrasing) -> str:
        """``"return target permanent to its owner's hand"``."""
        (ref,) = self.objects
        return f"return {phrasing.object(ref)} to {phrasing.possessive(ref)} owner's hand"


@dataclass(frozen=True)
class TapAll(Effect):
    """ "Tap all [creatures]" (701.26a): every permanent of the group when the effect applies
    (608.2h) that is untapped becomes tapped, all at once; one already tapped stays as it is
    (701.26a: only an untapped permanent can become tapped). Not targeted (115.10)."""

    group: EachCreature

    def tasks(self, state: GameState, context: Context) -> tuple[Task, ...]:
        from resolve.errors import NotImplementedRule

        raise NotImplementedRule("701.26a: tapping a group of permanents")

    def describe(self, phrasing: Phrasing) -> str:
        """``"tap all creatures your opponents control"``."""
        group = self.group
        noun = "all creatures" if group.except_ is None else "all other creatures"
        match group.controlled_by:
            case None:
                return f"tap {noun}"
            case You():
                return f"tap {noun} you control"
            case EachOpponent():
                return f"tap {noun} your opponents control"


DamageRecipient = TargetRef | EachCreature | EachOpponent
"""Who or what damage may be dealt to."""


def _recipients(
    state: GameState, recipient: DamageRecipient, context: Context
) -> tuple[tuple[ObjectId, ...], tuple[PlayerId, ...]]:
    """The permanents (120.1a: creatures, planeswalkers and battles only) and players still in
    the game (800.4a) a recipient stands for now."""
    from resolve.effects import evaluation

    match recipient:
        case TargetRef():
            objects = evaluation.objects(state, recipient, context)
            players = evaluation.players(state, recipient, context)
        case EachCreature():
            objects = evaluation.each_creature(state, recipient, context)
            players = ()
        case EachOpponent():
            objects = ()
            players = evaluation.each_opponent(state, recipient, context)
    return tuple(obj for obj in objects if _can_be_dealt_damage(state, obj)), players


def _can_be_dealt_damage(state: GameState, obj: ObjectId) -> bool:
    """120.1a: only a battle, creature or planeswalker on the battlefield can be dealt damage."""
    from resolve.effects.characteristics import characteristics
    from resolve.state.zones import ZoneKind

    game_object = state.objects.get(obj)
    if game_object is None or game_object.zone.kind is not ZoneKind.BATTLEFIELD:
        return False
    types = characteristics(state, obj).card_types
    return any(t in types for t in (CardType.BATTLE, CardType.CREATURE, CardType.PLANESWALKER))


def _permanents(
    state: GameState, refs: tuple[ObjectRef, ...], context: Context
) -> tuple[ObjectId, ...]:
    """The permanents the references name, each once, in the order named."""
    from resolve.effects import evaluation
    from resolve.state.zones import ZoneKind

    found: list[ObjectId] = []
    for ref in refs:
        for obj in evaluation.objects(state, ref, context):
            game_object = state.objects.get(obj)
            if obj in found or game_object is None:
                continue
            if game_object.zone.kind is ZoneKind.BATTLEFIELD:
                found.append(obj)
    return tuple(found)


def _recipient_text(recipient: DamageRecipient, source: ObjectRef, phrasing: Phrasing) -> str:
    match recipient:
        case TargetRef():
            return phrasing.object(recipient)
        case EachCreature(except_=None):
            return "each creature"
        case EachCreature(except_=excepted) if excepted == source:
            return "each other creature"
        case EachCreature(except_=excepted):
            assert excepted is not None
            return f"each creature other than {phrasing.object(excepted)}"
        case EachOpponent():
            return "each opponent"


def _listed(items: list[str], *, comma: bool = False) -> str:
    """``"a"``, ``"a and b"``, ``"a, b, and c"`` (with ``comma``, the serial comma card text uses
    for long lists)."""
    if len(items) <= 2:
        return " and ".join(items)
    return ", ".join(items[:-1]) + ("," if comma else "") + " and " + items[-1]
