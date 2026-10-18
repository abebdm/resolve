"""800.4: leaving a multiplayer game, and 104: how such a game ends.

From the pinned CR:

- 104.5: a player who loses leaves the game. 800.4a: all objects they own leave the game; if
  they had priority, priority passes to the next player in turn order still in the game.
- 800.4h: a choice a rule asks of a player who left is made by the next player in turn order.
- 800.4j: a player who leaves during their turn leaves it to continue without an active player;
  where the active player would receive priority, the next player in turn order does.
- 800.4k: a player who left begins no more turns.
- 104.2a: the last player still in the game wins; 104.4a: if all the remaining players lose at
  once, the game is a draw.
- 103.8c, 103.5c: "begins with more than two players": still a multiplayer game after a player
  leaves.

Interpretation (test_800_4a_priority_passes_to_the_next_player_in_the_game and
test_117_4_if_everyone_left_has_passed_the_step_ends): when the holder leaves, earlier passes
still count. If everyone still in the game has passed in succession, that is all players passing
(117.4) and the step ends; otherwise the next player in turn order receives priority.
"""

from __future__ import annotations

import pytest

from resolve.agents.scripted import Choose, choose
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import ChooseOne, PassOption, PlayerOption, PlayLandOption
from resolve.engine import concede
from resolve.engine.api import new_game
from resolve.engine.mulligans import KEEP, MULLIGAN
from resolve.errors import NotImplementedRule
from resolve.events.cards import CardDiscarded
from resolve.events.game import PlayerLeftGame
from resolve.events.turn import StepBegan, TurnBegan
from resolve.state.config import GameConfig
from resolve.state.game import GameState
from resolve.state.ids import PlayerId
from resolve.state.mana import ManaType
from resolve.state.turn import Phase, Step
from resolve.state.zones import EXILE, Zone
from tests.game_fixtures import Passer, deck, pass_until, request_of
from tests.scenario import Scenario, names, run_script

P0, P1, P2, P3 = (PlayerId(p) for p in range(4))


def pass_(player: PlayerId) -> Choose:
    return choose(PassOption(), player=player, kind=DecisionKind.PRIORITY_ACTION)


def board(players: int = 3) -> Scenario:
    scenario = Scenario(players)
    for player in scenario.players:
        scenario.library(player, ["Forest"] * 4)
        scenario.hand(player, ["Forest", "Grizzly Bears"])
    return scenario


def test_800_4a_a_conceding_players_objects_leave_the_game() -> None:
    scenario = board()
    scenario.battlefield(P2, ["Forest", "Grizzly Bears"])
    scenario.graveyard(P2, ["Hill Giant"])
    scenario.exile(P2, ["Forest"])
    scenario.mana(P2, ManaType.GREEN)
    scenario.at(Step.UPKEEP, number=2)
    state = scenario.build()
    owned = sorted(obj for obj, o in state.objects.items() if o.owner == P2)
    library = list(state.player(P2).library)
    old = request_of(state)
    concede(state, P2)
    assert not any(o.owner == P2 for o in state.objects.values())
    player = state.player(P2)
    assert (player.library, player.hand, player.graveyard, player.mana_pool) == ([], [], [], [])
    assert state.exile == [] and state.battlefield == []
    (left,) = [e.record for e in state.event_log if isinstance(e.record, PlayerLeftGame)]
    # design.md §9: the library's objects are counted, not named.
    assert sorted(left.removed + tuple(library)) == owned
    assert left.library_size == len(library) == 4
    assert left.rules[:2] == ("800.4a", "104.5")
    # Player 0's request was withdrawn and asked again with a new id.
    again = request_of(state)
    assert again.player == P0 and again.id != old.id
    assert state.result is None


