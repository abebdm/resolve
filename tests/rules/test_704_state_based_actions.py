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
- 704.5f: a creature with 0 or less toughness is put into its owner's graveyard (not destroyed,
  701.8b). 704.5g: a creature with toughness above 0 and damage at least its toughness is
  destroyed (701.8a). 404.3: cards put into one graveyard at the same time are ordered by their
  owner.
- A game that continues after a player leaves (800.4) is not implemented until M1.5.
"""

from __future__ import annotations

import copy

import pytest

from resolve.agents.scripted import choose
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.request import DecisionAnswer
from resolve.decisions.spaces import ObjectOption, Order, Pick
from resolve.engine.api import new_game, pending_decision, submit, view_for
from resolve.errors import InvalidAnswer, NotImplementedRule
from resolve.events.game import GameEnded, PlayerLost
from resolve.events.permanents import PermanentDestroyed, PutIntoGraveyard
from resolve.state.config import GameConfig
from resolve.state.game import GameState
from resolve.state.ids import PlayerId
from resolve.state.turn import Step
from resolve.state.zones import Zone
from tests.game_fixtures import answer, deck, pass_until, request_of
from tests.scenario import Scenario, names, run_script

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
    # Adjacent: one check; then each loser leaves (104.5) and the game ends.
    assert kinds == ["PlayerLost", "PlayerLost", "PlayerLeftGame", "PlayerLeftGame", "GameEnded"]
    assert [lost.player for lost in losses(state)] == [P1, P2]  # APNAP order of the record


def test_104_4a_everyone_losing_together_in_multiplayer_is_a_draw() -> None:
    scenario = Scenario(4)
    for player in scenario.players:
        scenario.life(player, 0)
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    assert state.result is not None and state.result.is_draw


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


# --- 704.5f and 704.5g: creatures ---------------------------------------------------------------


def creature_moves(state: GameState) -> list[PutIntoGraveyard | PermanentDestroyed]:
    return [
        e.record
        for e in state.event_log
        if isinstance(e.record, PutIntoGraveyard | PermanentDestroyed)
    ]


def test_704_5f_a_creature_with_0_toughness_goes_to_its_owners_graveyard() -> None:
    """Controlled by player 1, owned by player 0: it goes to player 0's graveyard (704.5f), and
    it is put there, not destroyed (701.8b)."""
    scenario = Scenario(2)
    (wisp,) = scenario.battlefield(P1, ["Test Wisp"], owner=P0)
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    assert state.battlefield == []
    assert names(state, Zone.graveyard(P0)) == ["Test Wisp"]
    assert state.player(P1).graveyard == []
    (moved,) = creature_moves(state)
    assert isinstance(moved, PutIntoGraveyard) and moved.obj == wisp
    assert moved.rules[0] == "704.5f"
    assert moved.moved in state.player(P0).graveyard  # 400.7: a new object
    assert request_of(state).player == P0  # then priority, the game going on


@pytest.mark.parametrize(("damage", "dies"), [(1, False), (2, True), (3, True)])
def test_704_5g_lethal_damage_destroys_a_creature(damage: int, dies: bool) -> None:
    scenario = Scenario(2)
    (bears,) = scenario.battlefield(P1, ["Grizzly Bears"])
    scenario.damage(bears, damage)
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    if dies:
        (destroyed,) = creature_moves(state)
        assert isinstance(destroyed, PermanentDestroyed) and destroyed.obj == bears
        assert destroyed.rules[0] == "704.5g"
        assert names(state, Zone.graveyard(P1)) == ["Grizzly Bears"]
    else:
        assert creature_moves(state) == []
        assert state.objects[bears].damage == 1


def test_704_5g_needs_toughness_above_0_so_only_704_5f_applies() -> None:
    scenario = Scenario(2)
    (wisp,) = scenario.battlefield(P0, ["Test Wisp"])
    scenario.damage(wisp, 2)
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    (moved,) = creature_moves(state)  # one event, not both
    assert isinstance(moved, PutIntoGraveyard)


def test_704_5g_only_creatures_are_destroyed_by_damage() -> None:
    scenario = Scenario(2)
    (forest,) = scenario.battlefield(P0, ["Forest"])
    scenario.damage(forest, 5)
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    assert creature_moves(state) == []
    assert state.battlefield == [forest]


def test_704_3_creatures_and_players_are_handled_in_the_same_event() -> None:
    """A creature dying and a player losing are one check; the game then ends (104.2a)."""
    scenario = Scenario(2)
    scenario.battlefield(P0, ["Test Wisp"])
    scenario.life(P1, 0)
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    kinds = [type(e.record).__name__ for e in state.event_log]
    assert kinds == ["PutIntoGraveyard", "PlayerLost", "PlayerLeftGame", "GameEnded"]
    assert state.result is not None and state.result.winners == (P0,)


def test_404_3_creatures_dying_together_are_ordered_by_their_owner() -> None:
    """Two of player 1's creatures die in one check (704.3); player 1 orders them in the
    graveyard (404.3, listed top to bottom). Player 0's single creature needs no order."""
    scenario = Scenario(2)
    lions, giant = scenario.battlefield(P1, ["Savannah Lions", "Hill Giant"])
    (bears,) = scenario.battlefield(P0, ["Grizzly Bears"])
    scenario.damage(lions, 1).damage(giant, 3).damage(bears, 2)
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    request = request_of(state)
    assert request.kind is DecisionKind.ORDER_CARDS and request.player == P1
    assert request.rules == ("404.3",)
    assert len(state.battlefield) == 3  # nothing has moved yet
    run_script(state, choose(ObjectOption(lions), ObjectOption(giant), player=P1))
    assert names(state, Zone.graveyard(P1)) == ["Hill Giant", "Savannah Lions"]  # top last
    assert names(state, Zone.graveyard(P0)) == ["Grizzly Bears"]
    assert len(creature_moves(state)) == 3
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION


