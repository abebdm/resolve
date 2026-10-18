"""A concession (104.3a) while some player is in the middle of a decision.

From the pinned CR and design.md §5 ("Asking again"):

- 104.3a: a player may concede at any time, so also while another player, or they themselves,
  is answering a question. The pending request is withdrawn; the task that asked runs again.
- 800.4a: the objects the conceding player owns leave the game. 800.4h: a choice a rule asks of
  a player who left is made by the next player in turn order (before turn order exists,
  103.1, in seating order).
- A question that is still the same question is asked again with a new request id, keeping the
  answers already given (the cards already chosen for a discard or for the bottom of a library
  are not chosen again; only their order is asked again).
- 404.3: cards put into a graveyard together are ordered by their owner; 704.3: the
  state-based actions of one check happen together. If a player who left owned some of the
  creatures of a pending check, the check is computed again (docs/decisions.md, "Conceding and
  leaving the game"), and its orders are asked again.
- 514.1: only the active player discards in cleanup; 800.4j: a turn whose active player left
  goes on without one, so nobody discards.
- 103.5: the cards put on the bottom are chosen and ordered by the player who took the
  mulligan; a player who left puts nothing on the bottom.
"""

from __future__ import annotations

from resolve.agents.scripted import Choose, choose
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import ChooseOne, ObjectOption, PassOption, PlayerOption
from resolve.engine import concede
from resolve.engine.api import new_game
from resolve.engine.mulligans import KEEP, MULLIGAN
from resolve.events.cards import CardDiscarded, CardsPutOnBottom
from resolve.events.turn import TurnBegan
from resolve.state.config import GameConfig
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.turn import Step
from resolve.state.zones import Zone
from tests.game_fixtures import deck, request_of
from tests.scenario import Scenario, names, run_script

P0, P1, P2, P3 = (PlayerId(p) for p in range(4))
NINE = ["Forest", "Llanowar Elves", "Forest", "Test Shock", "Forest", "Forest", "Test Ponder",
        "Forest", "Forest"]  # fmt: skip


def order(player: PlayerId, *objs: ObjectId) -> Choose:
    return choose(*(ObjectOption(o) for o in objs), player=player, kind=DecisionKind.ORDER_CARDS)


def records[T](state: GameState, kind: type[T]) -> list[T]:
    return [e.record for e in state.event_log if isinstance(e.record, kind)]


# --- 704.5g and 404.3: the order of dying creatures ------------------------------------------


def dying_creatures() -> tuple[Scenario, list[ObjectId], list[ObjectId]]:
    """Four players, player 0 active. Players 0 and 1 each have two creatures with lethal
    damage, player 2 has one: owners 0 and then 1 are asked to order theirs (APNAP, 101.4)."""
    scenario = Scenario(4)
    for player in scenario.players:
        scenario.library(player, ["Forest"] * 3)
    p0 = scenario.battlefield(P0, ["Grizzly Bears", "Hill Giant"])
    p1 = scenario.battlefield(P1, ["Savannah Lions", "Hill Giant"])
    p2 = scenario.battlefield(P2, ["Grizzly Bears"])
    for obj in (*p0, *p1, *p2):
        scenario.damage(obj, 3)
    scenario.at(Step.UPKEEP, number=2, active=P0)
    return scenario, p0, p1


def test_404_3_another_player_conceding_keeps_the_orders_already_given() -> None:
    """Player 3, who owns none of the dying creatures, concedes while player 1 orders theirs:
    the check is unchanged, player 1 is asked again with a new id, and player 0's order
    stands."""
    scenario, (bears, giant), (lions, p1_giant) = dying_creatures()
    state = scenario.build()
    run_script(state, order(P0, bears, giant))  # the Bears on top
    asked = request_of(state)
    assert (asked.kind, asked.player) == (DecisionKind.ORDER_CARDS, P1)
    concede(state, P3)
    again = request_of(state)
    assert (again.kind, again.player, again.space) == (DecisionKind.ORDER_CARDS, P1, asked.space)
    assert again.id != asked.id
    run_script(state, order(P1, p1_giant, lions))
    assert names(state, Zone.graveyard(P0)) == ["Hill Giant", "Grizzly Bears"]  # top last
    assert names(state, Zone.graveyard(P1)) == ["Savannah Lions", "Hill Giant"]
    assert names(state, Zone.graveyard(P2)) == ["Grizzly Bears"]
    assert state.battlefield == []
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION


