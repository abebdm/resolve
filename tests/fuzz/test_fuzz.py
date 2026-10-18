"""Random-agent fuzz games (design.md §14), and tests that the harness catches what it should.

Every M0 game stops at ``NotImplementedRule("103.5: ...")``, which the harness treats as the end
of the game (roadmap M0). The game seeds are fixed, so the suite is deterministic.
"""

from __future__ import annotations

import dataclasses
import io
from contextlib import redirect_stdout

import pytest

from resolve.agents.random_agent import RandomAgent
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.request import DecisionRequest, validate_answer
from resolve.decisions.spaces import (
    AnswerSpace,
    ChooseNumber,
    ChooseOne,
    ChooseOrder,
    ChooseSubset,
    Distribute,
    PlayerOption,
)
from resolve.engine.api import new_game, view_for
from resolve.engine.deck import Deck
from resolve.engine.view import PlayerView
from resolve.errors import InvalidAnswer
from resolve.state.config import GameConfig
from resolve.state.game import GameState
from resolve.state.ids import PlayerId
from resolve.tasks import Task
from tests.engine_support import (
    AsksLaxly,
    AskTwice,
    CheckThatChanges,
    CrashOnAnswer,
    EndGame,
    GapOnAnswer,
    HoldsValue,
    RejectsEverything,
    Unrepeatable,
    running,
)
from tests.game_fixtures import DAYBREAKER, deck
from tests.scenario import Scenario
from tools import fuzz as fuzz_tool
from tools.fuzz import FuzzFailure, fuzz_game, fuzz_run, invalid_answers, state_problems

PLAYER_COUNTS = [2, 3, 4, 5, 6]
SEEDS = range(12)


def decks_for(players: int, commander: bool, seed: int) -> list[Deck]:
    """Decks of varying sizes (including empty), with one commander each in Commander games."""
    commanders = [DAYBREAKER] if commander else []
    return [
        deck(forests=(seed + seat) % 5, elves=seat % 3, commanders=commanders)
        for seat in range(players)
    ]


