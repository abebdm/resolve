"""104.3a: conceding, through ``resolve.engine.concede`` (design.md §3).

From the pinned CR and the approved plan (★2, ★3):

- 104.3a: a player can concede at any time; they leave the game immediately and lose.
- A concession withdraws the pending request (its id goes stale); the game then goes on, and
  whoever must decide next is asked with a new request.
- ``concede`` rejects, changing nothing, when the game is over or the player already left.
- Replays are the seed plus the ordered inputs: answers and concessions (design.md §12).
"""

from __future__ import annotations

import copy
import pickle

import pytest

from resolve.agents.replay import replay
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.request import DecisionAnswer
from resolve.decisions.spaces import ChooseOne, Pick, PickMany, PlayerOption
from resolve.engine import concede
from resolve.engine.api import new_game, pending_decision, submit, view_for
from resolve.errors import EngineError, InvalidAnswer
from resolve.events.game import Conceded, GameEnded, PlayerLeftGame, PlayerLost
from resolve.state.config import GameConfig
from resolve.state.game import GameState
from resolve.state.ids import PlayerId
from resolve.state.invariants import invariant_violations, state_impurities
from resolve.state.turn import Step
from tests.game_fixtures import Passer, deck, pass_until, request_of, started_game
from tests.scenario import Scenario

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)


def at_upkeep(players: int = 2) -> Scenario:
    scenario = Scenario(players)
    for player in scenario.players:
        scenario.library(player, ["Forest"] * 3)
    scenario.at(Step.UPKEEP, number=2, active=P1)
    return scenario


@pytest.mark.parametrize("who", [P1, P0])
def test_104_3a_conceding_ends_a_two_player_game(who: PlayerId) -> None:
    """Player 1 holds priority. Either player concedes: the other one wins (104.2a)."""
    state = at_upkeep().build()
    assert request_of(state).player == P1
    concede(state, who)
    other = P0 if who == P1 else P1
    assert state.result is not None and state.result.winners == (other,)
    assert pending_decision(state) is None
    records = [type(e.record) for e in state.event_log]
    assert records == [Conceded, PlayerLost, PlayerLeftGame, GameEnded]
    lost = state.event_log[1].record
    assert isinstance(lost, PlayerLost) and lost.rules[0] == "104.3a"
    assert all(e.visible_to is None for e in state.event_log)  # public
    assert state.player(who).lost and state.player(who).left_game


def test_concede_withdraws_the_request_and_asks_again_with_a_new_id() -> None:
    state = at_upkeep(3).build()
    request = request_of(state)
    assert request.player == P1
    concede(state, P0)  # someone else concedes
    again = request_of(state)
    assert again.player == P1 and again.kind is DecisionKind.PRIORITY_ACTION
    assert again.id != request.id
    with pytest.raises(InvalidAnswer):
        submit(state, DecisionAnswer(request.id, P1, Pick(0)))  # the old id is stale


@pytest.mark.parametrize("when", ["over", "left"])
def test_concede_rejects_a_finished_game_or_a_player_who_left(when: str) -> None:
    state = at_upkeep(3).build()
    if when == "over":
        concede(state, P0)
        concede(state, P2)
        assert state.result is not None
        target = P1
    else:
        concede(state, P2)
        target = P2
    before = copy.deepcopy(state)
    with pytest.raises(InvalidAnswer):
        concede(state, target)
    assert state == before


def test_concede_rejects_an_unknown_player() -> None:
    state = at_upkeep().build()
    before = copy.deepcopy(state)
    with pytest.raises(EngineError, match="no player 5"):
        concede(state, PlayerId(5))
    assert state == before


def test_concede_during_103_1_in_a_two_player_game() -> None:
    state = new_game(GameConfig.standard(), [deck(5, 5), deck(5, 5)], seed=1)
    chooser = request_of(state).player
    concede(state, chooser)
    other = P0 if chooser == P1 else P1
    assert state.result is not None and state.result.winners == (other,)


def test_800_4h_concede_during_103_1_the_next_player_chooses() -> None:
    """The chooser leaves: the next player in seating order (turn order isn't set yet) makes
    the choice, and only players still in the game can be chosen."""
    state = new_game(GameConfig.standard(), [deck(5, 5)] * 3, seed=1)
    chooser = request_of(state).player
    concede(state, chooser)
    request = request_of(state)
    assert request.kind is DecisionKind.CHOOSE_STARTING_PLAYER
    assert request.player == PlayerId((chooser + 1) % 3)
    assert isinstance(request.space, ChooseOne)
    assert chooser not in [o.player for o in request.space.options if isinstance(o, PlayerOption)]


