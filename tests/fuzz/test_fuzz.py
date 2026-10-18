"""Random-agent fuzz games (design.md §14), and tests that the harness catches what it should.

Until the turn structure exists (M1.2), every game stops after the mulligans at
``NotImplementedRule("103.8: ...")``, which the harness treats as the end of the game. The game
seeds are fixed, so the suite is deterministic.
"""

from __future__ import annotations

import dataclasses
import hashlib
import io
import os
import pickle
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from resolve.agents.base import Agent
from resolve.agents.random_agent import RandomAgent
from resolve.agents.scripted import ScriptedAgent, Step
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.request import DecisionAnswer, DecisionRequest, validate_answer
from resolve.decisions.spaces import (
    AnswerSpace,
    ChooseNumber,
    ChooseOne,
    ChooseOrder,
    ChooseSubset,
    Distribute,
    Number,
    PlayerOption,
)
from resolve.engine import loop as engine_loop
from resolve.engine import view as engine_view
from resolve.engine.api import new_game, view_for
from resolve.engine.deck import Deck
from resolve.engine.view import PlayerView
from resolve.errors import InvalidAnswer
from resolve.events.base import AnswerRecord
from resolve.state.config import GameConfig
from resolve.state.game import GameObject, GameState
from resolve.state.ids import PlayerId
from resolve.state.zones import Zone
from resolve.tasks import Task
from tests import scryfall_fixtures as fx
from tests.engine_support import (
    AsksLaxly,
    AskTwice,
    CheckThatChanges,
    CrashOnAnswer,
    EndGame,
    GapOnAnswer,
    HoldsValue,
    LeaksALibraryCard,
    LossyPickle,
    RejectsEverything,
    Unrepeatable,
    running,
)
from tests.game_fixtures import DAYBREAKER, deck
from tests.scenario import Scenario, run_script
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
    assert result.gap is not None and result.gap.startswith("103.8: ")
    # 103.1, then at least one mulligan declaration per player (103.5).
    assert result.answers >= 1 + players
    state = result.state
    assert state.starting_player is not None
    decks = decks_for(players, commander, seed)
    for player in state.players:
        held = len(player.hand) + len(player.library)
        assert held == len(decks[player.id].cards), "every card is in the hand or library"
        assert len(player.hand) <= 7
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
    agents: Sequence[Agent] | None = None,
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
        agents or [RandomAgent(1), RandomAgent(2)],
        describe="broken game",
        check_copies=check_copies,
        max_answers=max_answers,
    )


def test_a_disallowed_gap_is_a_failure() -> None:
    with pytest.raises(FuzzFailure, match=r"gap that isn't allowed: 601\.2: a test gap"):
        fuzz(GapOnAnswer("601.2"))
    config = GameConfig.standard()
    with pytest.raises(FuzzFailure, match=r"isn't allowed: 103\.8"):
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


def test_a_redacted_entry_that_still_shows_a_library_card_is_a_failure() -> None:
    """design.md §9: library object IDs survive shuffles, so no other player may see them."""
    with pytest.raises(FuzzFailure, match="shows player 1's view a drawn library card"):
        fuzz(LeaksALibraryCard(), AskTwice(PlayerId(0)))


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
    script = ScriptedAgent([Step(Number(1)), Step(Number(0))])  # 1 is rejected
    with pytest.raises(FuzzFailure, match=r"the rejected answer .* changed the state"):
        fuzz(CheckThatChanges(), EndGame(()), agents=[script, script], check_copies=False)


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


def test_a_pickle_round_trip_that_changes_the_state_is_a_failure() -> None:
    """CLAUDE.md rule 5: the state must survive pickle at any moment. A NaN is equal to itself
    only by identity (and, since Python 3.13, dataclasses compare field by field, so not even
    then): a copy of a state holding one compares unequal before any answer is given."""
    with pytest.raises(FuzzFailure, match=r"a (deep|pickled) copy differs from the state after 0"):
        fuzz(AskTwice(PlayerId(0)), beneath=HoldsValue(value=float("nan")))


def test_an_engine_ignoring_the_request_id_and_player_is_caught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """design.md §6: an answer must echo the pending request's id and player."""

    def space_only(request: DecisionRequest, answer: DecisionAnswer) -> None:
        request.space.validate(answer.value)

    monkeypatch.setattr(engine_loop, "validate_answer", space_only)
    with pytest.raises(FuzzFailure, match=r"the invalid answer DecisionAnswer\(request_id=2"):
        fuzz_game(GameConfig.standard(), decks_for(3, False, 1), 1)


def test_a_pickle_round_trip_that_loses_data_is_a_failure() -> None:
    """The pickled-copy check on its own: a deep copy of this state is faithful, a pickle isn't."""
    with pytest.raises(FuzzFailure, match="a pickled copy differs from the state after 0 answers"):
        fuzz(AskTwice(PlayerId(0)), beneath=LossyPickle(7))