@pytest.mark.parametrize("commander", [False, True], ids=["standard", "commander"])
@pytest.mark.parametrize("players", PLAYER_COUNTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_random_agent_games_complete_with_every_check_passing(
    seed: int, players: int, commander: bool
) -> None:
    config = GameConfig.commander_game() if commander else GameConfig.standard()
    result = fuzz_game(config, decks_for(players, commander, seed), seed)
    assert result.gap is not None and result.gap.startswith("103.5: ")
    assert result.answers == 1  # 103.1 is the only decision M0 asks
    state = result.state
    assert state.starting_player is not None
    if commander:
        assert len(state.command) == players  # 103.2c
    else:
        assert state.command == []


def test_fuzz_games_are_reproducible_from_their_seed() -> None:
    decks = decks_for(4, True, 3)
    first = fuzz_game(GameConfig.commander_game(), decks, 3)
    again = fuzz_game(GameConfig.commander_game(), decks, 3)
    assert first.state == again.state
    starters = {
        fuzz_game(GameConfig.standard(), decks_for(4, False, seed), seed).state.starting_player
        for seed in range(30)
    }
    assert starters == {0, 1, 2, 3}


def test_a_game_that_ends_reports_no_gap() -> None:
    result = fuzz_run(
        lambda: running(AskTwice(PlayerId(1)), EndGame((PlayerId(0),))),
        [RandomAgent(1), RandomAgent(2)],
        describe="test",
    )
    assert result.gap is None
    assert result.answers == 2
    assert result.rejected > 0  # AskTwice rejects odd numbers, so the agent answered again
    assert result.state.result is not None and result.state.result.winners == (0,)


# --- The harness catches broken engines --------------------------------------------------------


def fuzz(
    *tasks: Task,
    beneath: Task | None = None,
    check_copies: bool = True,
    max_answers: int = 50,
) -> None:
    """Fuzz a ``running(*tasks)`` game, with ``beneath`` at the bottom of the task stack."""

    def make() -> GameState:
        state = running(*tasks)
        if beneath is not None:
            state.tasks.insert(0, beneath)
        return state

    fuzz_run(
        make,
        [RandomAgent(1), RandomAgent(2)],
        describe="broken game",
        check_copies=check_copies,
        max_answers=max_answers,
    )


def test_a_disallowed_gap_is_a_failure() -> None:
    with pytest.raises(FuzzFailure, match=r"gap that isn't allowed: 601\.2: a test gap"):
        fuzz(GapOnAnswer("601.2"))
    config = GameConfig.standard()
    with pytest.raises(FuzzFailure, match=r"isn't allowed: 103\.5"):
        fuzz_game(config, decks_for(2, False, 0), 0, allowed_gaps=())


def test_an_allowed_gap_ends_the_game() -> None:
    result = fuzz_run(
        lambda: running(GapOnAnswer("601.2")),
        [RandomAgent(1), RandomAgent(2)],
        describe="test",
        allowed_gaps=("601.2",),
    )
    assert result.gap == "601.2: a test gap"


def test_an_engine_error_is_a_failure_naming_the_game() -> None:
    with pytest.raises(FuzzFailure, match="broken game: EngineError: crashed"):
        fuzz(CrashOnAnswer())


def test_an_impure_state_is_a_failure() -> None:
    with pytest.raises(FuzzFailure, match="isn't pure data"):
        fuzz(AskTwice(PlayerId(0)), beneath=HoldsValue(value=frozenset({1})))


def test_nondeterministic_resumption_is_a_failure() -> None:
    """design.md §5: a state copied mid-task must resume exactly as the original."""
    with pytest.raises(FuzzFailure, match="copy differs"):
        fuzz(Unrepeatable(), EndGame(()))


def test_a_replay_that_differs_is_a_failure() -> None:
    """design.md §12: replaying the answers must reproduce the identical state."""
    with pytest.raises(FuzzFailure, match="replay doesn't reproduce"):
        fuzz(Unrepeatable(), EndGame(()), check_copies=False)


def test_a_check_answer_that_changes_the_state_is_a_failure() -> None:
    with pytest.raises(FuzzFailure, match=r"the rejected answer .* changed the state"):
        fuzz(CheckThatChanges(), EndGame(()), check_copies=False)


def test_an_accepted_invalid_answer_is_a_failure() -> None:
    with pytest.raises(FuzzFailure, match=r"the invalid answer .* was accepted"):
        fuzz(AsksLaxly(), EndGame(()))


def test_a_decision_rejecting_every_answer_is_a_failure() -> None:
    with pytest.raises(FuzzFailure, match="in a row were rejected"):
        fuzz(RejectsEverything())


def test_a_game_that_never_ends_is_a_failure() -> None:
    """The ``Hold`` task under ``running`` asks forever."""
    with pytest.raises(FuzzFailure, match="didn't end within 5 answers"):
        fuzz(max_answers=5)


def test_state_problems_finds_a_broken_zone() -> None:
    state = new_game(GameConfig.standard(), decks_for(2, False, 1), 1)
    assert state_problems(state) == []
    state.players[0].library.append(state.players[1].library[0])
    assert any("listed in" in problem for problem in state_problems(state))


def test_state_problems_finds_a_view_naming_a_hidden_card(monkeypatch: pytest.MonkeyPatch) -> None:
    """402.3: other players don't see the cards in a hand; the harness checks every view."""
    scenario = Scenario(2)
    scenario.hand(PlayerId(0), ["Llanowar Elves"])
    state = scenario.build(AskTwice(PlayerId(0)))
    assert state_problems(state) == []

    def leaky_view(state: GameState, viewer: PlayerId) -> PlayerView:
        view = view_for(state, viewer)
        leaked = tuple(
            dataclasses.replace(
                summary,
                hand=tuple(dataclasses.replace(obj, name="Llanowar Elves") for obj in summary.hand),
            )
            for summary in view.players
        )
        return dataclasses.replace(view, players=leaked)

    monkeypatch.setattr(fuzz_tool, "view_for", leaky_view)
    assert state_problems(state) == ["player 1's view of object 1 is wrong"]


def test_state_problems_finds_a_view_holding_another_players_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = Scenario(2).build(AskTwice(PlayerId(0)))

    def everyone_sees_the_request(state: GameState, viewer: PlayerId) -> PlayerView:
        return dataclasses.replace(view_for(state, viewer), request=state.pending)

    monkeypatch.setattr(fuzz_tool, "view_for", everyone_sees_the_request)
    assert state_problems(state) == ["player 1's view holds the wrong request"]


# --- The invalid answers the harness probes with -----------------------------------------------

OPTIONS = tuple(PlayerOption(PlayerId(p)) for p in range(3))
SPACES: list[AnswerSpace] = [
    ChooseOne(OPTIONS),
    ChooseSubset(OPTIONS, 1, 2),
    ChooseSubset(OPTIONS, 0, 3),
    ChooseOrder(OPTIONS),
    ChooseNumber(0, 4),
    ChooseNumber(2),
    Distribute(OPTIONS[:2], 5),
]


@pytest.mark.parametrize("space", SPACES, ids=repr)
def test_every_probe_answer_is_invalid(space: AnswerSpace) -> None:
    request = DecisionRequest(4, PlayerId(1), DecisionKind.MAY, space, "?", ("117.1",))
    probes = invalid_answers(request, players=3)
    assert len(probes) >= 5
    for probe in probes:
        with pytest.raises(InvalidAnswer):
            validate_answer(request, probe)


def test_the_command_line_runs_games_and_reports_a_benchmark() -> None:
    output = io.StringIO()
    with redirect_stdout(output):
        status = fuzz_tool.main(["--games", "10", "--seed", "100", "--players", "2", "4"])
    text = output.getvalue()
    assert status == 0
    assert "10 games passed: 10 answers accepted" in text
    assert "Endings: 103.5 x10" in text
    assert "games per second" in text


@pytest.mark.parametrize("args", [["--games", "0"], ["--players", "1"], ["--players"]])
def test_the_command_line_refuses_bad_arguments(args: list[str]) -> None:
    with pytest.raises(SystemExit) as exit_info, redirect_stdout(io.StringIO()):
        fuzz_tool.main(args)
    assert exit_info.value.code == 2