def test_404_3_800_4a_an_owner_of_dying_creatures_concedes_while_ordering_them() -> None:
    """Player 1 concedes while asked to order their two dying creatures: they leave the game
    with the player (800.4a), so nobody orders them; the check is computed again and player 0
    orders their creatures anew; the new order is the one that counts."""
    scenario, (bears, giant), _ = dying_creatures()
    state = scenario.build()
    run_script(state, order(P0, bears, giant))
    assert request_of(state).player == P1
    concede(state, P1)
    again = request_of(state)
    assert (again.kind, again.player) == (DecisionKind.ORDER_CARDS, P0)
    run_script(state, order(P0, giant, bears))  # now the Giant on top
    assert names(state, Zone.graveyard(P0)) == ["Grizzly Bears", "Hill Giant"]
    assert names(state, Zone.graveyard(P2)) == ["Grizzly Bears"]
    assert not any(o.owner == P1 for o in state.objects.values())
    assert state.battlefield == []
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION
    assert state.result is None


# --- 514.1 and 404.3: discarding in cleanup ---------------------------------------------------


def cleanup() -> tuple[Scenario, list[ObjectId]]:
    """Three players in player 0's cleanup step; players 0 and 1 hold nine cards each."""
    scenario = Scenario(3)
    for player in scenario.players:
        scenario.library(player, ["Forest"] * 3)
    hand = scenario.hand(P0, NINE)
    scenario.hand(P1, NINE)
    scenario.at(Step.CLEANUP, active=P0)
    return scenario, hand


def test_514_1_800_4j_the_active_player_concedes_while_choosing_discards() -> None:
    """Nobody discards: the turn has no active player any more, and 514.1 asks only the active
    player. The next turn is player 1's, who still holds nine cards in their upkeep."""
    scenario, _ = cleanup()
    state = scenario.build()
    assert request_of(state).kind is DecisionKind.DISCARD
    concede(state, P0)
    assert records(state, CardDiscarded) == []
    request = request_of(state)
    assert (request.kind, request.player) == (DecisionKind.PRIORITY_ACTION, P1)
    turn = state.turn
    assert turn is not None and (turn.number, turn.active_player, turn.step) == (2, P1, Step.UPKEEP)
    assert len(state.player(P1).hand) == 9


def test_404_3_another_player_conceding_while_discards_are_ordered() -> None:
    """Player 2 concedes while player 0 orders their two discarded cards: player 0 is asked for
    the order again (same cards, new id), not which cards to discard."""
    scenario, hand = cleanup()
    state = scenario.build()
    run_script(
        state,
        choose(ObjectOption(hand[3]), ObjectOption(hand[1]), kind=DecisionKind.DISCARD),
    )
    asked = request_of(state)
    assert (asked.kind, asked.player) == (DecisionKind.ORDER_CARDS, P0)
    concede(state, P2)
    again = request_of(state)
    assert (again.kind, again.player, again.space) == (DecisionKind.ORDER_CARDS, P0, asked.space)
    assert again.id != asked.id
    run_script(state, order(P0, hand[3], hand[1]))  # the Test Shock on top
    assert names(state, Zone.graveyard(P0)) == ["Llanowar Elves", "Test Shock"]
    assert len(state.player(P0).hand) == 7
    turn = state.turn
    assert turn is not None and (turn.number, turn.active_player) == (2, P1)


# --- 103.5: putting cards on the bottom after a mulligan --------------------------------------


def mulligans() -> GameState:
    """Three players, player 0 starts. Round 1: players 0 and 1 take their free mulligan
    (103.5c), player 2 keeps."""
    state = new_game(GameConfig.standard(), [deck(10, 10)] * 3, seed=1)
    run_script(
        state,
        choose(PlayerOption(P0), kind=DecisionKind.CHOOSE_STARTING_PLAYER),
        choose(MULLIGAN, player=P0),
        choose(MULLIGAN, player=P1),
        choose(KEEP, player=P2),
    )
    return state


