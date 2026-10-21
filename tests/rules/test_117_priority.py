"""117: timing and priority.

Expected behavior, from the pinned CR:

- 117.3a: the active player receives priority at the beginning of each step and main phase,
  after its turn-based actions.
- 117.3d: a player who passes gives priority to the next player in turn order.
- 117.4, 500.2: when all players pass in succession with the stack empty, the step or phase
  ends; with an object on the stack, it resolves (608.1: test_608_resolving.py).
- 117.1a: an instant may be cast whenever its player has priority; any other spell only in its
  player's main phase with an empty stack (301.1, 302.1, 307.1). 903.8: a commander may be cast
  from the command zone. 305.1, 305.2, 305.3, 116.2a: a land may be played in its player's own
  main phase with an empty stack, once per turn; 305.9: a land is never cast.
- Casting is tested in test_601_casting.py, playing lands and mana abilities in test_305_lands.py
  and test_605_mana_abilities.py.
"""

from __future__ import annotations

import copy

import pytest

from resolve.agents.scripted import Choose, choose
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.request import DecisionAnswer
from resolve.decisions.spaces import (
    CastSpellOption,
    ChooseOne,
    Option,
    PassOption,
    Pick,
    PlayLandOption,
)
from resolve.engine.api import submit
from resolve.errors import InvalidAnswer, NotImplementedRule
from resolve.events.turn import PriorityPassed
from resolve.state.config import GameConfig
from resolve.state.game import GameState
from resolve.state.ids import PlayerId
from resolve.state.spell import COMMANDER, FROM_HAND, NORMAL
from resolve.state.turn import Phase, Step
from tests.game_fixtures import request_of
from tests.scenario import Scenario, run_script

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)


def options(state: GameState) -> tuple[Option, ...]:
    request = request_of(state)
    assert request.kind is DecisionKind.PRIORITY_ACTION
    assert isinstance(request.space, ChooseOne)
    return request.space.options


def pass_(player: PlayerId) -> Choose:
    return choose(PassOption(), player=player, kind=DecisionKind.PRIORITY_ACTION)


def where(state: GameState) -> tuple[Phase, Step | None]:
    turn = state.turn
    assert turn is not None
    return (turn.phase, turn.step)


@pytest.mark.parametrize(
    "at",
    [Step.UPKEEP, Step.DRAW, Phase.PRECOMBAT_MAIN, Step.BEGINNING_OF_COMBAT, Step.END],
)
def test_117_3a_the_active_player_receives_priority_first(at: Phase | Step) -> None:
    scenario = Scenario(3)
    for player in scenario.players:
        scenario.library(player, ["Forest"])
    scenario.at(at, active=P1, number=4, begin=True)
    state = scenario.build()
    request = request_of(state)
    assert request.player == P1
    assert request.kind is DecisionKind.PRIORITY_ACTION
    assert request.rules == ("117.1",)
    turn = state.turn
    assert turn is not None and turn.priority == P1 and turn.passed == []


def test_117_3d_passing_gives_priority_to_the_next_player_in_turn_order() -> None:
    """3 players, player 1 active: priority goes 1, 2, 0 (seating order wraps around)."""
    scenario = Scenario(3)
    scenario.at(Step.UPKEEP, active=P1, number=2)
    state = scenario.build()
    holders = [request_of(state).player]
    for _ in range(2):
        run_script(state, pass_(holders[-1]))
        holders.append(request_of(state).player)
        assert where(state) == (Phase.BEGINNING, Step.UPKEEP)
    assert holders == [P1, P2, P0]
    turn = state.turn
    assert turn is not None and turn.passed == [P1, P2] and turn.priority == P0
    passes = [e.record for e in state.event_log if isinstance(e.record, PriorityPassed)]
    assert [p.player for p in passes] == [P1, P2]
    assert all(p.rules == ("117.3d",) for p in passes)


def test_117_4_500_2_a_step_ends_when_all_pass_in_succession_with_an_empty_stack() -> None:
    scenario = Scenario(2)
    scenario.library(P0, ["Forest"])
    scenario.at(Step.UPKEEP, number=3)
    state = scenario.build()
    run_script(state, pass_(P0))
    assert where(state) == (Phase.BEGINNING, Step.UPKEEP)  # one pass isn't enough
    run_script(state, pass_(P1))
    assert where(state) == (Phase.BEGINNING, Step.DRAW)
    assert request_of(state).player == P0
    turn = state.turn
    assert turn is not None and turn.passed == []


