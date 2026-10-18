"""704: state-based actions 704.5a and 704.5b, and the end of the game they cause (104).

From the pinned CR:

- 117.5, 704.3: each time a player would receive priority, every applicable state-based action
  is performed at once, as a single event, repeated until none apply.
- 704.5a: a player with 0 or less life loses. 704.5b: a player who attempted to draw from an
  empty library since the last check loses (121.4: "the next time a player would receive
  priority"). An empty library by itself loses nothing.
- 104.5: a player who loses leaves the game. 104.2a: a player still in the game wins once all
  their opponents have left. 104.4a: if all the players remaining lose simultaneously, the game
  is a draw.
- A game that continues after a player leaves (800.4) is not implemented until M1.5.
"""

from __future__ import annotations

import pytest

from resolve.decisions.kinds import DecisionKind
from resolve.decisions.request import DecisionAnswer
from resolve.decisions.spaces import Pick
from resolve.engine.api import new_game, pending_decision, submit, view_for
from resolve.errors import NotImplementedRule
from resolve.events.game import GameEnded, PlayerLost
from resolve.state.config import GameConfig
from resolve.state.game import GameState
from resolve.state.ids import PlayerId
from resolve.state.turn import Step
from tests.game_fixtures import answer, deck, pass_until, request_of
from tests.scenario import Scenario

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)


def losses(state: GameState) -> list[PlayerLost]:
    return [e.record for e in state.event_log if isinstance(e.record, PlayerLost)]


@pytest.mark.parametrize("life", [0, -3])
def test_704_5a_a_player_with_0_or_less_life_loses(life: int) -> None:
    scenario = Scenario(2)
    scenario.life(P1, life)
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    assert state.result is not None and state.result.winners == (P0,)  # 104.2a
    assert pending_decision(state) is None
    (lost,) = losses(state)
    assert lost.player == P1 and lost.rules[0] == "704.5a"
    assert state.player(P1).lost and not state.player(P0).lost
    ended = state.event_log[-1].record
    assert isinstance(ended, GameEnded) and ended.rules == ("104.2a",)


def test_704_5a_a_player_at_1_life_doesnt_lose() -> None:
    scenario = Scenario(2)
    scenario.life(P1, 1)
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    assert state.result is None
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION
    assert losses(state) == []


def test_704_5a_life_is_checked_when_a_resumed_round_gives_priority() -> None:
    """117.5: a scenario resuming with player 1 about to receive priority checks first."""
    scenario = Scenario(2)
    scenario.life(P0, 0)
    scenario.at(Step.UPKEEP, priority=P1, passed=[P0])
    state = scenario.build()
    assert state.result is not None and state.result.winners == (P1,)


def test_704_5b_drawing_from_an_empty_library_loses_before_priority_in_the_draw_step() -> None:
    scenario = Scenario(2)
    scenario.library(P1, ["Forest"] * 5)
    scenario.at(Step.DRAW, begin=True, number=3)  # player 0's library is empty
    state = scenario.build()
    assert state.result is not None and state.result.winners == (P1,)
    (lost,) = losses(state)
    assert lost.player == P0
    assert lost.rules[:2] == ("704.5b", "121.4")
    turn = state.turn
    assert turn is not None and turn.step is Step.DRAW and turn.priority is None


def test_704_5b_an_empty_library_alone_doesnt_lose() -> None:
    scenario = Scenario(2)
    scenario.at(Step.UPKEEP, number=3)  # both libraries are empty
    state = scenario.build()
    assert state.result is None
    assert request_of(state).player == P0
    assert not state.player(P0).drew_from_empty_library


def test_121_4_704_5b_a_short_deck_loses_at_the_first_upkeep() -> None:
    """Player 1's deck has 5 cards: drawing seven attempts two draws from an empty library
    (121.4), which loses the next time a player would receive priority (704.5b), which is the
    first upkeep (103.5 has no priority), even though they kept.

    727.3 (the same draws remembered across mulligans) supports this; 121.4 and 704.5b govern.
    """
    state = new_game(GameConfig.standard(), [deck(10, 10), deck(5, 0)], seed=1)
    submit(state, answer(state, Pick(0)))  # player 0 starts
    assert state.player(P1).drew_from_empty_library
    pass_until(state, lambda s: False)
    assert state.result is not None and state.result.winners == (P0,)
    turn = state.turn
    assert turn is not None and (turn.number, turn.step) == (1, Step.UPKEEP)
    (lost,) = losses(state)
    assert lost.player == P1 and lost.rules[0] == "704.5b"


def test_104_4a_both_players_losing_together_is_a_draw() -> None:
    scenario = Scenario(2)
    scenario.life(P0, 0)
    scenario.life(P1, -1)
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    assert state.result is not None and state.result.winners == ()
    assert state.result.is_draw
    ended = state.event_log[-1].record
    assert isinstance(ended, GameEnded) and ended.rules == ("104.4a",)


def test_104_4a_different_losses_at_once_are_also_a_draw() -> None:
    """704.5a for one player and 704.5b for the other, in one check."""
    scenario = Scenario(2)
    scenario.life(P1, 0)
    scenario.library(P1, ["Forest"])
    scenario.at(Step.DRAW, begin=True, number=3)  # player 0 draws from an empty library
    state = scenario.build()
    assert state.result is not None and state.result.is_draw
    assert sorted((lost.player, lost.rules[0]) for lost in losses(state)) == [
        (P0, "704.5b"),
        (P1, "704.5a"),
    ]


def test_117_5_704_3_state_based_actions_are_performed_as_one_event() -> None:
    """Two players of three lose in the same check: had they lost one at a time, the game would
    have continued with two players. Simultaneously, only player 0 is left and wins (104.2a)."""
    scenario = Scenario(3)
    scenario.life(P1, 0)
    scenario.life(P2, -2)
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    assert state.result is not None and state.result.winners == (P0,)
    kinds = [type(e.record).__name__ for e in state.event_log]
    assert kinds == ["PlayerLost", "PlayerLost", "GameEnded"]  # adjacent: one check
    assert [lost.player for lost in losses(state)] == [P1, P2]  # APNAP order of the record


def test_104_4a_everyone_losing_together_in_multiplayer_is_a_draw() -> None:
    scenario = Scenario(4)
    for player in scenario.players:
        scenario.life(player, 0)
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    assert state.result is not None and state.result.is_draw


def test_800_4a_a_loss_that_leaves_two_players_in_the_game_is_a_gap_until_m1_5() -> None:
    scenario = Scenario(3)
    scenario.life(P2, 0)
    scenario.at(Step.UPKEEP)
    with pytest.raises(NotImplementedRule) as gap:
        scenario.build()
    assert gap.value.rule == "800.4a"


def test_the_views_show_who_lost_and_the_result() -> None:
    scenario = Scenario(2)
    scenario.life(P1, 0)
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    for viewer in (P0, P1):
        view = view_for(state, viewer)
        assert [summary.lost for summary in view.players] == [False, True]
        assert view.result == state.result


def test_117_5_state_based_actions_are_checked_again_after_a_pass() -> None:
    """117.5: each time a player would receive priority, also within a round after a pass."""
    scenario = Scenario(2)
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    request = request_of(state)
    assert request.player == P0
    state.player(P0).life = 0  # as if something had happened while player 0 held priority
    submit(state, DecisionAnswer(request.id, P0, Pick(0)))  # pass
    assert state.result is not None and state.result.winners == (P1,)
    assert pending_decision(state) is None
