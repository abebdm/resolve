"""Random-agent fuzz games (design.md §14), and tests that the harness catches what it should.

A game ends when it is over or at one of the harness's allowed gaps (``ALLOWED_GAPS``: actions
the engine can't take yet, and a game that would continue after a player leaves). The game
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
from resolve.state.mana import ManaType
from resolve.state.turn import Step as TurnStep
from resolve.state.zones import COMMAND, Zone
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
    PatientAgent,
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
    """Decks of varying sizes, with one commander each in Commander games.

    Most decks hold 7 to 11 cards, so games get past the opening hands into turns and priority
    (a deck of 6 or fewer would make every player draw from an empty library during 103.5 and
    lose at the first state-based-action check, 704.5b). Every deck holds an elf, so random
    agents soon try to cast it and the game stops at the 601.2 gap. Seat 1's deck is empty in
    one game of four.
    """
    commanders = [DAYBREAKER] if commander else []
    return [
        deck(forests=0, elves=0, commanders=commanders)
        if seat == 1 and seed % 4 == 3
        else deck(forests=6 + (seed + seat) % 4, elves=1 + seat % 2, commanders=commanders)
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
    state = result.state
    if result.gap is None:
        assert state.result is not None
    else:
        assert result.gap.split(": ")[0] in fuzz_tool.ALLOWED_GAPS
    decks = decks_for(players, commander, seed)
    # 103.1, then at least one mulligan declaration per player with cards to draw (103.5).
    assert result.answers >= 1 + sum(1 for d in decks if d.cards)
    assert state.starting_player is not None
    if all(len(d.cards) >= 8 for d in decks):
        # Nobody can draw from an empty library before their first priority (103.8, 504.1), so
        # the game reached a priority decision (117.3a).
        asked = [e.record.kind for e in state.event_log if isinstance(e.record, AnswerRecord)]
        assert DecisionKind.PRIORITY_ACTION in asked, "the game reached priority"
    active = None if state.turn is None else state.turn.active_player
    for player in state.players:
        held = sum(1 for o in state.objects.values() if o.owner == player.id and o.zone != COMMAND)
        assert held == len(decks[player.id].cards), "every card of the deck is still in the game"
        # 514.1: only the active player can be above seven, by the card drawn this turn.
        assert len(player.hand) <= (8 if player.id == active else 7)
    if commander:
        assert len(state.command) == players  # 103.2c
    else:
        assert state.command == []


@pytest.mark.parametrize("players", [2, 3, 4])
@pytest.mark.parametrize("seed", range(2))
def test_patient_random_agents_play_many_turns_with_every_check_passing(
    seed: int, players: int
) -> None:
    """Agents that usually pass reach later turns: draws, discards, decking (704.5b)."""
    decks = [deck(forests=6 + seat, elves=2) for seat in range(players)]
    result = fuzz_run(
        lambda: new_game(GameConfig.standard(), decks, seed),
        [PatientAgent(seed * 10 + seat) for seat in range(players)],
        describe=f"patient game seed {seed}, {players} players",
        # The copy and invalid-answer checks are slow in long games; one game of each size has them.
        check_copies=seed == 0,
        probe_invalid=seed == 1,
    )
    state = result.state
    if result.gap is None:
        assert state.result is not None
    else:
        assert result.gap.split(": ")[0] in fuzz_tool.ALLOWED_GAPS
    assert state.turn is not None


@pytest.mark.parametrize("seed", range(3))
def test_random_agents_finish_two_player_land_only_games(seed: int) -> None:
    """M1.3: with only lands, random agents play every game to its end (704.5b decking)."""
    decks = [deck(forests=9, elves=0), deck(forests=10, elves=0)]
    result = fuzz_game(GameConfig.standard(), decks, seed, check_copies=seed == 0)
    assert result.gap is None
    state = result.state
    assert state.result is not None and len(state.result.winners) <= 1
    assert state.battlefield, "lands were played"


def test_patient_games_include_decking_and_discards() -> None:
    """Across these seeds some game ends by decking (704.5b) and some player discards (514.1)."""
    endings: list[str] = []
    discarded = False
    for seed in range(4):
        decks = [deck(forests=8, elves=0), deck(forests=9, elves=0)]
        result = fuzz_run(
            lambda decks=decks, seed=seed: new_game(GameConfig.standard(), decks, seed),
            [PatientAgent(seed), PatientAgent(seed + 100)],
            describe=f"patient seed {seed}",
            check_copies=False,
            probe_invalid=False,
        )
        endings.append(result.gap or "over")
        discarded = discarded or any(p.graveyard for p in result.state.players)
        if result.gap is None:
            assert result.state.result is not None
    assert "over" in endings
    assert discarded


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
    allowed_gaps: Sequence[str] = fuzz_tool.ALLOWED_GAPS,
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
        allowed_gaps=allowed_gaps,
        describe="broken game",
        check_copies=check_copies,
        max_answers=max_answers,
    )


def test_a_disallowed_gap_is_a_failure() -> None:
    with pytest.raises(FuzzFailure, match=r"gap that isn't allowed: 601\.2: a test gap"):
        fuzz(GapOnAnswer("601.2"), allowed_gaps=())
    config = GameConfig.standard()
    with pytest.raises(FuzzFailure, match=r"isn't allowed: 601\.2"):
        fuzz_game(config, [deck(10, 2), deck(10, 2)], 2, allowed_gaps=())


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


@pytest.mark.parametrize(
    ("how", "message"),
    [
        ("redacted", "shows player 1's view a drawn library card"),
        ("public", "shows player 1's view a drawn library card"),
        ("bottom", "shows player 1's view the bottomed cards"),
    ],
)
def test_a_log_entry_that_shows_another_players_library_card_is_a_failure(
    how: str, message: str
) -> None:
    """design.md §9: library object IDs survive shuffles, so no other player may see them."""
    with pytest.raises(FuzzFailure, match=message):
        fuzz(LeaksALibraryCard(how), AskTwice(PlayerId(0)))


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
    # The decks are empty, so 103.1 is the only question: a zero-card hand can't mulligan (103.5),
    # and every player, having drawn from an empty library, loses before the first priority
    # (704.5b): every game is a draw (104.4a).
    assert int(found.group(1)) == 10
    assert "Endings: game over x10" in text
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
    """Decks are refused, never approximated (design.md §11)."""
    data = tmp_path / "data"
    fx.write_snapshot(data, cards=[fx.FOREST, fx.LLANOWAR_ELVES])
    deck_file = tmp_path / "deck.txt"
    deck_file.write_text("Mainboard\n10 Forest\n1 Llanowar Elves\n", encoding="utf-8")
    output = io.StringIO()
    with redirect_stdout(output):
        status = fuzz_tool.main(["--deck", str(deck_file), "--data-dir", str(data)])
    assert status == 1
    assert "'Llanowar Elves' is not implemented" in output.getvalue()


def test_the_command_line_plays_decks_from_the_snapshot(tmp_path: Path) -> None:
    """Two-player Forest decks: random agents play lands and tap them until a player draws from
    an empty library (704.5b), so every game ends."""
    data = tmp_path / "data"
    fx.write_snapshot(data, cards=[fx.FOREST])
    deck_file = tmp_path / "deck.txt"
    deck_file.write_text("Mainboard\n9 Forest\n", encoding="utf-8")
    output = io.StringIO()
    with redirect_stdout(output):
        status = fuzz_tool.main(
            ["--games", "3", "--players", "2", "--format", "standard", "--deck", str(deck_file),
             "--data-dir", str(data)]
        )  # fmt: skip
    assert status == 0
    assert "Endings: game over x3" in output.getvalue()


def test_the_reproduce_command_names_the_failing_game() -> None:
    with pytest.raises(FuzzFailure) as failure:
        decks = [deck(10, 2, commanders=[DAYBREAKER]) for _ in range(3)]
        fuzz_game(GameConfig.commander_game(), decks, 8, allowed_gaps=())
    assert "--games 1 --seed 8 --players 3 --commander" in str(failure.value)


def turn_board() -> GameState:
    """Two players in turn 2's upkeep, player 1 active and about to act."""
    scenario = Scenario(2)
    scenario.at(TurnStep.UPKEEP, active=PlayerId(1), number=2)
    return scenario.build()


