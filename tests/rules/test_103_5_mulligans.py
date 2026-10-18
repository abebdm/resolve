"""103.5: opening hands and mulligans (with 103.5c for multiplayer games).

Worked from the pinned CR text:

- Each player draws their starting hand size (103.5), one card at a time (121.2), the starting
  player first and then the others in turn order (121.2c, with 101.4e making the starting player
  the active player while the game starts).
- The starting player declares first, then each other player in turn order. Mulligans are taken
  only after every player has declared, and all at the same time (103.5).
- Taking a mulligan: shuffle the hand into the library, draw a new hand of the starting hand size,
  then put as many of those cards on the bottom as the number of mulligans taken, in any order
  (103.5). Choices made at the same time are made in APNAP order (101.4).
- A player who keeps may not mulligan again; the process repeats until nobody mulligans (103.5).
- In a game that begins with more than two players (100.1b) the first mulligan doesn't count
  toward the cards put on the bottom or the number of mulligans allowed (103.5c).
- "A player can take mulligans until their opening hand would be zero cards, after which they may
  not take further mulligans" (103.5). Interpretation (docs/decisions.md): the mulligan that
  leaves zero cards may be taken; after it the player keeps without being asked.

Until the turn structure exists (M1.2), a game stops at ``NotImplementedRule("103.8: ...")`` once
every player has kept.
"""

from __future__ import annotations

import copy

import pytest

from resolve.agents.scripted import ScriptStep, choose
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.request import DecisionAnswer
from resolve.decisions.spaces import (
    ChooseOne,
    ChooseOrder,
    ChooseSubset,
    ObjectOption,
    Order,
    Pick,
    PickMany,
)
from resolve.engine.api import new_game, pending_decision, submit, view_for
from resolve.engine.deck import Deck
from resolve.engine.mulligans import KEEP, MULLIGAN
from resolve.errors import InvalidAnswer, NotImplementedRule
from resolve.events.base import AnswerRecord
from resolve.events.cards import CardDrawn, CardsPutOnBottom, HandShuffledIntoLibrary
from resolve.events.game import MulliganDeclared
from resolve.state.config import GameConfig
from resolve.state.game import GameState
from resolve.state.ids import CardId, ObjectId, PlayerId
from resolve.state.invariants import invariant_violations, state_impurities
from resolve.state.zones import ZoneKind
from tests.game_fixtures import DAYBREAKER, answer, choose_starting_player, deck, request_of
from tests.scenario import run_script

P0, P1, P2, P3 = PlayerId(0), PlayerId(1), PlayerId(2), PlayerId(3)


