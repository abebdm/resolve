"""The fuzz command line's defaults, presets and summary (tools/fuzz.py).

The default run plays 40-card decks of basic lands (copied from Scryfall into
``tools/excerpts/basic_lands.json``), so its games play turns: lands are played (305.1) and
tapped for mana (605.3a) until a player draws from an empty library (704.5b) or concedes
(104.3a).
"""

from __future__ import annotations

import copy
import io
import re
from collections import Counter
from collections.abc import Sequence
from contextlib import redirect_stdout
from typing import Any

import pytest

from resolve.decisions.spaces import ActivateAbilityOption, ChooseOne, Pick, PlayLandOption
from resolve.engine.api import submit
from resolve.engine.concede import concede
from resolve.engine.deck import Deck
from resolve.events.base import LogEntry
from resolve.events.game import PlayerLost
from resolve.events.mana import ManaAdded
from resolve.events.permanents import LandPlayed
from resolve.state.config import GameConfig
from resolve.state.ids import PlayerId
from resolve.state.turn import Phase
from tests.engine_support import EndGame, running
from tests.game_fixtures import answer, deck, pass_until, request_of, started_game
from tools import fuzz as fuzz_tool
from tools.fuzz import (
    CONCESSION,
    DECKED,
    DRAW,
    LIFE_TOTAL,
    RULES_GAP,
    FuzzResult,
    GameStats,
    ending,
    fuzz_game,
    summary_lines,
)

# --- ending ---------------------------------------------------------------------------------


def land_only_game(concession_chance: int = 0) -> FuzzResult:
    """Two players with 9 and 10 Forests; without concessions it ends by decking (704.5b)."""
    decks = [deck(forests=9, elves=0), deck(forests=10, elves=0)]
    return fuzz_game(
        GameConfig.standard(),
        decks,
        0,
        check_copies=False,
        probe_invalid=False,
        concession_chance=concession_chance,
    )


def with_last_loss(result: FuzzResult, rules: tuple[str, ...]) -> FuzzResult:
    """``result`` with one more loss logged after the others (for the endings no M1 game has)."""
    state = copy.deepcopy(result.state)
    record = PlayerLost(player=PlayerId(0), rules=rules)
    state.event_log.append(LogEntry(len(state.event_log), record, None))
    return FuzzResult(result.answers, result.rejected, None, state)


def test_a_land_only_game_without_concessions_ends_decked() -> None:
    """With only lands nobody can lose life, so the game ends when a player draws from an empty
    library (704.5b, 121.4)."""
    assert ending(land_only_game()) == DECKED


def test_a_game_won_by_a_concession_ends_by_concession() -> None:
    """Two players, a concession before half the decisions: the first loss is a concession
    (104.3a), and in a two-player game it ends the game (104.2a)."""
    result = land_only_game(concession_chance=2)
    assert ending(result) == CONCESSION


def test_a_game_ending_at_a_rules_gap_ends_at_a_rules_gap() -> None:
    state = running(EndGame(()))
    assert ending(FuzzResult(3, 0, "601.2: casting a spell", state)) == RULES_GAP


def test_a_game_with_no_winner_is_a_draw_however_the_players_lost() -> None:
    """Empty decks: every player draws from an empty library in the first upkeep and all lose
    at once (704.5b), so nobody wins and the game is a draw (104.4a)."""
    decks = [Deck(()), Deck(()), Deck(())]
    result = fuzz_game(GameConfig.standard(), decks, 0)
    losses = [e.record for e in result.state.event_log if isinstance(e.record, PlayerLost)]
    assert [loss.rules[0] for loss in losses] == ["704.5b"] * 3
    assert ending(result) == DRAW


def test_the_last_loss_names_the_ending() -> None:
    """704.5a: a player at 0 or less life loses; any other rule is reported as it is."""
    decked = land_only_game()
    assert ending(with_last_loss(decked, ("704.5a", "704.3"))) == LIFE_TOTAL
    assert ending(with_last_loss(decked, ("704.5c", "704.3"))) == "other (704.5c)"


def test_a_win_without_a_loss_is_reported_as_other() -> None:
    state = running(EndGame((PlayerId(0),)))
    assert ending(FuzzResult(0, 0, None, state)) == "other (no loss)"


def test_a_game_neither_over_nor_at_a_gap_has_no_ending() -> None:
    state = running()
    with pytest.raises(ValueError, match="neither over nor stopped at a gap"):
        ending(FuzzResult(0, 0, None, state))


# --- GameStats and summary_lines -----------------------------------------------------------------