def test_103_5_800_4a_a_player_conceding_while_choosing_cards_for_the_bottom() -> None:
    """Round 2: players 0 and 1 mulligan again and must each put one card on the bottom. Player
    0 concedes while choosing: player 1 is asked next, and nothing of player 0's goes to the
    bottom."""
    state = mulligans()
    run_script(state, choose(MULLIGAN, player=P0), choose(MULLIGAN, player=P1))
    asked = request_of(state)
    assert (asked.kind, asked.player) == (DecisionKind.PUT_ON_BOTTOM, P0)
    concede(state, P0)
    request = request_of(state)
    assert (request.kind, request.player) == (DecisionKind.PUT_ON_BOTTOM, P1)
    run_script(
        state,
        choose(ObjectOption(state.player(P1).hand[0]), kind=DecisionKind.PUT_ON_BOTTOM),
    )
    assert [b.player for b in records(state, CardsPutOnBottom)] == [P1]
    assert len(state.player(P1).hand) == 6
    assert not any(o.owner == P0 for o in state.objects.values())


def test_103_5_another_player_conceding_while_bottom_cards_are_ordered() -> None:
    """Round 2: player 0 mulligans (one card to the bottom), player 1 keeps; round 3: player 0
    mulligans again and puts two cards on the bottom. Player 2 concedes while player 0 orders
    them: player 0 is asked for the order again (same cards, new id)."""
    state = mulligans()
    run_script(state, choose(MULLIGAN, player=P0), choose(KEEP, player=P1))
    run_script(
        state,
        choose(ObjectOption(state.player(P0).hand[0]), kind=DecisionKind.PUT_ON_BOTTOM),
        choose(MULLIGAN, player=P0),
    )
    first, second = state.player(P0).hand[2], state.player(P0).hand[5]
    run_script(
        state, choose(ObjectOption(first), ObjectOption(second), kind=DecisionKind.PUT_ON_BOTTOM)
    )
    asked = request_of(state)
    assert (asked.kind, asked.player) == (DecisionKind.ORDER_CARDS, P0)
    cards = (state.objects[first].card, state.objects[second].card)
    concede(state, P2)
    again = request_of(state)
    assert (again.kind, again.player, again.space) == (DecisionKind.ORDER_CARDS, P0, asked.space)
    assert again.id != asked.id
    run_script(state, order(P0, second, first))  # listed top to bottom
    library = state.player(P0).library
    assert (state.objects[library[1]].card, state.objects[library[0]].card) == cards[::-1]
    assert len(state.player(P0).hand) == 5


# --- 103.1: choosing the starting player ------------------------------------------------------


def test_103_1_another_player_conceding_while_the_starting_player_is_chosen() -> None:
    """The chooser is asked again with a new id, and the player who left can't be chosen. The
    chooser isn't determined again: no randomness is drawn again (design.md §5)."""
    state = new_game(GameConfig.standard(), [deck(5, 5)] * 3, seed=1)
    asked = request_of(state)
    leaver = PlayerId((asked.player + 1) % 3)
    rng = state.rng.state
    concede(state, leaver)
    assert state.rng.state == rng
    again = request_of(state)
    assert (again.kind, again.player) == (DecisionKind.CHOOSE_STARTING_PLAYER, asked.player)
    assert again.id != asked.id
    assert isinstance(again.space, ChooseOne)
    choices = [o.player for o in again.space.options if isinstance(o, PlayerOption)]
    assert sorted(choices) == sorted(p for p in (P0, P1, P2) if p != leaver)


def test_800_4k_the_first_turn_goes_to_the_next_player_when_the_starting_player_leaves() -> None:
    """Three players; the starting player (0) concedes during the mulligans. Player 1 is asked
    next, and takes the game's first turn (800.4k: player 0's turn doesn't begin). The game
    began with three players, so player 1 draws in that turn (103.8c)."""
    state = new_game(GameConfig.standard(), [deck(10, 10)] * 3, seed=1)
    run_script(state, choose(PlayerOption(P0), kind=DecisionKind.CHOOSE_STARTING_PLAYER))
    assert request_of(state).player == P0
    concede(state, P0)
    request = request_of(state)
    assert (request.kind, request.player) == (DecisionKind.MULLIGAN, P1)
    run_script(state, choose(KEEP, player=P1), choose(KEEP, player=P2))
    began = records(state, TurnBegan)
    assert [(b.number, b.player) for b in began] == [(1, P1)]
    run_script(state, choose(PassOption(), player=P1), choose(PassOption(), player=P2))  # upkeep
    turn = state.turn
    assert turn is not None and turn.step is Step.DRAW
    assert len(state.player(P1).hand) == 8