def test_800_4a_priority_passes_to_the_next_player_in_the_game() -> None:
    """Player 1 holds priority (player 0 passed) and concedes: player 2 receives priority, and
    player 2's pass ends the step, since everyone still in the game has passed in succession."""
    scenario = board()
    scenario.at(Step.UPKEEP, number=2, priority=P1, passed=[P0])
    state = scenario.build()
    concede(state, P1)
    request = request_of(state)
    assert request.player == P2 and request.kind is DecisionKind.PRIORITY_ACTION
    run_script(state, pass_(P2))
    turn = state.turn
    assert turn is not None and turn.step is Step.DRAW


def test_800_4j_the_turn_continues_without_an_active_player() -> None:
    """Player 0 (active) concedes in their upkeep: no draw, no land play, no discard; in each
    step the next player in turn order receives priority first; then player 1's turn."""
    scenario = board()
    scenario.at(Step.UPKEEP, number=2)
    state = scenario.build()
    concede(state, P0)
    agent = Passer()
    pass_until(state, lambda s: s.turn is not None and s.turn.number == 3, agent)
    firsts: list[tuple[Step | None, PlayerId]] = []
    seen: set[Step | None] = set()
    for request, where in agent.requests:
        assert where is not None and where[0] == 2
        if where[2] not in seen:
            seen.add(where[2])
            firsts.append((where[2], request.player))
    assert all(player == P1 for _, player in firsts)
    assert {step for step, _ in firsts} >= {Step.UPKEEP, Step.DRAW, None, Step.END}
    # 305.1: a land is played in a main phase of the player's own turn; this turn is nobody's.
    for request, _ in agent.requests:
        assert isinstance(request.space, ChooseOne)
        assert not any(isinstance(o, PlayLandOption) for o in request.space.options)
    turn = state.turn
    assert turn is not None and turn.active_player == P1
    # Turn 2's draw step drew nothing (no active player); turn 3's hasn't come yet.
    assert [len(state.player(p).hand) for p in (P1, P2)] == [2, 2]


def test_514_1_800_4j_nobody_discards_in_a_turn_without_an_active_player() -> None:
    """Player 0 (active) concedes in their upkeep; player 1 holds nine cards. 514.1 asks only the
    active player to discard, and there is none (800.4h hands over a rule's *choice*, not the
    turn-based action), so player 1 still holds nine cards when their turn begins."""
    scenario = board()
    scenario.hand(P1, ["Forest"] * 7)
    scenario.at(Step.UPKEEP, number=2)
    state = scenario.build()
    concede(state, P0)
    agent = Passer()
    pass_until(state, lambda s: s.turn is not None and s.turn.number == 3, agent)
    assert all(request.kind is DecisionKind.PRIORITY_ACTION for request, _ in agent.requests)
    assert not any(isinstance(e.record, CardDiscarded) for e in state.event_log)
    assert len(state.player(P1).hand) == 9


def test_800_4a_the_objects_of_the_other_players_stay() -> None:
    """Only what the leaving player owns leaves: the others' permanents keep their status and
    damage, and their other zones are untouched."""
    scenario = board()
    forest, bears = scenario.battlefield(P0, ["Forest", "Grizzly Bears"])
    scenario.tap(forest).damage(bears, 1)
    (giant,) = scenario.battlefield(P1, ["Hill Giant"])
    scenario.graveyard(P1, ["Savannah Lions"])
    scenario.exile(P1, ["Forest"])
    scenario.battlefield(P2, ["Forest", "Grizzly Bears"])
    scenario.exile(P2, ["Forest"])
    scenario.at(Step.UPKEEP, number=2)
    state = scenario.build()
    kept = {obj: o for obj, o in state.objects.items() if o.owner != P2}
    concede(state, P2)
    assert state.battlefield == [forest, bears, giant]
    assert state.objects[forest].tapped and state.objects[bears].damage == 1
    assert state.objects == kept
    assert names(state, Zone.graveyard(P1)) == ["Savannah Lions"]
    assert names(state, EXILE) == ["Forest"]


