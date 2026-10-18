"""514: the cleanup step, with 402.2 (maximum hand size).

From the pinned CR:

- 514.1: if the active player's hand holds more cards than their maximum hand size, they discard
  enough cards to reduce it to that number. 402.2: the maximum hand size is normally seven, so
  the starting hand size (103.5) doesn't change it. Only the active player discards.
- 701.9a: discarding moves the card from its owner's hand to their graveyard; 701.9b: the
  player chooses which. 404.3: cards put into a graveyard at the same time are arranged by
  their owner (asked as ``ORDER_CARDS``, listed top to bottom). A discarded card becomes a new
  object (400.7) in a public zone, so every player sees it.
- 514.3: normally no player receives priority in the cleanup step.
"""

from __future__ import annotations

import copy

import pytest

from resolve.agents.scripted import choose
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.request import DecisionAnswer
from resolve.decisions.spaces import ChooseSubset, ObjectOption, Order, PassOption, PickMany
from resolve.engine.api import submit, view_for
from resolve.errors import InvalidAnswer
from resolve.events.cards import CardDiscarded
from resolve.state.config import GameConfig
from resolve.state.ids import PlayerId
from resolve.state.turn import Phase, Step
from resolve.state.zones import Zone
from tests.game_fixtures import request_of
from tests.scenario import Scenario, names, run_script

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)

NINE = ["Forest", "Llanowar Elves", "Forest", "Test Shock", "Forest", "Forest", "Test Ponder",
        "Forest", "Forest"]  # fmt: skip


def cleanup(players: int = 2, *, config: GameConfig | None = None) -> Scenario:
    scenario = Scenario(players, config=config)
    for player in scenario.players:
        scenario.library(player, ["Forest"] * 3)
    return scenario


def test_514_1_the_active_player_discards_down_to_seven() -> None:
    scenario = cleanup()
    hand = scenario.hand(P0, NINE)
    scenario.at(Step.CLEANUP)
    state = scenario.build()
    request = request_of(state)
    assert request.kind is DecisionKind.DISCARD and request.player == P0
    assert request.rules == ("514.1", "402.2")
    assert request.space == ChooseSubset(tuple(ObjectOption(o) for o in hand), 2, 2)
    # Discard the Test Shock and the Llanowar Elves; the Shock goes on top (listed first),
    # which is the reverse of their order in the hand (404.3: the owner's order counts).
    run_script(
        state,
        choose(ObjectOption(hand[3]), ObjectOption(hand[1]), kind=DecisionKind.DISCARD),
        choose(ObjectOption(hand[3]), ObjectOption(hand[1]), kind=DecisionKind.ORDER_CARDS),
    )
    assert len(state.player(P0).hand) == 7
    assert names(state, Zone.graveyard(P0)) == ["Llanowar Elves", "Test Shock"]  # top last
    entries = [e for e in state.event_log if isinstance(e.record, CardDiscarded)]
    discards = [e.record for e in entries if isinstance(e.record, CardDiscarded)]
    assert [d.card for d in discards] == [hand[1], hand[3]]  # bottom first
    assert all(e.visible_to is None for e in entries)  # public
    assert all(d.rules == ("514.1", "701.9a") for d in discards)
    assert [d.discarded for d in discards] == state.player(P0).graveyard  # 400.7
    # The cleanup step is over and the next turn has begun (514.3: no priority in cleanup).
    turn = state.turn
    assert turn is not None and (turn.number, turn.active_player) == (2, P1)
    for viewer in (P0, P1):  # the graveyard is public (404.2)
        graveyard = view_for(state, viewer).players[0].graveyard
        assert [obj.name for obj in graveyard] == ["Llanowar Elves", "Test Shock"]


def test_514_1_one_card_to_discard_asks_no_order() -> None:
    scenario = cleanup()
    hand = scenario.hand(P0, NINE[:8])
    scenario.at(Step.CLEANUP)
    state = scenario.build()
    run_script(state, choose(ObjectOption(hand[0]), kind=DecisionKind.DISCARD))
    assert names(state, Zone.graveyard(P0)) == ["Forest"]
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION  # turn 2's upkeep


def test_514_1_only_the_active_player_discards() -> None:
    scenario = cleanup(3)
    scenario.hand(P0, NINE[:7])
    scenario.hand(P1, NINE)
    scenario.hand(P2, NINE)
    scenario.at(Step.CLEANUP)
    state = scenario.build()
    request = request_of(state)
    assert request.kind is DecisionKind.PRIORITY_ACTION
    turn = state.turn
    assert turn is not None and (turn.number, turn.step) == (2, Step.UPKEEP)
    assert [len(state.player(p).hand) for p in (P1, P2)] == [9, 9]


def test_514_1_exactly_seven_cards_discards_nothing() -> None:
    scenario = cleanup()
    scenario.hand(P0, NINE[:7])
    scenario.at(Step.CLEANUP)
    state = scenario.build()
    assert len(state.player(P0).hand) == 7
    assert state.player(P0).graveyard == []
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION


