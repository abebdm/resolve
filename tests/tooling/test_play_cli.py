"""Tests for tools/play_cli.py."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from tests import scryfall_fixtures as fx
from tools.play_cli import EXIT_CANT_START, EXIT_GAP, EXIT_OVER, EXIT_QUIT, main


def run_cli(args: list[str], typed: str = "") -> tuple[int, str]:
    output = io.StringIO()
    status = main(args, input=io.StringIO(typed), output=output)
    return status, output.getvalue()


def test_a_game_of_random_agents_runs_to_the_turn_structure_gap() -> None:
    """Until the turn structure exists (M1.2), every game stops after the mulligans, at 103.8."""
    status, text = run_cli(["--players", "3", "--random", "0", "1", "2", "--seed", "4"])
    assert status == EXIT_GAP
    assert "No --deck given: every player gets an empty deck." in text
    assert "Stopped: the engine doesn't implement 103.8: taking turns" in text
    assert "MulliganDeclared" in text


def test_a_human_answers_after_a_rejected_answer() -> None:
    """Without --random every seat is human; a rejected answer is asked again (design.md §6)."""
    status, text = run_cli(["--commander"], "7\n0\n0\n0\n")  # then both players keep
    assert status == EXIT_GAP
    assert "life 40" in text
    assert "The engine rejected that answer: option index must be in 0..1" in text
    assert "0: keep" in text and "1: mulligan" in text
    assert "Stopped: the engine doesn't implement 103.8" in text


def test_hot_seat_prompts_show_the_deciding_players_view_and_no_final_view() -> None:
    """design.md §9: each human sees only their own view, so with several humans at one terminal
    the game ends without printing anyone's hand. Seed 1 of a 2-player game asks player 1 who
    starts; player 1 picks player 0, then both keep (103.5)."""
    status, text = run_cli(["--seed", "1"], "0\n0\n0\n")
    assert status == EXIT_GAP
    assert text.count("=== Player 1's view ===") == 2  # 103.1, then its mulligan decision
    assert text.count("=== Player 0's view ===") == 1  # its mulligan decision
    assert text.index("=== Player 1's view ===") < text.index("Player 1: Choose which player")
    last_view = max(text.rindex("=== Player 1's view ==="), text.rindex("=== Player 0's view ==="))
    assert last_view < text.rindex("Player 1: Keep this hand"), "no view after the last answer"


def test_a_single_human_sees_the_final_view() -> None:
    status, text = run_cli(["--players", "3", "--random", "1", "2", "--seed", "2"], "0\n0\n0\n")
    assert status == EXIT_GAP
    final = text.split("Stopped:")[0]
    assert final.rstrip().endswith(")") and "=== Player 0's view ===" in final
    assert "=== Player 1's view ===" not in text and "=== Player 2's view ===" not in text


def test_the_largest_agent_seed_is_accepted() -> None:
    """Seat i plays with seed agent_seed + i, which must stay below 2**64."""
    status, _ = run_cli(["--random", "0", "1", "--agent-seed", str(2**64 - 2)])
    assert status == EXIT_GAP
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
    fx.write_snapshot(data, cards=[fx.FOREST])
    deck = tmp_path / "deck.txt"
    deck.write_text("Mainboard\n10 Forest\n", encoding="utf-8")
    status, text = run_cli(["--deck", str(deck), "--deck", str(deck), "--data-dir", str(data)])
    assert status == EXIT_CANT_START
    assert "'Forest' is not implemented" in text


def test_missing_card_data_is_reported(tmp_path: Path) -> None:
    deck = tmp_path / "deck.txt"
    deck.write_text("Mainboard\n1 Forest\n", encoding="utf-8")
    status, text = run_cli(["--deck", str(deck)] * 2 + ["--data-dir", str(tmp_path / "none")])
    assert status == EXIT_CANT_START
    assert text.startswith("error: ")


def test_exit_statuses_are_distinct() -> None:
    assert len({EXIT_OVER, EXIT_CANT_START, 2, EXIT_GAP, EXIT_QUIT}) == 5