def test_800_4a_a_commander_leaves_the_command_zone_with_its_owner() -> None:
    scenario = Scenario(3, config=GameConfig.commander_game())
    commanders = {player: scenario.commander(player, "Test Daybreaker") for player in (P0, P1, P2)}
    for player in scenario.players:
        scenario.library(player, ["Forest"] * 4)
    scenario.at(Step.UPKEEP, number=2)
    state = scenario.build()
    concede(state, P2)
    assert state.command == [commanders[P0], commanders[P1]]
    assert not any(o.owner == P2 for o in state.objects.values())
    assert state.result is None


def test_117_4_a_player_who_passed_leaves_and_the_others_still_must_pass() -> None:
    """Four players: 0 and 1 passed, 2 holds priority. Player 1 leaves: player 2 is asked again
    and passes, and player 3, who hasn't passed, receives priority: not everyone still in the
    game has passed in succession yet (117.4)."""
    scenario = board(4)
    scenario.at(Step.UPKEEP, number=2, active=P0, priority=P2, passed=[P0, P1])
    state = scenario.build()
    concede(state, P1)
    assert request_of(state).player == P2
    run_script(state, pass_(P2))
    request = request_of(state)
    assert (request.kind, request.player) == (DecisionKind.PRIORITY_ACTION, P3)
    turn = state.turn
    assert turn is not None and turn.step is Step.UPKEEP


def test_117_4_the_holder_leaves_after_a_player_who_passed_left() -> None:
    """Four players: 0 and 1 passed, 2 holds priority. Player 1 leaves, then player 2: two
    passes are recorded and two players remain, but player 3 hasn't passed, so player 3
    receives priority (800.4a) instead of the step ending."""
    scenario = board(4)
    scenario.at(Step.UPKEEP, number=2, active=P0, priority=P2, passed=[P0, P1])
    state = scenario.build()
    concede(state, P1)
    concede(state, P2)
    request = request_of(state)
    assert (request.kind, request.player) == (DecisionKind.PRIORITY_ACTION, P3)
    turn = state.turn
    assert turn is not None and turn.step is Step.UPKEEP


def test_117_4_a_player_who_hadnt_passed_leaves_and_the_next_pass_ends_the_step() -> None:
    """Four players: 0 and 1 passed, 2 holds priority. Player 3, who hadn't passed, leaves:
    player 2's pass is the last one needed, and the step ends (117.4)."""
    scenario = board(4)
    scenario.at(Step.UPKEEP, number=2, active=P0, priority=P2, passed=[P0, P1])
    state = scenario.build()
    concede(state, P3)
    assert request_of(state).player == P2
    run_script(state, pass_(P2))
    turn = state.turn
    assert turn is not None and turn.step is Step.DRAW
    assert request_of(state).player == P0


def test_800_4k_players_who_left_take_no_turns() -> None:
    scenario = board(4)
    scenario.at(Step.END, number=1)
    state = scenario.build()
    concede(state, P1)
    concede(state, P2)
    pass_until(state, lambda s: s.turn is not None and s.turn.number == 3)
    began = [e.record for e in state.event_log if isinstance(e.record, TurnBegan)]
    assert [(b.number, b.player) for b in began] == [(2, P3), (3, P0)]


def test_104_2a_the_last_player_in_the_game_wins() -> None:
    state = board().at(Step.UPKEEP, number=2).build()
    concede(state, P1)
    assert state.result is None
    concede(state, P0)
    assert state.result is not None and state.result.winners == (P2,)


def test_104_2a_two_of_three_losing_at_once_leaves_the_third_the_winner() -> None:
    scenario = board()
    scenario.life(P0, 0)
    scenario.life(P2, 0)
    scenario.at(Step.UPKEEP, number=2)
    state = scenario.build()
    assert state.result is not None and state.result.winners == (P1,)


def test_704_5a_a_loss_in_multiplayer_leaves_the_game_going_on() -> None:
    """Replaces M1.2's 800.4a gap: one of three players loses; the other two play on."""
    scenario = board()
    scenario.life(P2, 0)
    scenario.battlefield(P2, ["Forest"])
    scenario.at(Step.UPKEEP, number=2)
    state = scenario.build()
    assert state.result is None
    assert state.player(P2).left_game and state.battlefield == []
    assert request_of(state).player == P0