def test_404_3_the_other_order() -> None:
    scenario = Scenario(2)
    lions, giant = scenario.battlefield(P1, ["Savannah Lions", "Hill Giant"])
    scenario.damage(lions, 1).damage(giant, 3)
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    run_script(state, choose(ObjectOption(giant), ObjectOption(lions), player=P1))
    assert names(state, Zone.graveyard(P1)) == ["Savannah Lions", "Hill Giant"]


def test_208_2_a_star_power_or_toughness_is_a_gap() -> None:
    scenario = Scenario(2)
    scenario.battlefield(P0, ["Test Star"])
    scenario.at(Step.UPKEEP)
    with pytest.raises(NotImplementedRule) as gap:
        scenario.build()
    assert gap.value.rule == "208.2"


def test_101_4_404_3_owners_order_their_cards_in_apnap_order_from_the_active_player() -> None:
    """Turn 2, player 1 active (player 0 started): player 1 orders first, then player 0."""
    scenario = Scenario(2)
    mine = scenario.battlefield(P1, ["Grizzly Bears", "Hill Giant"])
    theirs = scenario.battlefield(P0, ["Grizzly Bears", "Savannah Lions"])
    for obj in (*mine, *theirs):
        scenario.damage(obj, 3)
    scenario.at(Step.UPKEEP, active=P1, number=2)
    state = scenario.build()
    first = request_of(state)
    assert (first.kind, first.player) == (DecisionKind.ORDER_CARDS, P1)
    run_script(state, choose(*(ObjectOption(o) for o in mine), player=P1))
    second = request_of(state)
    assert (second.kind, second.player) == (DecisionKind.ORDER_CARDS, P0)


def test_101_4_404_3_three_players_asked_from_the_active_player_only_with_two_cards() -> None:
    scenario = Scenario(3)
    p0 = scenario.battlefield(P0, ["Grizzly Bears", "Hill Giant"])
    p2 = scenario.battlefield(P2, ["Grizzly Bears", "Hill Giant"])
    (single,) = scenario.battlefield(P1, ["Savannah Lions"])
    for obj in (*p0, *p2, single):
        scenario.damage(obj, 3)
    scenario.at(Step.UPKEEP, active=P1, number=2)
    state = scenario.build()
    asked: list[PlayerId] = []
    for cards in ((p2, P2), (p0, P0)):
        request = request_of(state)
        assert request.kind is DecisionKind.ORDER_CARDS
        asked.append(request.player)
        run_script(state, choose(*(ObjectOption(o) for o in cards[0]), player=cards[1]))
    assert asked == [P2, P0]  # APNAP from player 1; player 1 has one card, so isn't asked
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION
    assert names(state, Zone.graveyard(P1)) == ["Savannah Lions"]


def test_404_3_cards_are_grouped_by_owner_not_controller() -> None:
    """Player 1 controls both, but they go to different graveyards: nothing to order."""
    scenario = Scenario(2)
    (borrowed,) = scenario.battlefield(P1, ["Grizzly Bears"], owner=P0)
    (own,) = scenario.battlefield(P1, ["Hill Giant"])
    scenario.damage(borrowed, 2).damage(own, 3)
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION
    assert names(state, Zone.graveyard(P0)) == ["Grizzly Bears"]
    assert names(state, Zone.graveyard(P1)) == ["Hill Giant"]


def test_404_3_an_invalid_graveyard_order_is_rejected() -> None:
    scenario = Scenario(2)
    lions, giant = scenario.battlefield(P1, ["Savannah Lions", "Hill Giant"])
    scenario.damage(lions, 1).damage(giant, 3)
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    request = request_of(state)
    before = copy.deepcopy(state)
    for bad in (
        DecisionAnswer(request.id, P1, Order((0,))),
        DecisionAnswer(request.id, P1, Order((1, 1))),
        DecisionAnswer(request.id, P0, Order((0, 1))),
    ):
        with pytest.raises(InvalidAnswer):
            submit(state, bad)
        assert state == before


def test_120_6_damage_stays_until_the_cleanup_step() -> None:
    scenario = Scenario(2)
    (bears,) = scenario.battlefield(P1, ["Grizzly Bears"])
    scenario.damage(bears, 1)
    scenario.library(P0, ["Forest"])
    scenario.at(Step.UPKEEP, number=3)
    state = scenario.build()
    pass_until(state, lambda s: s.turn is not None and s.turn.step is Step.END)
    assert state.objects[bears].damage == 1
