"""Tests for tools/play_cli.py."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from resolve.agents.autopay import AutoPayAgent
from resolve.agents.random_agent import RandomAgent
from resolve.agents.scripted import ScriptedAgent, choose
from resolve.agents.text import TextAgent
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import CastSpellOption
from resolve.engine.api import pending_decision, submit, view_for
from resolve.events.spells import SpellCast
from resolve.state.config import GameConfig
from resolve.state.ids import PlayerId
from resolve.state.spell import COMMANDER, NORMAL
from resolve.state.turn import Phase
from tests import scryfall_fixtures as fx
from tests.casting_support import cast, records
from tests.scenario import Scenario, run_script
from tools.play_cli import (
    EXIT_CANT_START,
    EXIT_GAP,
    EXIT_OVER,
    EXIT_QUIT,
    main,
    play_game,
    seat_agents,
)


def run_cli(args: list[str], typed: str = "") -> tuple[int, str]:
    output = io.StringIO()
    status = main(args, input=io.StringIO(typed), output=output)
    return status, output.getvalue()


def test_a_game_of_random_agents_with_empty_decks_ends_in_a_draw() -> None:
    """Every opening draw from an empty deck fails (121.4), so every player loses when
    state-based actions are first checked, in the first upkeep (704.5b): a draw (104.4a)."""
    status, text = run_cli(["--players", "3", "--random", "0", "1", "2", "--seed", "4"])
    assert status == EXIT_OVER
    assert "No --deck given: every player gets an empty deck." in text
    # The draws from empty libraries have scrolled out of the recent log; the losses cite them.
    assert "PlayerLost(player=2)  (704.5b, 121.4, 704.3)" in text
    assert "PlayerLeftGame(player=2, removed=(), library_size=0)  (800.4a, 104.5)" in text
    assert "Game over: a draw." in text
    assert "Turn 1, player " in text and "upkeep step; nobody has priority." in text


def test_a_game_that_reaches_a_gap_exits_with_3() -> None:
    """Choosing an action the engine can't take yet stops the game (903.8: casting a commander
    from the command zone, until M7)."""
    scenario = Scenario(2, config=GameConfig.commander_game())
    commander = scenario.commander(PlayerId(0), "Grizzly Bears")
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    output = io.StringIO()
    agent = ScriptedAgent([choose(CastSpellOption(commander, NORMAL, COMMANDER))])
    status = play_game(state, [agent, agent], output, viewer=PlayerId(0))
    assert status == EXIT_GAP
    assert "Stopped: the engine doesn't implement 903.8: casting a commander" in output.getvalue()
    # Nobody holds priority while a spell is being cast (117.3c).
    assert "Turn 1, player 0's turn: precombat main phase; nobody has priority." in (
        output.getvalue()
    )


def test_a_human_answers_after_a_rejected_answer() -> None:
    """Without --random every seat is human; a rejected answer is asked again (design.md §6)."""
    status, text = run_cli(["--commander"], "7\n0\n")
    assert status == EXIT_OVER
    assert "life 40" in text
    assert "The engine rejected that answer: option index must be in 0..1" in text
    assert "Game over: a draw." in text


def test_hot_seat_prompts_show_the_deciding_players_view_and_no_final_view() -> None:
    """design.md §9: each human sees only their own view, so with several humans at one terminal
    the game ends without printing anyone's hand. Seed 1 of a 2-player game asks player 1. The
    decks are empty, so nobody is asked about a mulligan (103.5)."""
    status, text = run_cli(["--seed", "1"], "0\n")
    assert status == EXIT_OVER
    assert text.rstrip().endswith("Game over: a draw.")
    assert text.count("=== Player 1's view ===") == 1
    assert "=== Player 0's view ===" not in text
    assert text.index("=== Player 1's view ===") < text.index("Player 1: Choose which player")


def test_a_single_human_sees_the_final_view() -> None:
    status, text = run_cli(["--players", "3", "--random", "1", "2", "--seed", "2"], "0\n0\n0\n")
    assert status == EXIT_OVER
    final = text[text.rindex("=== Player 0's view ===") :]
    assert "Game over: a draw." in final
    assert "=== Player 1's view ===" not in text and "=== Player 2's view ===" not in text


def test_the_largest_agent_seed_is_accepted() -> None:
    """Seat i plays with seed agent_seed + i, which must stay below 2**64."""
    status, _ = run_cli(["--random", "0", "1", "--agent-seed", str(2**64 - 2)])
    assert status == EXIT_OVER
    with pytest.raises(SystemExit):
        run_cli(["--random", "0", "1", "--agent-seed", str(2**64 - 1)])


def test_quitting_at_the_prompt() -> None:
    assert run_cli([], "quit\n")[0] == EXIT_QUIT
    status, text = run_cli([], "")
    assert status == EXIT_QUIT and "Game abandoned." in text


def test_the_same_seed_plays_the_same_game() -> None:
    args = ["--players", "4", "--random", "0", "1", "2", "3", "--seed", "11"]
    assert run_cli(args) == run_cli(args)


@pytest.mark.parametrize(
    "args",
    [
        ["--players", "1"],
        ["--random", "2"],
        ["--players", "3", "--deck", "a.txt", "--deck", "b.txt"],
        ["--seed", "-1"],
        ["--agent-seed", "-1"],
    ],
)
def test_bad_arguments_exit_with_2(args: list[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        run_cli(args)
    assert exit_info.value.code == 2


def test_decks_with_unimplemented_cards_are_refused(tmp_path: Path) -> None:
    """Decks with unimplemented cards are refused, never approximated (design.md §11)."""
    data = tmp_path / "data"
    fx.write_snapshot(data, cards=[fx.FOREST, fx.TEST_RAPTOR])
    deck = tmp_path / "deck.txt"
    deck.write_text("Mainboard\n10 Forest\n1 Test Raptor\n", encoding="utf-8")
    status, text = run_cli(["--deck", str(deck), "--deck", str(deck), "--data-dir", str(data)])
    assert status == EXIT_CANT_START
    assert "'Test Raptor' is not implemented" in text


def test_random_agents_play_a_basic_land_game_to_its_end(tmp_path: Path) -> None:
    """Forest decks from the snapshot: random agents play lands and tap them (305, 605) until
    a player draws from an empty library and loses (704.5b)."""
    data = tmp_path / "data"
    fx.write_snapshot(data, cards=[fx.FOREST])
    deck = tmp_path / "deck.txt"
    deck.write_text("Mainboard\n10 Forest\n", encoding="utf-8")
    args = ["--deck", str(deck), "--deck", str(deck), "--data-dir", str(data)]
    status, text = run_cli([*args, "--random", "0", "1", "--seed", "3"])
    assert status == EXIT_OVER
    assert "Game over: won by player" in text
    battlefield = text[text.rindex("Battlefield:") :].splitlines()[0]
    assert "Forest #" in battlefield, "lands were played"


def test_missing_card_data_is_reported(tmp_path: Path) -> None:
    deck = tmp_path / "deck.txt"
    deck.write_text("Mainboard\n1 Forest\n", encoding="utf-8")
    status, text = run_cli(["--deck", str(deck)] * 2 + ["--data-dir", str(tmp_path / "none")])
    assert status == EXIT_CANT_START
    assert text.startswith("error: ")


def test_exit_statuses_are_distinct() -> None:
    assert len({EXIT_OVER, EXIT_CANT_START, 2, EXIT_GAP, EXIT_QUIT}) == 5


def test_autopay_wraps_every_seat_in_the_auto_payer() -> None:
    """``--autopay``: the auto-payer answers every seat's payment decisions (601.2g-h), human or
    random; without it the seats are the plain agents."""
    human = TextAgent(io.StringIO(""), io.StringIO())
    plain = seat_agents(3, random_seats=[1], agent_seed=5, human=human, autopay=False)
    assert plain[0] is human and plain[2] is human and isinstance(plain[1], RandomAgent)
    wrapped = seat_agents(3, random_seats=[1], agent_seed=5, human=human, autopay=True)
    assert all(isinstance(agent, AutoPayAgent) for agent in wrapped)
    inner = [agent.inner for agent in wrapped if isinstance(agent, AutoPayAgent)]
    assert inner[0] is human and inner[2] is human and isinstance(inner[1], RandomAgent)


def test_with_autopay_a_human_isnt_asked_to_pay() -> None:
    """A human casting Grizzly Bears ({1}{G}) with two Forests: the auto-payer taps them, so the
    terminal reads nothing (an empty input would quit the game)."""
    scenario = Scenario(2)
    scenario.battlefield(PlayerId(0), ["Forest", "Forest"])
    (bears,) = scenario.hand(PlayerId(0), ["Grizzly Bears"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(bears, PlayerId(0)))
    output = io.StringIO()
    (agent,) = seat_agents(
        1, random_seats=[], agent_seed=0, human=TextAgent(io.StringIO(""), output), autopay=True
    )
    while (request := pending_decision(state)) is not None and request.kind is not (
        DecisionKind.PRIORITY_ACTION
    ):
        submit(state, agent.decide(view_for(state, request.player), request))
    assert len(records(state, SpellCast)) == 1
    assert output.getvalue() == ""