def test_state_problems_finds_a_view_misreporting_the_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    state = turn_board()
    assert state_problems(state) == []

    def wrong_step(view: PlayerView) -> PlayerView:
        assert view.turn is not None
        return dataclasses.replace(view, turn=dataclasses.replace(view.turn, step=TurnStep.DRAW))

    leaking(monkeypatch, wrong_step)
    problems = state_problems(state)
    assert len(problems) == 2 and all("shows the turn as" in p for p in problems)


def test_state_problems_finds_a_view_hiding_the_priority_holder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = turn_board()
    leaking(
        monkeypatch,
        lambda view: dataclasses.replace(
            view, turn=dataclasses.replace(view.turn, priority=None) if view.turn else None
        ),
    )
    assert len(state_problems(state)) == 2


def test_state_problems_finds_a_view_misreporting_a_loss(monkeypatch: pytest.MonkeyPatch) -> None:
    state = turn_board()

    def everyone_lost(view: PlayerView) -> PlayerView:
        players = tuple(dataclasses.replace(summary, lost=True) for summary in view.players)
        return dataclasses.replace(view, players=players)

    leaking(monkeypatch, everyone_lost)
    problems = state_problems(state)
    assert "player 0's view misreports whether player 1 lost" in problems
    assert len(problems) == 4


def test_state_problems_finds_a_view_misreporting_tapped_permanents_and_mana(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = Scenario(2)
    (forest,) = scenario.battlefield(PlayerId(0), ["Forest"])
    scenario.tap(forest).mana(PlayerId(1), ManaType.GREEN)
    scenario.at(TurnStep.UPKEEP)
    state = scenario.build()
    assert state_problems(state) == []

    def untapped_and_empty(view: PlayerView) -> PlayerView:
        field = tuple(dataclasses.replace(obj, tapped=False) for obj in view.battlefield)
        players = tuple(dataclasses.replace(p, mana_pool=()) for p in view.players)
        return dataclasses.replace(view, battlefield=field, players=players)

    leaking(monkeypatch, untapped_and_empty)
    problems = state_problems(state)
    assert f"player 0's view misreports whether object {forest} is tapped" in problems
    assert "player 1's view misreports player 1's mana pool" in problems
    assert len(problems) == 4


def test_state_problems_finds_a_view_misreporting_damage(monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = Scenario(2)
    (bears,) = scenario.battlefield(PlayerId(0), ["Grizzly Bears"])
    scenario.damage(bears, 1)
    scenario.at(TurnStep.UPKEEP)
    state = scenario.build()
    assert state_problems(state) == []

    def undamaged(view: PlayerView) -> PlayerView:
        field = tuple(dataclasses.replace(obj, damage=0) for obj in view.battlefield)
        return dataclasses.replace(view, battlefield=field)

    leaking(monkeypatch, undamaged)
    assert state_problems(state) == [
        f"player 0's view misreports the damage on object {bears}",
        f"player 1's view misreports the damage on object {bears}",
    ]
