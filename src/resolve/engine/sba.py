"""State-based actions (704) and the end of the game they can bring (104).

``state_based_actions(state)`` lists the state-based actions that would be performed right now,
as events. ``CheckStateBasedActions`` performs them all at once, as a single event (704.3), then
checks again, until a check performs nothing. The state-based actions implemented so far:

- 704.5a: a player with 0 or less life loses the game.
- 704.5b: a player who attempted to draw from an empty library since the last check loses.
- 704.5f: a creature with 0 or less toughness is put into its owner's graveyard.
- 704.5g: a creature with toughness above 0 and lethal damage marked on it is destroyed.

A player who loses leaves the game (104.5). ``EndCheck`` then ends the game if at most one
player is left: the last player in the game wins (104.2a), and if none is left the game is a
draw (104.4a). A game that continues after a player leaves (800.4) is not implemented yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from resolve.data.types import CardType
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import AnswerValue, ChooseOrder, ObjectOption, Order
from resolve.effects.characteristics import characteristics
from resolve.errors import EngineError, NotImplementedRule
from resolve.events.base import Event
from resolve.events.game import GameEnded, PlayerLost
from resolve.events.permanents import PermanentDestroyed, PutIntoGraveyard
from resolve.events.pipeline import ApplyEvents
from resolve.state.game import apnap_order, players_in_game
from resolve.state.ids import ObjectId, PlayerId
from resolve.tasks import Done, NeedDecision, Push, Task, TaskResult

if TYPE_CHECKING:
    from resolve.decisions.request import DecisionRequest
    from resolve.state.game import GameState


def state_based_actions(state: GameState) -> tuple[Event, ...]:
    """The state-based actions to perform now (704.3): creatures first, in battlefield order,
    then players in APNAP order.

    Every condition is checked before anything is performed, so they happen simultaneously.
    """
    events: list[Event] = []
    for obj in state.battlefield:
        chars = characteristics(state, obj)
        if not chars.is_a(CardType.CREATURE):
            continue
        toughness = chars.toughness or 0  # 208.5: no value counts as 0
        if toughness <= 0:
            events.append(PutIntoGraveyard(obj=obj, rules=("704.5f", "704.3")))
        elif state.objects[obj].damage > 0 and toughness <= state.objects[obj].damage:
            events.append(PermanentDestroyed(obj=obj, rules=("704.5g", "120.6", "701.8a")))
    for player_id in apnap_order(state):
        player = state.player(player_id)
        if player.life <= 0:
            events.append(PlayerLost(player=player_id, rules=("704.5a", "704.3")))
        elif player.drew_from_empty_library:
            events.append(PlayerLost(player=player_id, rules=("704.5b", "121.4", "704.3")))
    return tuple(events)


def _moved(event: Event) -> ObjectId | None:
    if isinstance(event, PutIntoGraveyard | PermanentDestroyed):
        return event.obj
    return None


@dataclass(slots=True)
class CheckStateBasedActions(Task):
    """704.3: perform every applicable state-based action as one event; repeat until none apply.

    When two or more cards go to one player's graveyard together, their owner orders them first
    (404.3, ``ORDER_CARDS``, listed top to bottom), owners asked in APNAP order. ``events`` holds
    the check's state-based actions while orders are asked; ``orders`` the answers so far.

    Triggered abilities waiting to be put on the stack would go on it between checks (704.3);
    none can exist until M4.
    """

    events: tuple[Event, ...] = ()
    orders: dict[PlayerId, tuple[ObjectId, ...]] = field(
        default_factory=dict[PlayerId, tuple[ObjectId, ...]]
    )

    def run(self, state: GameState) -> TaskResult:
        if not self.events:
            self.events = state_based_actions(state)
            self.orders.clear()
            if not self.events:
                return Done()
        for owner, cards in self._to_order(state):
            if owner not in self.orders:
                return NeedDecision(
                    player=owner,
                    kind=DecisionKind.ORDER_CARDS,
                    space=ChooseOrder(tuple(ObjectOption(obj) for obj in cards)),
                    prompt="Order the cards going to your graveyard, from top to bottom.",
                    rules=("404.3",),
                )
        events = self._ordered(state)
        self.events = ()
        self.orders.clear()
        tasks: list[Task] = [ApplyEvents(events)]
        if any(isinstance(event, PlayerLost) for event in events):
            tasks.append(EndCheck())
        return Push((*tasks, self))

    def resume(self, state: GameState, request: DecisionRequest, answer: AnswerValue) -> TaskResult:
        if not isinstance(request.space, ChooseOrder) or not isinstance(answer, Order):
            raise EngineError(f"CheckStateBasedActions can't resume with {answer!r}")
        chosen = request.space.chosen(answer)
        self.orders[request.player] = tuple(
            option.object for option in chosen if isinstance(option, ObjectOption)
        )
        return self.run(state)

    def _to_order(self, state: GameState) -> list[tuple[PlayerId, tuple[ObjectId, ...]]]:
        by_owner: dict[PlayerId, list[ObjectId]] = {}
        for event in self.events:
            obj = _moved(event)
            if obj is not None:
                by_owner.setdefault(state.objects[obj].owner, []).append(obj)
        return [
            (owner, tuple(by_owner[owner]))
            for owner in apnap_order(state)
            if len(by_owner.get(owner, ())) > 1
        ]

    def _ordered(self, state: GameState) -> tuple[Event, ...]:
        """The events, with each ordered owner's cards applied bottom first, so the card listed
        first ends up on top."""
        position: dict[ObjectId, int] = {}
        for cards in self.orders.values():
            for index, obj in enumerate(cards):
                position[obj] = len(cards) - index
        moves = [e for e in self.events if _moved(e) is not None]
        others = [e for e in self.events if _moved(e) is None]
        moves.sort(key=lambda e: position.get(_moved(e) or ObjectId(0), 0))
        return (*moves, *others)


@dataclass(slots=True)
class EndCheck(Task):
    """After players lose (104.5): end the game if at most one player is still in it."""

    def run(self, state: GameState) -> TaskResult:
        remaining = players_in_game(state)
        if len(remaining) == 1:
            return Push((ApplyEvents((GameEnded(winners=remaining, rules=("104.2a",)),)),))
        if not remaining:
            return Push((ApplyEvents((GameEnded(winners=(), rules=("104.4a",)),)),))
        raise NotImplementedRule(
            "800.4a: a player leaving a game that other players continue (roadmap M1.5)"
        )
