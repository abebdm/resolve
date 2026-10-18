"""Tests for tools/play_cli.py."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from resolve.agents.scripted import ScriptedAgent, choose
from resolve.decisions.spaces import CastSpellOption
from resolve.state.ids import PlayerId
from resolve.state.turn import Phase
from tests import scryfall_fixtures as fx
from tests.scenario import Scenario
from tools.play_cli import EXIT_CANT_START, EXIT_GAP, EXIT_OVER, EXIT_QUIT, main, play_game


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
    assert "empty_library=True" in text
    assert "PlayerLost(player=2)  (704.5b, 121.4, 704.3)" in text
    assert "Game over: a draw." in text
    assert "Turn 1, player " in text and "upkeep step; nobody has priority." in text


def test_a_game_that_reaches_a_gap_exits_with_3() -> None:
    """Choosing an action the engine can't take yet stops the game (601.2 until M2)."""
    scenario = Scenario(2)
    (elves,) = scenario.hand(PlayerId(0), ["Llanowar Elves"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    output = io.StringIO()
    agent = ScriptedAgent([choose(CastSpellOption(elves))])
    status = play_game(state, [agent, agent], output, viewer=PlayerId(0))
    assert status == EXIT_GAP
    assert "Stopped: the engine doesn't implement 601.2: casting a spell" in output.getvalue()
    assert "Turn 1, player 0's turn: precombat main phase; player 0 has priority." in (
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
    fx.write_snapshot(data, cards=[fx.FOREST, fx.LLANOWAR_ELVES])
    deck = tmp_path / "deck.txt"
    deck.write_text("Mainboard\n10 Forest\n1 Llanowar Elves\n", encoding="utf-8")
    status, text = run_cli(["--deck", str(deck), "--deck", str(deck), "--data-dir", str(data)])
    assert status == EXIT_CANT_START
    assert "'Llanowar Elves' is not implemented" in text


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
    assert "LandPlayed(" in text or "Forest #" in text


def test_missing_card_data_is_reported(tmp_path: Path) -> None:
    deck = tmp_path / "deck.txt"
    deck.write_text("Mainboard\n1 Forest\n", encoding="utf-8")
    status, text = run_cli(["--deck", str(deck)] * 2 + ["--data-dir", str(tmp_path / "none")])
    assert status == EXIT_CANT_START
    assert text.startswith("error: ")


def test_exit_statuses_are_distinct() -> None:
    assert len({EXIT_OVER, EXIT_CANT_START, 2, EXIT_GAP, EXIT_QUIT}) == 5