def test_concession_states_are_pure_and_consistent() -> None:
    state = at_upkeep(3).build()
    concede(state, P2)
    assert invariant_violations(state) == []
    assert state_impurities(state) == []
    assert copy.deepcopy(state) == state
    assert pickle.loads(pickle.dumps(state)) == state


def test_design_12_a_replay_with_concessions_is_identical() -> None:
    """Rebuild from config, decks and seed, then the ordered answers and concessions."""
    config, decks, seed = GameConfig.standard(), [deck(10, 0)] * 3, 5

    def make() -> GameState:
        return new_game(config, decks, seed)

    state = make()
    agent = Passer()
    submit(state, DecisionAnswer(request_of(state).id, request_of(state).player, Pick(0)))
    pass_until(state, lambda s: s.turn is not None and s.turn.number == 2, agent)
    concede(state, P1)
    pass_until(state, lambda s: s.turn is not None and s.turn.number == 4, agent)
    again = make()
    replay(again, state.event_log)
    assert again == state


def test_a_started_game_can_be_conceded_by_everyone_but_one() -> None:
    state = started_game(4, decks=[deck(10, 0)] * 4)
    for player in (P1, P2, PlayerId(3)):
        concede(state, player)
    assert state.result is not None and state.result.winners == (P0,)


def test_concede_asks_a_pending_mulligan_again_with_a_new_id() -> None:
    state = new_game(GameConfig.standard(), [deck(10, 10)] * 3, seed=1)
    submit(state, DecisionAnswer(request_of(state).id, request_of(state).player, Pick(0)))
    asked = request_of(state)
    assert asked.kind is DecisionKind.MULLIGAN
    leaver = next(p for p in (P0, P1, P2) if p != asked.player)
    concede(state, leaver)
    again = request_of(state)
    assert (again.kind, again.player, again.space) == (asked.kind, asked.player, asked.space)
    assert again.id != asked.id
    with pytest.raises(InvalidAnswer):
        submit(state, DecisionAnswer(asked.id, asked.player, Pick(0)))


def test_concede_asks_a_pending_discard_again_with_a_new_id() -> None:
    scenario = Scenario(3)
    for player in scenario.players:
        scenario.library(player, ["Forest"] * 3)
    scenario.hand(P0, ["Forest"] * 9)
    scenario.at(Step.CLEANUP, active=P0)
    state = scenario.build()
    asked = request_of(state)
    assert (asked.kind, asked.player) == (DecisionKind.DISCARD, P0)
    concede(state, P2)
    again = request_of(state)
    assert (again.kind, again.player, again.space) == (asked.kind, asked.player, asked.space)
    assert again.id != asked.id
    with pytest.raises(InvalidAnswer):
        submit(state, DecisionAnswer(asked.id, P0, PickMany((0, 1))))


def test_an_answer_from_a_player_who_left_is_rejected() -> None:
    """Player 0 left; an answer in their name to the pending request (with its current id) is
    refused and changes nothing. It is refused because only the asked player may answer
    (design.md §6), and a player who left is never asked (800.4h; the invariants check it), so
    no separate check for players who left is needed."""
    state = at_upkeep(3).build()
    concede(state, P0)
    request = request_of(state)
    assert request.player == P1
    before = copy.deepcopy(state)
    with pytest.raises(InvalidAnswer):
        submit(state, DecisionAnswer(request.id, P0, Pick(0)))
    assert state == before


def test_design_9_leaving_doesnt_show_library_objects() -> None:
    """``PlayerLeftGame`` is public. Library object IDs survive shuffles and are never shown to
    other players (design.md §9), so the event names the objects that left from the other zones
    and only counts the library."""
    scenario = at_upkeep(3)
    scenario.hand(P2, ["Forest", "Grizzly Bears"])
    scenario.graveyard(P2, ["Hill Giant"])
    state = scenario.build()
    library = list(state.player(P2).library)
    others = sorted(o for o, obj in state.objects.items() if obj.owner == P2 and o not in library)
    concede(state, P2)
    (entry,) = [e for e in state.event_log if isinstance(e.record, PlayerLeftGame)]
    left = entry.record
    assert isinstance(left, PlayerLeftGame)
    assert entry.visible_to is None
    assert sorted(left.removed) == others
    assert left.library_size == len(library) == 3
    for viewer in (P0, P1):
        shown = [
            e.record for e in view_for(state, viewer).log if isinstance(e.record, PlayerLeftGame)
        ]
        assert shown == [left]