def test_117_4_players_who_passed_before_the_scenario_count_toward_the_succession() -> None:
    scenario = Scenario(3)
    scenario.at(Phase.POSTCOMBAT_MAIN, active=P0, priority=P2, passed=[P0, P1])
    state = scenario.build()
    assert request_of(state).player == P2
    run_script(state, pass_(P2))
    assert where(state) == (Phase.ENDING, Step.END)


def test_117_1a_noninstant_spells_and_lands_need_the_players_own_main_phase() -> None:
    scenario = Scenario(2)
    forest, elves, shock, ponder = scenario.hand(
        P0, ["Forest", "Llanowar Elves", "Test Shock", "Test Ponder"]
    )
    scenario.hand(P1, ["Forest", "Llanowar Elves", "Test Shock"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    assert options(state) == (
        PassOption(),
        PlayLandOption(forest),
        CastSpellOption(elves, NORMAL, FROM_HAND),
        CastSpellOption(shock, NORMAL, FROM_HAND),
        CastSpellOption(ponder, NORMAL, FROM_HAND),
    )


def test_117_1a_only_instants_outside_the_main_phase() -> None:
    scenario = Scenario(2)
    scenario.hand(P0, ["Forest", "Llanowar Elves", "Test Ponder"])
    (shock,) = scenario.hand(P0, ["Test Shock"])
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    assert options(state) == (PassOption(), CastSpellOption(shock, NORMAL, FROM_HAND))


def test_117_1a_305_3_only_instants_on_another_players_turn() -> None:
    """The nonactive player, with priority in the active player's main phase."""
    scenario = Scenario(2)
    scenario.hand(P1, ["Forest", "Llanowar Elves", "Test Ponder"])
    (shock,) = scenario.hand(P1, ["Test Shock"])
    scenario.at(Phase.PRECOMBAT_MAIN, priority=P1, passed=[P0])
    state = scenario.build()
    assert request_of(state).player == P1
    assert options(state) == (PassOption(), CastSpellOption(shock, NORMAL, FROM_HAND))


def test_117_1a_305_1_nothing_but_instants_with_an_object_on_the_stack() -> None:
    scenario = Scenario(2)
    scenario.hand(P0, ["Forest", "Llanowar Elves"])
    (shock,) = scenario.hand(P0, ["Test Shock"])
    scenario.stack(P1, ["Test Ponder"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    assert options(state) == (PassOption(), CastSpellOption(shock, NORMAL, FROM_HAND))


def test_305_2_no_second_land_in_a_turn() -> None:
    scenario = Scenario(2)
    scenario.hand(P0, ["Forest"])
    (elves,) = scenario.hand(P0, ["Llanowar Elves"])
    scenario.at(Phase.POSTCOMBAT_MAIN, lands_played=1)
    state = scenario.build()
    assert options(state) == (PassOption(), CastSpellOption(elves, NORMAL, FROM_HAND))


def test_903_8_a_commander_may_be_cast_from_the_command_zone_by_its_owner() -> None:
    scenario = Scenario(2, config=GameConfig.commander_game())
    mine = scenario.commander(P0, "Test Daybreaker")
    scenario.commander(P1, "Test Daybreaker")
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    assert options(state) == (PassOption(), CastSpellOption(mine, NORMAL, COMMANDER))


def test_903_8_a_commander_is_cast_with_the_timing_of_its_type() -> None:
    """A creature commander isn't offered in the upkeep (302.1)."""
    scenario = Scenario(2, config=GameConfig.commander_game())
    scenario.commander(P0, "Test Daybreaker")
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    assert options(state) == (PassOption(),)


def test_109_3_a_split_card_in_hand_is_a_gap() -> None:
    """709.4: its characteristics are those of both halves combined; not implemented yet."""
    scenario = Scenario(2)
    scenario.hand(P0, ["Test Spark // Test Frost"])
    scenario.at(Step.UPKEEP)
    with pytest.raises(NotImplementedRule) as gap:
        scenario.build()
    assert gap.value.rule == "109.3"


def test_priority_answers_outside_the_options_are_rejected() -> None:
    scenario = Scenario(2)
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    request = request_of(state)
    before = copy.deepcopy(state)
    for bad in (
        DecisionAnswer(request.id, P1, Pick(0)),  # not P1's priority
        DecisionAnswer(request.id, P0, Pick(1)),  # only one option (pass)
        DecisionAnswer(request.id + 1, P0, Pick(0)),  # another request
    ):
        with pytest.raises(InvalidAnswer):
            submit(state, bad)
        assert state == before