def mulligan_game(
    players: int = 2,
    *,
    starting: int = 0,
    seed: int = 1,
    config: GameConfig | None = None,
    cards: int = 20,
) -> GameState:
    """A game of ``cards``-card decks, at its first mulligan decision."""
    decks = [deck(cards // 2, cards - cards // 2) for _ in range(players)]
    state = new_game(config or GameConfig.standard(), decks, seed)
    assert choose_starting_player(state, starting) is None
    return state


def act(state: GameState, *steps: ScriptStep) -> NotImplementedRule | None:
    """Play ``steps``. Until M1.2 the game stops at the 103.8 gap once everyone has kept."""
    try:
        run_script(state, *steps)
    except NotImplementedRule as gap:
        assert gap.rule == "103.8", gap
        return gap
    return None


def keep(player: PlayerId) -> ScriptStep:
    return choose(KEEP, player=player, kind=DecisionKind.MULLIGAN)


def mulligan(player: PlayerId) -> ScriptStep:
    return choose(MULLIGAN, player=player, kind=DecisionKind.MULLIGAN)


def bottom(player: PlayerId, *objs: ObjectId) -> ScriptStep:
    return choose(*(ObjectOption(o) for o in objs), player=player, kind=DecisionKind.PUT_ON_BOTTOM)


def order(player: PlayerId, *objs: ObjectId) -> ScriptStep:
    return choose(*(ObjectOption(o) for o in objs), player=player, kind=DecisionKind.ORDER_CARDS)


def card_of(state: GameState, obj: ObjectId) -> CardId:
    card = state.objects[obj].card
    assert card is not None
    return card


def events[T](state: GameState, kind: type[T]) -> list[T]:
    return [entry.record for entry in state.event_log if isinstance(entry.record, kind)]


# --- Drawing the opening hands ------------------------------------------------------------------


@pytest.mark.parametrize(("size", "hand", "library"), [(7, 7, 13), (5, 5, 15), (1, 1, 19)])
def test_103_5_each_player_draws_their_starting_hand_size(
    size: int, hand: int, library: int
) -> None:
    state = mulligan_game(3, config=GameConfig(starting_hand_size=size))
    for player in state.players:
        assert len(player.hand) == hand
        assert len(player.library) == library
    assert request_of(state).kind is DecisionKind.MULLIGAN


def test_103_5_a_starting_hand_size_of_zero_draws_nothing_and_asks_nothing() -> None:
    """With nothing to draw, a mulligan would leave zero cards already: nobody is asked."""
    state = new_game(GameConfig(starting_hand_size=0), [deck(10, 10), deck(10, 10)], seed=1)
    gap = choose_starting_player(state, 0)
    assert gap is not None and gap.rule == "103.8"
    assert all(player.hand == [] and len(player.library) == 20 for player in state.players)
    assert events(state, CardDrawn) == []
    assert events(state, MulliganDeclared) == []


def test_121_2c_101_4e_opening_draws_go_in_turn_order_from_the_starting_player() -> None:
    state = mulligan_game(3, starting=2)
    drawers = [event.player for event in events(state, CardDrawn)]
    assert drawers == [2] * 7 + [0] * 7 + [1] * 7
    assert all(event.rules[0] == "103.5" for event in events(state, CardDrawn))


def test_400_7_each_drawn_card_is_a_new_object_in_its_owners_hand() -> None:
    state = mulligan_game(2)
    for event in events(state, CardDrawn):
        assert event.drawn_from is not None and event.drawn is not None
        assert event.drawn_from not in state.objects  # the library object is gone (400.7)
        new = state.objects[event.drawn]
        assert new.zone.kind is ZoneKind.HAND and new.zone.owner == event.player
        assert new.owner == event.player
    assert sorted(o for p in state.players for o in p.hand) == sorted(
        e.drawn for e in events(state, CardDrawn) if e.drawn is not None
    )


# --- Declarations --------------------------------------------------------------------------------


def test_103_5_the_starting_player_declares_first_then_each_other_player_in_turn_order() -> None:
    state = mulligan_game(4, starting=2)
    asked: list[PlayerId] = []
    for player in (P2, P3, P0, P1):
        asked.append(request_of(state).player)
        act(state, keep(player))
    assert asked == [P2, P3, P0, P1]


def test_103_5_the_mulligan_question_offers_keep_and_mulligan() -> None:
    state = mulligan_game(2)
    request = request_of(state)
    assert request.kind is DecisionKind.MULLIGAN
    assert request.player == P0
    assert request.space == ChooseOne((KEEP, MULLIGAN))
    assert "103.5" in request.rules


def test_101_4b_mulligan_declarations_are_public() -> None:
    state = mulligan_game(3)
    act(state, mulligan(P0))
    for viewer in (P0, P1, P2):
        declared = [
            e.record for e in view_for(state, viewer).log if isinstance(e.record, MulliganDeclared)
        ]
        assert declared == [MulliganDeclared(player=P0, mulligan=True, rules=("103.5",))]


def test_103_5_mulligans_are_taken_only_after_every_player_has_declared() -> None:
    state = mulligan_game(3)
    hand = list(state.players[0].hand)
    act(state, mulligan(P0), keep(P1))
    assert state.players[0].hand == hand, "P2 hasn't declared yet"
    assert events(state, HandShuffledIntoLibrary) == []
    act(state, keep(P2))
    assert events(state, HandShuffledIntoLibrary) != []
    assert not set(hand) & set(state.players[0].hand)


def test_103_5_all_players_who_mulligan_do_so_at_the_same_time() -> None:
    """The hands go back together, then the new hands are drawn in turn order (121.2c)."""
    state = mulligan_game(3, starting=1)
    act(state, mulligan(P1), keep(P2), mulligan(P0))
    kinds = [
        (type(e.record).__name__, getattr(e.record, "player", None))
        for e in state.event_log
        if isinstance(e.record, HandShuffledIntoLibrary | CardDrawn)
    ][21:]
    assert kinds == [
        ("HandShuffledIntoLibrary", P1),
        ("HandShuffledIntoLibrary", P0),
        *[("CardDrawn", P1)] * 7,
        *[("CardDrawn", P0)] * 7,
    ]


# --- Taking a mulligan ---------------------------------------------------------------------------


def test_103_5_a_mulligan_shuffles_the_hand_back_and_draws_a_new_hand() -> None:
    state = mulligan_game(3)  # multiplayer: the first mulligan bottoms nothing (103.5c)
    old_hand = list(state.players[0].hand)
    old_cards = sorted(card_of(state, obj) for obj in old_hand)
    act(state, mulligan(P0), keep(P1), keep(P2))
    shuffled = events(state, HandShuffledIntoLibrary)
    assert shuffled == [
        HandShuffledIntoLibrary(player=P0, cards=tuple(old_hand), rules=shuffled[0].rules)
    ]
    assert shuffled[0].rules[:2] == ("103.5", "701.24a")
    player = state.players[0]
    assert len(player.hand) == 7 and len(player.library) == 13
    assert not set(old_hand) & set(state.objects), "the old hand objects are gone (400.7)"
    assert not set(old_hand) & set(player.library), "the library holds new objects only"
    del old_cards


def test_103_5_701_24a_a_mulligan_really_shuffles_the_library() -> None:
    """Without a shuffle P0 would draw back exactly the old seven cards (the hand goes on top).

    Over a few seeds, the new hand differs from the old one at least once; and the shuffle
    touches only the mulliganing player's library.
    """
    differs = 0
    for seed in range(5):
        state = mulligan_game(2, seed=seed)
        old = sorted(card_of(state, o) for o in state.players[0].hand)
        other_library = list(state.players[1].library)
        act(state, mulligan(P0), keep(P1))
        new = sorted(card_of(state, o) for o in state.players[0].hand)
        differs += new != old
        assert state.players[1].library == other_library
    assert differs > 0


def test_701_24a_a_later_mulligan_forgets_the_cards_put_on_the_bottom_earlier() -> None:
    state = mulligan_game(2)
    act(state, mulligan(P0), keep(P1))
    act(state, bottom(P0, state.players[0].hand[0]))
    assert state.objects[state.players[0].library[0]].known_to == (P0,)
    act(state, mulligan(P0))
    assert request_of(state).kind is DecisionKind.PUT_ON_BOTTOM
    assert all(state.objects[o].known_to == () for o in state.players[0].library)


def test_103_5_a_later_round_still_starts_from_the_starting_player_in_turn_order() -> None:
    """The starting player kept; the next round asks the others in turn order from them."""
    state = mulligan_game(4, starting=2)
    act(state, keep(P2), mulligan(P3), mulligan(P0), mulligan(P1))  # first mulligans are free
    asked: list[PlayerId] = []
    for player in (P3, P0, P1):
        asked.append(request_of(state).player)
        act(state, keep(player))
    assert asked == [P3, P0, P1]


def test_103_5_a_player_who_kept_keeps_the_same_hand_while_others_mulligan() -> None:
    state = mulligan_game(3)
    kept = list(state.players[1].hand)
    act(state, mulligan(P0), keep(P1), keep(P2))
    act(state, mulligan(P0))
    act(state, bottom(P0, state.players[0].hand[0]))
    assert state.players[1].hand == kept


def test_103_5_a_third_mulligan_orders_three_cards() -> None:
    state = mulligan_game(2)
    act(state, mulligan(P0), keep(P1))
    act(state, bottom(P0, state.players[0].hand[0]))
    act(state, mulligan(P0))
    first, second = state.players[0].hand[:2]
    act(state, bottom(P0, first, second), order(P0, first, second))
    act(state, mulligan(P0))
    a, b, c = state.players[0].hand[4], state.players[0].hand[0], state.players[0].hand[2]
    cards = (card_of(state, a), card_of(state, b), card_of(state, c))
    act(state, bottom(P0, a, b, c), order(P0, a, b, c))  # top to bottom: a, b, c
    library = state.players[0].library
    assert (card_of(state, library[2]), card_of(state, library[1]), card_of(state, library[0])) == (
        cards
    )
    assert len(state.players[0].hand) == 4


def test_103_5_the_standard_hand_allows_seven_mulligans_in_two_player_games() -> None:
    """Seven cards: hands of 6, 5, ... 0 after seven mulligans; then no eighth (103.5)."""
    state = mulligan_game(2)
    act(state, mulligan(P0), keep(P1))
    gap = None
    for taken in range(1, 8):
        hand = state.players[0].hand
        if taken < 7:  # the seventh puts the whole hand on the bottom: only the order is asked
            act(state, bottom(P0, *hand[:taken]))
        if taken > 1:
            gap = act(state, order(P0, *hand[:taken]))
        assert len(state.players[0].hand) == 7 - taken
        if taken < 7:
            act(state, mulligan(P0))
    assert gap is not None, "no eighth mulligan is offered: the mulligans are over"


def test_103_5c_the_standard_hand_allows_eight_mulligans_in_multiplayer_games() -> None:
    """The free first mulligan (103.5c) keeps seven cards; then 6, 5, ... 0 after the eighth."""
    state = mulligan_game(3)
    act(state, mulligan(P0), keep(P1), keep(P2))
    assert len(state.players[0].hand) == 7
    gap = None
    for counted in range(1, 8):
        act(state, mulligan(P0))
        hand = state.players[0].hand
        if counted < 7:
            act(state, bottom(P0, *hand[:counted]))
        if counted > 1:
            gap = act(state, order(P0, *hand[:counted]))
        assert len(state.players[0].hand) == 7 - counted
    assert gap is not None, "no ninth mulligan is offered"


def test_103_5_put_on_bottom_rejects_repeats_and_unknown_cards() -> None:
    state = mulligan_game(2)
    act(state, mulligan(P0), keep(P1))
    act(state, bottom(P0, state.players[0].hand[0]))
    act(state, mulligan(P0))
    before = copy.deepcopy(state)
    for bad in (PickMany((0, 0)), PickMany((1, 0)), PickMany((0, 7)), PickMany((0,))):
        with pytest.raises(InvalidAnswer):
            submit(state, answer(state, bad))
        assert state == before


def test_103_5_the_first_mulligan_in_a_two_player_game_puts_one_card_on_the_bottom() -> None:
    state = mulligan_game(2)
    act(state, mulligan(P0), keep(P1))
    request = request_of(state)
    assert request.kind is DecisionKind.PUT_ON_BOTTOM
    assert request.player == P0
    hand = state.players[0].hand
    assert len(hand) == 7
    assert request.space == ChooseSubset(tuple(ObjectOption(o) for o in hand), 1, 1)
    chosen = hand[3]
    chosen_card = card_of(state, chosen)
    act(state, bottom(P0, chosen))
    player = state.players[0]
    assert len(player.hand) == 6
    assert len(player.library) == 14
    assert card_of(state, player.library[0]) == chosen_card, "on the bottom (the list's start)"
    assert chosen not in state.objects, "a new object in the library (400.7)"


def test_103_5_a_second_mulligan_puts_two_cards_on_the_bottom_in_the_chosen_order() -> None:
    """The ORDER_CARDS answer lists the cards from top to bottom (docs/decisions.md)."""
    state = mulligan_game(2)
    act(state, mulligan(P0), keep(P1))
    act(state, bottom(P0, state.players[0].hand[0]))
    act(state, mulligan(P0))
    hand = state.players[0].hand
    assert request_of(state).space == ChooseSubset(tuple(ObjectOption(o) for o in hand), 2, 2)
    first, second = hand[5], hand[1]
    upper, lower = card_of(state, first), card_of(state, second)
    act(state, bottom(P0, first, second))
    request = request_of(state)
    assert request.kind is DecisionKind.ORDER_CARDS
    assert request.space == ChooseOrder((ObjectOption(second), ObjectOption(first)))
    act(state, order(P0, first, second))
    library = state.players[0].library
    assert len(state.players[0].hand) == 5
    assert (card_of(state, library[1]), card_of(state, library[0])) == (upper, lower)


def test_103_5_cards_put_on_the_bottom_stay_known_to_their_owner_only() -> None:
    """400.2: the owner chose them; until a shuffle (701.24a) they know which cards those are."""
    state = mulligan_game(2)
    act(state, mulligan(P0), keep(P1))
    act(state, bottom(P0, state.players[0].hand[2]))
    assert state.objects[state.players[0].library[0]].known_to == (P0,)
    assert all(state.objects[o].known_to == () for o in state.players[0].library[1:])


def test_101_4_bottom_choices_are_made_in_apnap_order_then_done_together() -> None:
    state = mulligan_game(3, starting=1)
    act(state, mulligan(P1), mulligan(P2), mulligan(P0))  # first mulligans: free (103.5c)
    act(state, mulligan(P1), mulligan(P2), mulligan(P0))
    asked: list[PlayerId] = []
    for _ in range(3):
        request = request_of(state)
        asked.append(request.player)
        assert request.kind is DecisionKind.PUT_ON_BOTTOM
        assert events(state, CardsPutOnBottom) == [], "nothing moves until all have chosen"
        act(state, bottom(request.player, state.players[request.player].hand[0]))
    assert asked == [P1, P2, P0]
    entries = [i for i, e in enumerate(state.event_log) if isinstance(e.record, CardsPutOnBottom)]
    assert [event.player for event in events(state, CardsPutOnBottom)] == [P1, P2, P0]
    assert entries == list(range(entries[0], entries[0] + 3)), "one simultaneous set of events"


def test_103_5_a_player_who_keeps_is_not_asked_again() -> None:
    state = mulligan_game(2)
    act(state, keep(P0), mulligan(P1))
    act(state, bottom(P1, state.players[1].hand[0]))
    request = request_of(state)
    assert request.player == P1 and request.kind is DecisionKind.MULLIGAN


def test_103_5_the_process_repeats_until_no_player_mulligans() -> None:
    state = mulligan_game(2)
    act(state, mulligan(P0), mulligan(P1))
    act(state, bottom(P0, state.players[0].hand[0]))
    act(state, bottom(P1, state.players[1].hand[0]))
    act(state, mulligan(P0), keep(P1))
    hand = state.players[0].hand
    act(state, bottom(P0, hand[0], hand[1]), order(P0, hand[0], hand[1]))
    gap = act(state, keep(P0))
    assert gap is not None
    assert [len(p.hand) for p in state.players] == [5, 6]
    assert [len(p.library) for p in state.players] == [15, 14]
    declared = [(e.player, e.mulligan) for e in events(state, MulliganDeclared)]
    assert declared == [(P0, True), (P1, True), (P0, True), (P1, False), (P0, False)]


def test_103_5_mulligans_are_allowed_until_the_opening_hand_would_be_zero_cards() -> None:
    """Hand size 2: mulligan 1 leaves one card, mulligan 2 leaves none; then no more.

    The second mulligan puts both cards on the bottom: which cards is forced (not asked), their
    order is still a choice.
    """
    state = mulligan_game(2, config=GameConfig(starting_hand_size=2))
    act(state, mulligan(P0), keep(P1))
    act(state, bottom(P0, state.players[0].hand[0]))
    assert len(state.players[0].hand) == 1
    act(state, mulligan(P0))
    hand = state.players[0].hand
    request = request_of(state)
    assert request.kind is DecisionKind.ORDER_CARDS, "both cards must go: only the order is asked"
    gap = act(state, order(P0, hand[1], hand[0]))
    assert gap is not None, "the player keeps an empty hand without being asked"
    assert state.players[0].hand == []
    assert len(state.players[0].library) == 20


def test_103_5c_the_first_mulligan_is_free_in_a_multiplayer_game() -> None:
    state = mulligan_game(3)
    act(state, mulligan(P0), keep(P1), keep(P2))
    request = request_of(state)
    assert (request.player, request.kind) == (P0, DecisionKind.MULLIGAN), "no bottom question"
    assert len(state.players[0].hand) == 7
    assert len(state.players[0].library) == 13
    act(state, mulligan(P0))
    assert request_of(state).space == ChooseSubset(
        tuple(ObjectOption(o) for o in state.players[0].hand), 1, 1
    )
    act(state, bottom(P0, state.players[0].hand[0]))
    assert len(state.players[0].hand) == 6


def test_103_5c_a_multiplayer_game_allows_one_more_mulligan() -> None:
    """Hand size 2, three players: hands of 2 (free), 1 and 0 cards; three mulligans in all."""
    state = mulligan_game(3, config=GameConfig(starting_hand_size=2))
    act(state, mulligan(P0), keep(P1), keep(P2))
    assert len(state.players[0].hand) == 2
    act(state, mulligan(P0))
    act(state, bottom(P0, state.players[0].hand[0]))
    assert len(state.players[0].hand) == 1
    act(state, mulligan(P0))
    hand = state.players[0].hand
    gap = act(state, order(P0, hand[0], hand[1]))
    assert gap is not None
    assert state.players[0].hand == []


def test_100_1a_103_5c_a_two_player_commander_game_has_no_free_mulligan() -> None:
    decks = [deck(10, 10, commanders=[DAYBREAKER]) for _ in range(2)]
    state = new_game(GameConfig.commander_game(), decks, seed=1)
    choose_starting_player(state, 0)
    act(state, mulligan(P0), keep(P1))
    assert request_of(state).kind is DecisionKind.PUT_ON_BOTTOM
    act(state, bottom(P0, state.players[0].hand[0]))
    assert len(state.players[0].hand) == 6
    commanders = [state.objects[o] for o in state.command]
    assert len(commanders) == 2, "commanders stay in the command zone and aren't drawn"


# --- Hidden information --------------------------------------------------------------------------


def test_other_players_never_see_drawn_or_bottomed_cards() -> None:
    """design.md §9: drawn cards and library object IDs stay hidden from other players."""
    state = mulligan_game(2)
    act(state, mulligan(P0), keep(P1))
    act(state, bottom(P0, state.players[0].hand[0]))
    library_ids = {
        e.drawn_from for e in events(state, CardDrawn) if e.player == P0 and e.drawn_from
    }
    for viewer, other in ((P1, P0), (P0, P1)):
        view = view_for(state, viewer)
        assert all(obj.name is None for obj in view.players[other].hand)
        for entry in view.log:
            record = entry.record
            if isinstance(record, CardDrawn) and record.player == other:
                assert record.drawn_from is None, "the library ID is redacted"
                assert record.drawn is not None, "the hand placeholder ID is public"
            if isinstance(record, CardsPutOnBottom) and record.player == other:
                assert record.cards == () and record.count == 1
    own = [e.record for e in view_for(state, P0).log if isinstance(e.record, CardDrawn)]
    assert {e.drawn_from for e in own if e.player == P0} == library_ids, "P0 sees their own"
    for entry in state.event_log:
        if isinstance(entry.record, AnswerRecord):
            assert entry.visible_to == (entry.record.player,)


# --- Edge cases and validation -------------------------------------------------------------------


def test_121_4_a_short_library_is_drawn_out_and_remembered_but_doesnt_lose_yet() -> None:
    """704.5b is checked only when a player would receive priority, which 103.5 never gives."""
    decks = [deck(10, 10), deck(3, 2)]
    state = new_game(GameConfig.standard(), decks, seed=1)
    choose_starting_player(state, 0)
    assert len(state.players[1].hand) == 5
    assert state.players[1].library == []
    assert state.players[1].drew_from_empty_library
    assert not state.players[0].drew_from_empty_library
    assert state.result is None
    empties = [e for e in events(state, CardDrawn) if e.empty_library]
    assert [e.player for e in empties] == [P1, P1]


def test_103_5_a_player_whose_opening_hand_is_zero_cards_may_not_mulligan() -> None:
    """103.5: "until their opening hand would be zero cards, after which they may not take
    further mulligans." An empty library gives a zero-card hand at once, so P0 isn't asked."""
    state = new_game(GameConfig.standard(), [Deck(()), deck(10, 10)], seed=1)
    choose_starting_player(state, 0)
    assert state.players[0].hand == []
    assert state.players[0].drew_from_empty_library
    request = request_of(state)
    assert (request.player, request.kind) == (P1, DecisionKind.MULLIGAN)


def test_103_5_a_short_library_reaches_a_zero_card_hand_sooner() -> None:
    """A 3-card library: hands of 3, 2, 1 and then 0 cards; the limit is the cards, not 7."""
    state = new_game(GameConfig.standard(), [deck(2, 1), deck(10, 10)], seed=1)
    choose_starting_player(state, 0)
    act(state, mulligan(P0), keep(P1))
    act(state, bottom(P0, state.players[0].hand[0]))
    assert len(state.players[0].hand) == 2
    act(state, mulligan(P0))
    first, second = state.players[0].hand[:2]
    act(state, bottom(P0, first, second), order(P0, first, second))
    assert len(state.players[0].hand) == 1
    act(state, mulligan(P0))
    hand = state.players[0].hand
    assert request_of(state).kind is DecisionKind.ORDER_CARDS, "all three must go to the bottom"
    gap = act(state, order(P0, *hand))
    assert gap is not None, "the hand is zero cards: no further mulligan is offered"
    assert state.players[0].hand == []


def test_121_4_727_3_mulligans_dont_undo_drawing_from_an_empty_library() -> None:
    """727.3: a player with fewer than seven cards loses "regardless of any mulligans"."""
    state = new_game(GameConfig.standard(), [deck(10, 10), deck(3, 2)], seed=1)
    choose_starting_player(state, 0)
    act(state, keep(P0), mulligan(P1))
    act(state, bottom(P1, state.players[1].hand[0]))
    assert state.players[1].drew_from_empty_library
    empties = [e.player for e in events(state, CardDrawn) if e.empty_library]
    assert empties == [P1, P1, P1, P1], "two failed draws for each of the two hands"


def test_103_5_illegal_answers_are_rejected_and_change_nothing() -> None:
    state = mulligan_game(2)
    request = request_of(state)
    before = copy.deepcopy(state)
    for bad in (
        answer(state, Pick(2)),
        answer(state, PickMany((0,))),
        DecisionAnswer(request.id, P1, Pick(0)),
    ):
        with pytest.raises(InvalidAnswer):
            submit(state, bad)
        assert state == before
    act(state, mulligan(P0), keep(P1))
    act(state, bottom(P0, state.players[0].hand[0]))
    act(state, mulligan(P0))
    hand = state.players[0].hand
    act(state, bottom(P0, hand[0], hand[1]))
    before = copy.deepcopy(state)
    for bad in (answer(state, Order((0,))), answer(state, Order((0, 0))), answer(state, Pick(0))):
        with pytest.raises(InvalidAnswer):
            submit(state, bad)
        assert state == before


def test_103_5_put_on_bottom_rejects_the_wrong_number_of_cards() -> None:
    state = mulligan_game(2)
    act(state, mulligan(P0), keep(P1))
    before = copy.deepcopy(state)
    for bad in (PickMany(()), PickMany((0, 1)), PickMany((7,))):
        with pytest.raises(InvalidAnswer):
            submit(state, answer(state, bad))
        assert state == before


def test_103_5_the_game_is_a_function_of_seed_and_answers() -> None:
    first, second = mulligan_game(3, seed=4), mulligan_game(3, seed=4)
    for state in (first, second):
        act(state, mulligan(P0), keep(P1), mulligan(P2))  # free mulligans (103.5c)
        act(state, mulligan(P0), keep(P2))
        act(state, bottom(P0, state.players[0].hand[0]))
    assert first == second
    assert [p.hand for p in first.players] == [p.hand for p in second.players]


def test_mulligan_states_are_pure_and_consistent_at_every_decision() -> None:
    state = mulligan_game(3)
    steps = [mulligan(P0), keep(P1), mulligan(P2)]
    for step in steps:
        assert invariant_violations(state) == []
        assert state_impurities(state) == []
        act(state, step)
    assert pending_decision(state) is not None
    assert invariant_violations(state) == []