def test_104_4a_everyone_left_in_the_game_losing_at_once_is_a_draw() -> None:
    scenario = board()
    scenario.at(Step.UPKEEP, number=2)
    state = scenario.build()
    concede(state, P2)
    state.player(P0).life = 0  # as if damage had been dealt while player 0 held priority
    state.player(P1).life = 0
    run_script(state, pass_(P0))
    assert state.result is not None and state.result.is_draw


def test_three_player_game_by_decking() -> None:
    """10-card decks, everyone keeps and passes. Libraries hold 3 after the opening hands; with
    three players nobody skips a draw (103.8c), so P0 draws on turns 1, 4, 7, P1 on 2, 5, 8 and
    P2 on 3, 6, 9. P0 draws from an empty library on turn 10 and leaves; turn 11 is P1's, who
    loses the same way; P2 wins (104.2a)."""
    state = new_game(GameConfig.standard(), [deck(10, 0)] * 3, seed=2)
    run_script(state, _start(state))
    pass_until(state, lambda s: False)
    assert state.result is not None and state.result.winners == (P2,)
    turn = state.turn
    assert turn is not None and (turn.number, turn.active_player, turn.step) == (11, P1, Step.DRAW)
    assert state.player(P0).left_game and state.player(P1).left_game


def _start(state: GameState) -> Choose:
    return choose(PlayerOption(P0), kind=DecisionKind.CHOOSE_STARTING_PLAYER)


def test_103_8c_103_5c_still_multiplayer_after_a_concession_during_mulligans() -> None:
    state = new_game(GameConfig.standard(), [deck(10, 10)] * 3, seed=1)
    run_script(state, _start(state))
    concede(state, P2)  # while player 0 decides about a mulligan
    run_script(state, choose(MULLIGAN, player=P0))  # the free first mulligan still applies
    run_script(state, choose(KEEP, player=P1))
    run_script(state, choose(KEEP, player=P0))
    assert len(state.player(P0).hand) == 7  # 103.5c: nothing put on the bottom
    turn = state.turn
    assert turn is not None and turn.number == 1
    pass_until(state, lambda s: s.turn is not None and s.turn.phase is Phase.PRECOMBAT_MAIN)
    assert len(state.player(P0).hand) == 8  # 103.8c: the starting player drew
    assert [type(e.record) for e in state.event_log].count(StepBegan) >= 3


def test_800_4h_a_player_who_left_isnt_asked_about_mulligans() -> None:
    state = new_game(GameConfig.standard(), [deck(10, 10)] * 3, seed=1)
    run_script(state, _start(state))
    run_script(state, choose(KEEP, player=P0))
    concede(state, P2)  # while player 1 decides
    run_script(state, choose(KEEP, player=P1))
    turn = state.turn
    assert turn is not None and turn.number == 1
    assert all(o.owner != P2 for o in state.objects.values())


def test_800_4a_leaving_with_control_of_another_players_permanent_is_a_gap() -> None:
    """Control-changing effects can't exist yet, so an object controlled by a player but
    owned by another can only come from the scenario builder; leaving with one is a gap."""
    scenario = board()
    scenario.battlefield(P2, ["Forest"], owner=P0)
    scenario.at(Step.UPKEEP, number=2)
    state = scenario.build()
    with pytest.raises(NotImplementedRule) as gap:
        concede(state, P2)
    assert gap.value.rule == "800.4a"


def test_117_4_if_everyone_left_has_passed_the_step_ends() -> None:
    """Players 0 and 1 passed; player 2 holds priority and concedes: all players still in the
    game have passed in succession, so the step ends (117.4), with no new priority."""
    scenario = board()
    scenario.at(Step.UPKEEP, number=2, priority=P2, passed=[P0, P1])
    state = scenario.build()
    concede(state, P2)
    turn = state.turn
    assert turn is not None and turn.step is Step.DRAW
    assert request_of(state).player == P0