def test_an_engine_ignoring_only_the_player_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    """design.md §6: an answer from a player other than the decider is rejected, even when its
    request id and value are right."""

    def no_player_check(request: DecisionRequest, answer: DecisionAnswer) -> None:
        if answer.request_id != request.id:
            raise InvalidAnswer("wrong request")
        request.space.validate(answer.value)

    monkeypatch.setattr(engine_loop, "validate_answer", no_player_check)
    state = new_game(GameConfig.standard(), decks_for(3, False, 1), 1)
    chooser = state.pending.player if state.pending else 0
    other = (chooser + 1) % 3
    with pytest.raises(
        FuzzFailure, match=rf"the invalid answer DecisionAnswer\(request_id=1, player={other},"
    ):
        fuzz_game(GameConfig.standard(), decks_for(3, False, 1), 1)


def test_a_replay_that_asks_someone_else_is_a_failure() -> None:
    """design.md §12: the replay stops at the first decision that doesn't match the record."""
    seeds = iter([1, 2])

    def make() -> GameState:
        return Scenario(2, starting_player=None).build(
            AskTwice(PlayerId(next(seeds) % 2)), EndGame(())
        )

    with pytest.raises(FuzzFailure, match="the replay failed: ScriptError: step 1 expects player"):
        fuzz_run(make, [RandomAgent(1), RandomAgent(2)], describe="test")


def test_a_replay_that_ends_early_is_a_failure() -> None:
    games = iter([(AskTwice(PlayerId(0)), EndGame(())), (EndGame(()),)])

    def make() -> GameState:
        return Scenario(2).build(*next(games))

    with pytest.raises(FuzzFailure, match="the replay ended differently"):
        fuzz_run(make, [RandomAgent(1), RandomAgent(2)], describe="test")


def test_a_fuzz_game_over_a_multiplayer_board_with_hidden_cards() -> None:
    """400.2 and 402.3 in a real run: hands seen by their owners and by players who know a card,
    graveyards and the battlefield by everyone, and answers only by their player."""

    def make() -> GameState:
        scenario = Scenario(4)
        scenario.hand(PlayerId(0), ["Llanowar Elves", "Forest"])
        scenario.add(
            "Forest", owner=PlayerId(1), zone=Zone.hand(PlayerId(1)), known_to=[PlayerId(3)]
        )
        scenario.graveyard(PlayerId(2), ["Forest", "Llanowar Elves"])
        scenario.battlefield(PlayerId(3), ["Llanowar Elves"], owner=PlayerId(2))
        scenario.library(PlayerId(3), ["Forest"] * 3)
        return scenario.build(*(AskTwice(PlayerId(p)) for p in (2, 0, 3, 1)), EndGame(()))

    agents = [RandomAgent(seat + 10) for seat in range(4)]
    result = fuzz_run(make, agents, describe="test")
    assert result.gap is None and result.answers == 8


def leaking(monkeypatch: pytest.MonkeyPatch, change: Callable[[PlayerView], PlayerView]) -> None:
    """Make the harness see views changed by ``change``."""

    def view(state: GameState, viewer: PlayerId) -> PlayerView:
        return change(view_for(state, viewer))

    monkeypatch.setattr(fuzz_tool, "view_for", view)


def board() -> GameState:
    """Three players: a hand card known to player 2, a graveyard card, a decision pending."""
    scenario = Scenario(3)
    scenario.add("Forest", owner=PlayerId(0), zone=Zone.hand(PlayerId(0)), known_to=[PlayerId(2)])
    scenario.graveyard(PlayerId(1), ["Llanowar Elves", "Forest"])
    state = scenario.build(AskTwice(PlayerId(0)), EndGame(()))
    run_script(state, Step(Number(2)))  # puts an answer, visible to player 0 only, in the log
    return state


def test_state_problems_accepts_correct_views() -> None:
    assert state_problems(board()) == []


def test_state_problems_finds_a_view_showing_every_log_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """design.md §7: an answer is visible only to the player who gave it."""
    state = board()
    leaking(monkeypatch, lambda view: dataclasses.replace(view, log=tuple(state.event_log)))
    assert state_problems(state) == [
        "player 1's view shows the wrong log entries",
        "player 2's view shows the wrong log entries",
    ]


def test_state_problems_finds_an_answer_logged_for_everyone() -> None:
    state = board()
    entry = next(e for e in state.event_log if isinstance(e.record, AnswerRecord))
    state.event_log[entry.index] = dataclasses.replace(entry, visible_to=None)
    assert f"log entry {entry.index} shows an answer to other players" in state_problems(state)


def test_state_problems_doesnt_trust_the_engines_knowledge_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """402.3: if the engine showed every hand to everyone, the harness's own oracle notices."""
    state = board()

    def everyone_knows(obj: GameObject, viewer: PlayerId) -> bool:
        return True

    monkeypatch.setattr(engine_view, "is_known_to", everyone_knows)
    assert state_problems(state) == ["player 1's view of object 1 is wrong"]


def test_state_problems_finds_a_hand_card_hidden_from_a_player_who_knows_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """400.2: player 2 knows player 0's hand card, so their view names it."""
    state = board()

    def ignores_known_to(obj: GameObject, viewer: PlayerId) -> bool:
        return obj.zone.kind.is_public or viewer == obj.owner

    monkeypatch.setattr(engine_view, "is_known_to", ignores_known_to)
    assert state_problems(state) == ["player 2's view of object 1 is wrong"]