def test_game_stats_count_turns_land_plays_and_mana_abilities() -> None:
    """A scripted game: in turn 1's precombat main phase player 0 plays a Forest (305.1) and
    taps it for mana (605.3a); then player 1 concedes (104.3a) and player 0 wins (104.2a)."""
    state = started_game(2, forests=10, elves=0)
    pass_until(state, lambda s: s.turn is not None and s.turn.phase is Phase.PRECOMBAT_MAIN)

    def choose(kind: type) -> None:
        space = request_of(state).space
        assert isinstance(space, ChooseOne)
        index = next(i for i, option in enumerate(space.options) if isinstance(option, kind))
        submit(state, answer(state, Pick(index)))

    choose(PlayLandOption)
    choose(ActivateAbilityOption)
    concede(state, PlayerId(1))
    stats = GameStats.of(FuzzResult(17, 2, None, state))
    assert stats == GameStats(
        answers=17, rejected=2, turns=1, ending=CONCESSION, lands_played=1, mana_abilities=1
    )


def test_game_stats_of_a_game_that_never_reached_a_turn() -> None:
    state = running(EndGame(()))
    assert GameStats.of(FuzzResult(0, 0, None, state)).turns == 0


def test_the_summary_lines() -> None:
    games = [
        GameStats(answers=10, rejected=1, turns=3, ending=DECKED, lands_played=2, mana_abilities=5),
        GameStats(20, 0, 5, CONCESSION, 3, 4),
        GameStats(31, 2, 7, "other (704.5c)", 0, 0),
    ]
    assert summary_lines(games) == [
        "3 games passed: 61 answers accepted, 3 rejected.",
        "Answers per game: min 10, average 20.3, max 31.",
        "Turns per game: min 3, average 5.0, max 7.",
        "Endings: decked x1, life total x0, concession x1, draw x0, rules gap x0, "
        "other (704.5c) x1.",
        "Played: 5 lands, 9 mana abilities activated.",
    ]


def test_the_summary_of_one_game() -> None:
    games = [GameStats(1, 0, 1, DRAW, 0, 0)]
    assert summary_lines(games)[1:3] == [
        "Answers per game: min 1, average 1.0, max 1.",
        "Turns per game: min 1, average 1.0, max 1.",
    ]


# --- The default run and the presets ---------------------------------------------------------


class Recorder:
    """Stands in for ``fuzz_game``: records each call, then plays it (or returns ``canned``)."""

    def __init__(self, canned: FuzzResult | None = None) -> None:
        self.canned = canned
        self.calls: list[tuple[GameConfig, list[Deck], int, dict[str, Any]]] = []
        self.results: list[FuzzResult] = []

    def __call__(
        self, config: GameConfig, decks: Sequence[Deck], seed: int, **options: Any
    ) -> FuzzResult:
        self.calls.append((config, list(decks), seed, options))
        result = self.canned or fuzz_game(config, decks, seed, **options)
        self.results.append(result)
        return result


def run_main(monkeypatch: pytest.MonkeyPatch, recorder: Recorder, *args: str) -> str:
    monkeypatch.setattr(fuzz_tool, "fuzz_game", recorder)
    output = io.StringIO()
    with redirect_stdout(output):
        status = fuzz_tool.main(list(args))
    assert status == 0, output.getvalue()
    return output.getvalue()


def numbers(pattern: str, text: str) -> tuple[float, ...]:
    found = re.search(pattern, text)
    assert found is not None, f"{pattern!r} not in:\n{text}"
    return tuple(float(group) for group in found.groups())