def test_402_2_the_maximum_hand_size_is_seven_whatever_the_starting_hand_size() -> None:
    scenario = cleanup(config=GameConfig(starting_hand_size=5))
    scenario.hand(P0, NINE[:6])
    scenario.at(Step.CLEANUP)
    state = scenario.build()
    assert len(state.player(P0).hand) == 6
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION


def test_402_2_a_large_starting_hand_size_still_discards_to_seven() -> None:
    scenario = cleanup(config=GameConfig(starting_hand_size=9))
    scenario.hand(P0, NINE)
    scenario.at(Step.CLEANUP)
    state = scenario.build()
    request = request_of(state)
    assert request.kind is DecisionKind.DISCARD
    assert isinstance(request.space, ChooseSubset) and request.space.minimum == 2


@pytest.mark.parametrize("indices", [(0,), (0, 1, 2), ()])
def test_514_1_the_wrong_number_of_discards_is_rejected(indices: tuple[int, ...]) -> None:
    scenario = cleanup()
    scenario.hand(P0, NINE)
    scenario.at(Step.CLEANUP)
    state = scenario.build()
    request = request_of(state)
    before = copy.deepcopy(state)
    with pytest.raises(InvalidAnswer):
        submit(state, DecisionAnswer(request.id, P0, PickMany(indices)))
    assert state == before


def test_514_cleanup_begins_after_the_end_step() -> None:
    scenario = cleanup()
    scenario.hand(P0, NINE)
    scenario.at(Step.END)
    state = scenario.build()
    run_script(state, choose(PassOption(), player=P0), choose(PassOption(), player=P1))
    turn = state.turn
    assert turn is not None and (turn.phase, turn.step) == (Phase.ENDING, Step.CLEANUP)
    assert request_of(state).kind is DecisionKind.DISCARD


def test_404_3_the_other_order_puts_the_other_card_on_top() -> None:
    scenario = cleanup()
    hand = scenario.hand(P0, NINE)
    scenario.at(Step.CLEANUP)
    state = scenario.build()
    run_script(
        state,
        choose(ObjectOption(hand[3]), ObjectOption(hand[1]), kind=DecisionKind.DISCARD),
        choose(ObjectOption(hand[1]), ObjectOption(hand[3]), kind=DecisionKind.ORDER_CARDS),
    )
    assert names(state, Zone.graveyard(P0)) == ["Test Shock", "Llanowar Elves"]  # top last


def test_514_cleanup_decisions_reject_invalid_answers() -> None:
    scenario = cleanup()
    scenario.hand(P0, NINE)
    scenario.at(Step.CLEANUP)
    state = scenario.build()
    request = request_of(state)
    before = copy.deepcopy(state)
    for bad in (
        DecisionAnswer(request.id, P1, PickMany((0, 1))),  # only the active player discards
        DecisionAnswer(request.id, P0, PickMany((1, 1))),  # a repeated card
        DecisionAnswer(request.id, P0, PickMany((0, 9))),  # out of range
    ):
        with pytest.raises(InvalidAnswer):
            submit(state, bad)
        assert state == before
    submit(state, DecisionAnswer(request.id, P0, PickMany((0, 1))))
    order = request_of(state)
    assert order.kind is DecisionKind.ORDER_CARDS and order.rules == ("404.3",)
    before = copy.deepcopy(state)
    for permutation in ((0, 0), (0,), (0, 1, 2)):
        with pytest.raises(InvalidAnswer):
            submit(state, DecisionAnswer(order.id, P0, Order(permutation)))
        assert state == before


def test_514_3a_a_state_based_action_in_cleanup_is_performed_in_that_cleanup() -> None:
    """514.3a: the game checks state-based actions in the cleanup step; player 1 at 0 life
    loses there (704.5a), not in the next turn."""
    scenario = cleanup()
    scenario.life(P1, 0)
    scenario.at(Step.CLEANUP)
    state = scenario.build()
    assert state.result is not None and state.result.winners == (P0,)
    turn = state.turn
    assert turn is not None and (turn.number, turn.step) == (1, Step.CLEANUP)
    assert not any(type(e.record).__name__ == "TurnBegan" for e in state.event_log)


def test_514_3a_discarding_comes_before_the_state_based_actions() -> None:
    scenario = cleanup()
    hand = scenario.hand(P0, NINE)
    scenario.life(P1, 0)
    scenario.at(Step.CLEANUP)
    state = scenario.build()
    assert state.result is None
    assert request_of(state).kind is DecisionKind.DISCARD  # 514.1 first
    run_script(
        state,
        choose(ObjectOption(hand[0]), ObjectOption(hand[2])),
        choose(ObjectOption(hand[0]), ObjectOption(hand[2])),
    )
    assert state.result is not None and state.result.winners == (P0,)
    turn = state.turn
    assert turn is not None and turn.step is Step.CLEANUP