def test_state_problems_finds_a_hidden_graveyard_card(monkeypatch: pytest.MonkeyPatch) -> None:
    """404.2: graveyards are public."""
    state = board()

    def hide_graveyards(view: PlayerView) -> PlayerView:
        players = tuple(
            dataclasses.replace(
                summary,
                graveyard=tuple(dataclasses.replace(obj, name=None) for obj in summary.graveyard),
            )
            for summary in view.players
        )
        return dataclasses.replace(view, players=players)

    leaking(monkeypatch, hide_graveyards)
    problems = state_problems(state)
    assert len(problems) == 6 and all("view of object" in problem for problem in problems)


def test_state_problems_finds_a_dropped_hand_and_a_reordered_graveyard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """402.3: hands may be counted, so a view must list every hidden card; 404.2: graveyards
    keep their order."""
    state = board()

    def drop_and_reorder(view: PlayerView) -> PlayerView:
        players = tuple(
            dataclasses.replace(summary, hand=(), graveyard=summary.graveyard[::-1])
            for summary in view.players
        )
        return dataclasses.replace(view, players=players)

    leaking(monkeypatch, drop_and_reorder)
    problems = state_problems(state)
    assert "player 1's view shows the wrong objects in player 0's hand" in problems
    assert "player 0's view shows the wrong objects in player 1's graveyard" in problems


def test_replays_dont_depend_on_the_hash_seed() -> None:
    """CLAUDE.md rule 6: no hash ordering. Two processes with different PYTHONHASHSEEDs play the
    same fuzz game to byte-identical states."""
    script = (
        "import hashlib, pickle\n"
        "from resolve.state.config import GameConfig\n"
        "from tests.fuzz.test_fuzz import decks_for\n"
        "from tools.fuzz import fuzz_game\n"
        "state = fuzz_game(GameConfig.commander_game(), decks_for(5, True, 7), 7).state\n"
        "print(hashlib.sha256(pickle.dumps(state)).hexdigest())\n"
    )
    root = Path(__file__).resolve().parents[2]
    digests: set[str] = set()
    for hash_seed in ("1", "2"):
        env = dict(os.environ, PYTHONHASHSEED=hash_seed, PYTHONPATH=str(root))
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        digests.add(completed.stdout.strip())
    state = fuzz_game(GameConfig.commander_game(), decks_for(5, True, 7), 7).state
    assert digests == {hashlib.sha256(pickle.dumps(state)).hexdigest()}


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
    probes = invalid_answers(request, 3, RandomAgent(1).random_value(space))
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
    found = re.search(r"10 games passed: (\d+) answers accepted, (\d+) rejected\.", text)
    assert found is not None
    # Each game: 103.1 and at least one mulligan declaration per player (103.5).
    assert int(found.group(1)) >= 5 * (1 + 2) + 5 * (1 + 4)
    assert "Endings: 103.8 x10" in text
    assert "games per second" in text


@pytest.mark.parametrize("args", [["--games", "0"], ["--players", "1"], ["--players"]])
def test_the_command_line_refuses_bad_arguments(args: list[str]) -> None:
    with pytest.raises(SystemExit) as exit_info, redirect_stdout(io.StringIO()):
        fuzz_tool.main(args)
    assert exit_info.value.code == 2


@pytest.mark.parametrize(
    ("args", "formats"),
    [
        ([], "Formats: commander x4, standard x6"),
        (["--commander"], "Formats: commander x10"),
        (["--format", "commander"], "Formats: commander x10"),
        (["--format", "standard"], "Formats: standard x10"),
    ],
)
def test_the_command_line_plays_the_chosen_formats(args: list[str], formats: str) -> None:
    """Each format plays one round of the player counts, in turn: with two counts, games 0-1
    are standard, 2-3 Commander, 4-5 standard, 6-7 Commander and 8-9 standard."""
    output = io.StringIO()
    with redirect_stdout(output):
        status = fuzz_tool.main(["--games", "10", "--players", "2", "3", *args])
    assert status == 0
    assert formats in output.getvalue()


def test_the_command_line_refuses_unimplemented_decks(tmp_path: Path) -> None:
    """Decks are refused, never approximated (design.md §11); no card is implemented yet."""
    data = tmp_path / "data"
    fx.write_snapshot(data, cards=[fx.FOREST])
    deck_file = tmp_path / "deck.txt"
    deck_file.write_text("Mainboard\n10 Forest\n", encoding="utf-8")
    output = io.StringIO()
    with redirect_stdout(output):
        status = fuzz_tool.main(["--deck", str(deck_file), "--data-dir", str(data)])
    assert status == 1
    assert "'Forest' is not implemented" in output.getvalue()


def test_the_reproduce_command_names_the_failing_game() -> None:
    with pytest.raises(FuzzFailure) as failure:
        fuzz_game(GameConfig.commander_game(), decks_for(3, True, 8), 8, allowed_gaps=())
    assert "--games 1 --seed 8 --players 3 --commander" in str(failure.value)
