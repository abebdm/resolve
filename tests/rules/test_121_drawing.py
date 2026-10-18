"""121: drawing cards.

- 121.1: a player draws a card by putting the top card of their library into their hand.
- 121.2: cards are drawn one at a time; "draw N" is N individual draws.
- 121.4: a player who attempts to draw from an empty library loses the next time a player would
  receive priority (704.5b). Drawing itself only records the attempt; the loss is a state-based
  action (tested with the turn structure).
- 400.7: the drawn card becomes a new object in the hand.
- design.md §9: other players don't learn which library object was drawn.
"""

from __future__ import annotations

from resolve.engine.api import view_for
from resolve.engine.drawing import DrawCards
from resolve.events.cards import CardDrawn
from resolve.state.game import GameState
from resolve.state.ids import PlayerId
from resolve.state.zones import Zone
from tests.engine_support import Hold, holding
from tests.scenario import Scenario, names

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)


def drawn(state: GameState) -> list[CardDrawn]:
    return [e.record for e in state.event_log if isinstance(e.record, CardDrawn)]


def test_121_1_a_draw_puts_the_top_card_of_the_library_into_the_hand() -> None:
    scenario = Scenario(2)
    top, under = scenario.library(P0, ["Forest", "Llanowar Elves"])
    state = scenario.build(DrawCards(P0, 1, ("121.1",)), Hold())
    assert holding(state)
    assert names(state, Zone.hand(P0)) == ["Forest"]
    assert state.players[0].library == [under]
    assert top not in state.objects, "the drawn card is a new object (400.7)"
    (event,) = drawn(state)
    assert event.drawn_from == top
    assert event.drawn == state.players[0].hand[0]
    assert not event.empty_library


def test_121_2_drawing_several_cards_is_that_many_individual_draws_from_the_top() -> None:
    scenario = Scenario(2)
    a, b, c = scenario.library(P0, ["Forest", "Llanowar Elves", "Forest"])
    state = scenario.build(DrawCards(P0, 2, ("121.2",)), Hold())
    assert [event.drawn_from for event in drawn(state)] == [a, b]
    assert names(state, Zone.hand(P0)) == ["Forest", "Llanowar Elves"]
    assert state.players[0].library == [c]
    assert state.players[1].hand == []


def test_121_4_drawing_from_an_empty_library_draws_nothing_and_is_remembered() -> None:
    state = Scenario(2).build(DrawCards(P1, 1, ("121.1",)), Hold())
    assert state.players[1].hand == []
    assert state.players[1].drew_from_empty_library
    assert not state.players[0].drew_from_empty_library
    (event,) = drawn(state)
    assert event.empty_library and event.drawn is None and event.drawn_from is None
    assert "121.4" in event.rules
    assert state.event_log[-1].visible_to is None, "an empty library hides nothing"
    assert state.result is None, "the loss waits for a state-based action check (704.5b)"


def test_121_4_drawing_more_cards_than_the_library_holds_draws_the_rest() -> None:
    """104.3c: the player draws the remaining cards (and loses later, as a state-based action)."""
    scenario = Scenario(2)
    scenario.library(P0, ["Forest"])
    state = scenario.build(DrawCards(P0, 3, ("121.2",)), Hold())
    assert names(state, Zone.hand(P0)) == ["Forest"]
    assert [event.empty_library for event in drawn(state)] == [False, True, True]
    assert state.players[0].drew_from_empty_library


def test_121_draws_are_seen_in_full_only_by_the_drawing_player() -> None:
    scenario = Scenario(3)
    (top,) = scenario.library(P1, ["Llanowar Elves"])
    state = scenario.build(DrawCards(P1, 1, ("121.1",)), Hold())
    entry = next(e for e in state.event_log if isinstance(e.record, CardDrawn))
    assert entry.visible_to == (P1,)
    assert entry.record == CardDrawn(
        player=P1, drawn_from=top, drawn=state.players[1].hand[0], rules=("121.1",)
    )
    assert entry.redacted == CardDrawn(
        player=P1, drawn_from=None, drawn=state.players[1].hand[0], rules=("121.1",)
    )
    for viewer in (P0, P2):
        (shown,) = [e for e in view_for(state, viewer).log if isinstance(e.record, CardDrawn)]
        assert shown.record == entry.redacted
        assert shown.index == entry.index
    (own,) = [e for e in view_for(state, P1).log if isinstance(e.record, CardDrawn)]
    assert own == entry


def test_400_7_knowledge_of_a_library_card_doesnt_follow_it_into_the_hand() -> None:
    """400.7: the drawn card is a new object; 402.3 lets only its owner see it in hand.

    P1 knew the top card of P0's library (say, it was revealed earlier); once drawn, the new
    object in P0's hand isn't known to P1.
    """
    scenario = Scenario(2)
    scenario.add("Forest", owner=P0, zone=Zone.library(P0), known_to=[P1])
    state = scenario.build(DrawCards(P0, 1, ("121.1",)), Hold())
    obj = state.objects[state.players[0].hand[0]]
    assert obj.known_to == ()
    assert view_for(state, P1).players[0].hand[0].name is None
    assert view_for(state, P0).players[0].hand[0].name == "Forest"