def test_a_default_run_plays_turns_lands_and_mana_and_reports_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default run, cut to its first four games (standard, 2 to 5 players). Each player has
    40 basic lands, 8 of each; the games reach later turns, players play lands (at most one a
    turn, 305.2) and tap them for mana, and the summary's numbers are those of the games."""
    recorder = Recorder()
    text = run_main(monkeypatch, recorder, "--games", "4")

    assert [len(decks) for _, decks, _, _ in recorder.calls] == [2, 3, 4, 5]
    assert [seed for _, _, seed, _ in recorder.calls] == [0, 1, 2, 3]
    for config, decks, _, options in recorder.calls:
        assert config.commander is None
        assert options == {"concession_chance": 200, "check_every": 10}
        for player_deck in decks:
            names = Counter(card.data.name for card in player_deck.cards)
            assert names == {"Plains": 8, "Island": 8, "Swamp": 8, "Mountain": 8, "Forest": 8}
    assert "Run: quick preset; decks: 8 of each basic land (basic_lands.json); " in text
    assert "concessions: 1 decision in 200; full checks every 10 answers." in text

    # Each game's numbers, counted here from its final state.
    answers: list[int] = []
    turns: list[int] = []
    lands = mana = 0
    endings: Counter[str] = Counter()
    for result in recorder.results:
        state = result.state
        assert result.gap is None and state.result is not None and state.turn is not None
        answers.append(result.answers)
        turns.append(state.turn.number)
        records = [entry.record for entry in state.event_log]
        played = sum(1 for record in records if isinstance(record, LandPlayed))
        assert 0 < played <= state.turn.number  # 305.2: one land per turn
        lands += played
        mana += sum(1 for record in records if isinstance(record, ManaAdded))
        last_loss = [record for record in records if isinstance(record, PlayerLost)][-1]
        endings[{"704.5b": "decked", "104.3a": "concession"}[last_loss.rules[0]]] += 1
    assert max(turns) >= 10, "some game reaches a later turn"
    assert mana > 0

    total = sum(answers)
    assert numbers(r"4 games passed: (\d+) answers accepted, (\d+) rejected\.", text) == (total, 0)
    assert numbers(r"Answers per game: min (\d+), average ([\d.]+), max (\d+)\.", text) == (
        min(answers),
        round(total / 4, 1),
        max(answers),
    )
    assert numbers(r"Turns per game: min (\d+), average ([\d.]+), max (\d+)\.", text) == (
        min(turns),
        round(sum(turns) / 4, 1),
        max(turns),
    )
    assert numbers(
        r"Endings: decked x(\d+), life total x(\d+), concession x(\d+), draw x(\d+), "
        r"rules gap x(\d+)\.",
        text,
    ) == (endings["decked"], 0, endings["concession"], 0, 0)
    assert numbers(r"Played: (\d+) lands, (\d+) mana abilities activated\.", text) == (lands, mana)
    assert "Formats: standard x4" in text


def canned_result() -> FuzzResult:
    """A finished game, returned by a stubbed ``fuzz_game`` so preset tests don't play."""
    return fuzz_game(GameConfig.standard(), [Deck(()), Deck(())], 0)


def test_the_default_run_is_quick() -> None:
    """Ten games: one of each player count (2 to 6) in each format."""
    assert fuzz_tool.Preset(games=10, concessions=200, check_every=10) == fuzz_tool.QUICK


def test_the_default_run_cycles_every_player_count_in_both_formats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = Recorder(canned_result())
    text = run_main(monkeypatch, recorder)
    shapes = [(len(decks), config.commander is not None) for config, decks, _, _ in recorder.calls]
    assert shapes == [(n, False) for n in range(2, 7)] + [(n, True) for n in range(2, 7)]
    assert "Run: quick preset;" in text


def test_thorough_runs_more_games_with_rarer_concessions_and_every_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = Recorder(canned_result())
    text = run_main(monkeypatch, recorder, "--thorough")
    thorough = fuzz_tool.THOROUGH
    assert len(recorder.calls) == thorough.games
    assert thorough.games >= 10 * fuzz_tool.QUICK.games
    assert thorough.concessions > fuzz_tool.QUICK.concessions
    assert thorough.check_every == 1
    for _, _, _, options in recorder.calls:
        assert options == {"concession_chance": thorough.concessions, "check_every": 1}
    assert (
        f"Run: thorough preset; decks: 8 of each basic land (basic_lands.json); concessions: "
        f"1 decision in {thorough.concessions}; full checks every answer." in text
    )
    assert f"{thorough.games} games passed" in text


def test_explicit_options_override_the_preset(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder(canned_result())
    run_main(
        monkeypatch, recorder, "--thorough", "--games", "3", "--check-every", "5",
        "--concessions", "0",
    )  # fmt: skip
    assert len(recorder.calls) == 3
    assert {str(options) for _, _, _, options in recorder.calls} == {
        str({"concession_chance": 0, "check_every": 5})
    }


def test_the_reproduce_command_of_a_failure_is_printed(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing(config: GameConfig, decks: Sequence[Deck], seed: int, **options: Any) -> Any:
        raise fuzz_tool.FuzzFailure(f"game seed {seed}: broken")

    monkeypatch.setattr(fuzz_tool, "fuzz_game", failing)
    output = io.StringIO()
    with redirect_stdout(output):
        status = fuzz_tool.main(["--seed", "7"])
    assert status == 1
    assert output.getvalue() == "FAILED: game seed 7: broken\n"
