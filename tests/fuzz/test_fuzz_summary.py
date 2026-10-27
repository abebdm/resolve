"""The fuzz command line's defaults, presets and summary (tools/fuzz.py).

The default run plays decks from two recipes: basic lands (8 or 2 of each, copied from Scryfall
into ``tools/excerpts/basic_lands.json``) plus the cards of ``tools/excerpts/cards.json``: its
noncreature cards (``spells``) or all of them (``creatures``). Its games play turns: lands are
played (305.1) and tapped for mana (605.3a), spells are cast (601.2), resolve (608) or are
reversed (733.1), until a player draws from an empty library (704.5b), concedes (104.3a), or the
game reaches an allowed gap (508.1, 903.8).
"""

from __future__ import annotations

import copy
import io
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Sequence
from contextlib import redirect_stdout
from dataclasses import replace
from typing import Any

import pytest

from resolve.agents.scripted import Choose, ScriptedAgent, Step
from resolve.decisions.spaces import ActivateAbilityOption, ChooseOne, Pick, PlayLandOption
from resolve.engine.api import submit, view_for
from resolve.engine.concede import concede
from resolve.engine.deck import Deck
from resolve.events.base import LogEntry
from resolve.events.damage import DamageDealt
from resolve.events.game import PlayerLost
from resolve.events.mana import ManaAdded
from resolve.events.permanents import LandPlayed
from resolve.events.spells import (
    ActionReversed,
    PermanentSpellResolved,
    SpellCast,
    SpellCountered,
    SpellDidNotResolve,
    SpellResolved,
)
from resolve.state.config import GameConfig
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import ManaType
from resolve.state.turn import Phase
from tests.casting_support import (
    activate,
    activate_with_priority,
    cast,
    counts,
    pass_,
    pay,
    records,
    reverse,
)
from tests.engine_support import EndGame, running
from tests.game_fixtures import answer, deck, pass_until, request_of, started_game
from tests.scenario import Scenario, run_script
from tools import fuzz as fuzz_tool
from tools.fuzz import (
    CONCESSION,
    DECKED,
    DRAW,
    LIFE_TOTAL,
    RULES_GAP,
    FuzzResult,
    GameStats,
    PayableCasts,
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
        "Played: 5 lands, 9 mana abilities activated, 0 reversed.",
        "Spells: 0 cast, 0 resolved, 0 didn't resolve, 0 countered, 0 reversed.",
        "Damage: 0 dealt.",
        "Reversed casts: auto-pay seats 0 of 0 attempts, 0 of 0 payable; random seats 0 of 0, "
        "0 of 0 payable.",
        "Casts per card: none.",
        "Gaps: none.",
    ]


def test_the_summary_counts_spells_casts_per_card_and_gaps() -> None:
    games = [
        GameStats(10, 0, 3, RULES_GAP, 2, 5, (("Sol Ring", 2),), 2, 4, "508.1"),
        GameStats(
            20, 0, 5, RULES_GAP, 3, 4, (("Grizzly Bears", 1), ("Sol Ring", 1)), 1, 0, "903.8"
        ),
        GameStats(5, 0, 1, RULES_GAP, 0, 0, (), 0, 1, "508.1"),
    ]
    games[1] = replace(games[1], did_not_resolve=2, damage=7, countered=1)
    assert summary_lines(games)[5:] == [
        "Spells: 4 cast, 3 resolved, 2 didn't resolve, 1 countered, 5 reversed.",
        "Damage: 7 dealt.",
        "Reversed casts: auto-pay seats 0 of 0 attempts, 0 of 0 payable; random seats 5 of 9, "
        "0 of 4 payable.",
        "Casts per card: Grizzly Bears x1, Sol Ring x3.",
        "Gaps: 508.1 x2, 903.8 x1.",
    ]


def test_game_stats_count_casts_resolutions_reversals_and_the_gap() -> None:
    """A scripted game: P0 casts Sol Ring with a Forest (it resolves), then tries Grizzly Bears
    with only Sol Ring's {C}{C}, which is reversed (107.4a, 733.1)."""
    scenario = Scenario(2)
    ring, bears = scenario.hand(PlayerId(0), ["Sol Ring", "Grizzly Bears"])
    (forest,) = scenario.battlefield(PlayerId(0), ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(ring), activate(forest), pass_(), pass_())
    (permanent,) = [o for o in state.battlefield if o != forest]
    run_script(state, cast(bears), activate(permanent), reverse())
    stats = GameStats.of(FuzzResult(9, 0, "508.1: declaring attackers", state))
    assert stats.casts == (("Sol Ring", 1),)
    assert (stats.resolved, stats.reversed, stats.gap) == (1, 1, "508.1")
    assert stats.abilities_reversed == 0


def test_game_stats_count_reversed_mana_abilities_apart_from_reversed_casts() -> None:
    """Selesnya Signet activated with no mana for its {1}: its activation is reversed (733.1),
    which is no reversed cast."""
    scenario = Scenario(2)
    (signet,) = scenario.battlefield(PlayerId(0), ["Selesnya Signet"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, activate_with_priority(signet), activate_with_priority(signet))
    stats = GameStats.of(FuzzResult(2, 0, "508.1: declaring attackers", state))
    assert (stats.reversed, stats.abilities_reversed) == (0, 2)
    games = [stats, GameStats(1, 0, 1, DRAW, 0, 0, abilities_reversed=1)]
    assert summary_lines(games)[4] == "Played: 0 lands, 0 mana abilities activated, 3 reversed."


def test_game_stats_count_casts_and_reversals_of_the_auto_paying_seats() -> None:
    """The odd seats are the auto-payers (``fuzz_game``): P1 casts Sol Ring with a Forest, then
    tries Grizzly Bears with nothing to pay for it (reversed, 733.1); P0's casts don't count."""
    scenario = Scenario(2)
    ring, bears = scenario.hand(PlayerId(1), ["Sol Ring", "Grizzly Bears"])
    (forest,) = scenario.battlefield(PlayerId(1), ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN, active=PlayerId(1))
    state = scenario.build()
    run_script(state, cast(ring), activate(forest), pass_(), pass_())
    run_script(state, cast(bears), pay())
    stats = GameStats.of(FuzzResult(9, 0, "508.1: declaring attackers", state))
    assert (stats.reversed, stats.autopay_casts, stats.autopay_reversed) == (1, 1, 1)


def payable_after(state: GameState, *steps: Step | Choose) -> list[PlayerId]:
    """Run ``steps`` as ``fuzz_run`` does, judging the casts with ``PayableCasts``; returns the
    players whose payable casts were reversed."""
    tracker = PayableCasts(seen=len(state.event_log))
    agent = ScriptedAgent(steps)
    for _ in steps:
        request = request_of(state)
        view = view_for(state, request.player)
        tracker.before(view, request)
        submit(state, agent.decide(view, request))
        tracker.after(state)
    return tracker.reversed


def bears_with(lands: list[str], mana: tuple[ManaType, ...] = ()) -> tuple[GameState, ObjectId]:
    scenario = Scenario(2)
    scenario.battlefield(PlayerId(0), lands)
    (bears,) = scenario.hand(PlayerId(0), ["Grizzly Bears"])
    scenario.mana(PlayerId(0), *mana)
    scenario.at(Phase.PRECOMBAT_MAIN)
    return scenario.build(), bears


def test_a_payable_cast_paid_too_early_counts_as_a_payable_reversal() -> None:
    """Grizzly Bears ({1}{G}) with two Forests: payable (601.2g: the planner finds the Forests);
    answering "pay" at once leaves it unpaid (118.3), so it is reversed (733.1)."""
    state, bears = bears_with(["Forest", "Forest"])
    assert payable_after(state, cast(bears), pay()) == [PlayerId(0)]


def test_an_unpayable_reversed_cast_isnt_a_payable_reversal() -> None:
    """One Forest can't pay {1}{G} (107.4b): reversing it was inevitable."""
    state, bears = bears_with(["Forest"])
    assert payable_after(state, cast(bears), pay()) == []


def test_a_cast_whose_first_question_is_the_payment_is_payable() -> None:
    """Pool {G}{G}{W} and no mana ability: 601.2h asks only because the pool pays in two ways
    (GG, GW). The cast completes: no payable reversal."""
    state, bears = bears_with([], (ManaType.GREEN, ManaType.GREEN, ManaType.WHITE))
    assert payable_after(state, cast(bears), counts(2, 0)) == []
    assert len(records(state, SpellCast)) == 1


def test_game_stats_count_payable_reversals_by_seat() -> None:
    state, _ = bears_with([])
    result = FuzzResult(1, 0, "508.1: declaring attackers", state, (PlayerId(1), PlayerId(0)))
    stats = GameStats.of(result)
    assert (stats.payable_reversed, stats.autopay_payable_reversed) == (2, 1)


def test_the_summary_compares_the_auto_paying_seats_with_the_random_ones() -> None:
    """Of the attempts (casts and reversed casts) of each kind of seat, how many were reversed;
    and of the payable ones (casts, and casts reversed although payable), how many."""
    games = [
        GameStats(10, 0, 3, RULES_GAP, 2, 5, (("Sol Ring", 3),), 2, 4, "508.1", 0, 2, 1, 3, 0),
        GameStats(5, 0, 1, DRAW, 0, 0, (("Sol Ring", 1),), 0, 2, None, 0, 0, 0, 1, 0),
    ]
    assert summary_lines(games)[7] == (
        "Reversed casts: auto-pay seats 1 of 3 attempts, 0 of 2 payable; random seats 5 of 7, "
        "4 of 6 payable."
    )


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


# The excerpt's cards, by hand: the noncreature ones, and the creatures.
NONCREATURES = [
    "Arcane Signet", "Cancel", "Chandra's Ignition", "Command Tower", "Cryptic Command",
    "Darksteel Relic", "Decimate", "Fiery Confluence", "Selesnya Signet", "Sol Ring",
    "Swords to Plowshares", "Temple of the False God",
]  # fmt: skip
# Repentant Blacksmith is left out (``FUZZ_EXCLUSIONS``: 702.16e until M6).
CREATURES = [
    "Ashcoat Bear", "Avacyn's Pilgrim", "Darksteel Myr", "Gladecover Scout", "Grizzly Bears",
    "Hill Giant", "Humble Budoka", "Ixalli's Lorekeeper", "Llanowar Elves", "Nacatl Savage",
    "Savannah Lions",
]  # fmt: skip


def expected_deck(recipe: str, copies: int) -> Counter[str]:
    """A recipe's deck, worked out by hand: ``copies`` of each basic land and ``copies // 2``
    (at least one) of each recipe card: the noncreature cards for ``spells``, every excerpt card
    for ``creatures``."""
    cards = NONCREATURES if recipe == "spells" else NONCREATURES + CREATURES
    deck: Counter[str] = Counter({name: copies for name in fuzz_tool.BASIC_LAND_NAMES})
    deck.update({name: max(1, copies // 2) for name in cards})
    return deck


def test_the_recipes_hold_the_excerpt_minus_the_exclusions() -> None:
    assert fuzz_tool.recipe_cards("spells") == (
        "Arcane Signet", "Cancel", "Chandra's Ignition", "Command Tower", "Cryptic Command",
        "Darksteel Relic", "Decimate", "Fiery Confluence", "Selesnya Signet", "Sol Ring",
        "Swords to Plowshares", "Temple of the False God",
    )  # fmt: skip
    assert fuzz_tool.recipe_cards("creatures") == (
        "Arcane Signet", "Ashcoat Bear", "Avacyn's Pilgrim", "Cancel", "Chandra's Ignition",
        "Command Tower", "Cryptic Command", "Darksteel Myr", "Darksteel Relic", "Decimate",
        "Fiery Confluence", "Gladecover Scout", "Grizzly Bears", "Hill Giant", "Humble Budoka",
        "Ixalli's Lorekeeper", "Llanowar Elves", "Nacatl Savage", "Savannah Lions",
        "Selesnya Signet", "Sol Ring", "Swords to Plowshares", "Temple of the False God",
    )  # fmt: skip
    assert list(fuzz_tool.FUZZ_EXCLUSIONS) == ["Repentant Blacksmith"]
    for recipe in fuzz_tool.RECIPES:
        for copies in (8, 2):
            deck = fuzz_tool.recipe_deck(recipe, copies)
            assert Counter(card.data.name for card in deck.cards) == expected_deck(recipe, copies)


def test_a_default_run_plays_turns_lands_and_spells_and_reports_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default run, cut to its first five games (standard, 2 to 6 players). The
    seats get the spells and creatures recipes with 8 and then 2 of each basic land, in turn. The
    games reach later turns; players play lands (at most one a turn, 305.2), tap them for mana,
    cast spells, which resolve or are reversed; and the summary's numbers are those of the
    games. (Five games since M2.7: with Fiery Confluence in the decks, the first four no longer
    include a payable cast that a random seat reversed.)"""
    recorder = Recorder()
    text = run_main(monkeypatch, recorder, "--games", "5", "--jobs", "1")

    pool = [("spells", 8), ("creatures", 8), ("spells", 2), ("creatures", 2)]
    assert [len(decks) for _, decks, _, _ in recorder.calls] == [2, 3, 4, 5, 6]
    assert [seed for _, _, seed, _ in recorder.calls] == [0, 1, 2, 3, 4]
    for config, decks, seed, options in recorder.calls:
        assert config.commander is None
        assert options == {"concession_chance": 200, "check_every": 10}
        for seat, player_deck in enumerate(decks):
            names = Counter(card.data.name for card in player_deck.cards)
            assert names == expected_deck(*pool[(seed + seat) % len(pool)])
            assert player_deck.commanders == ()
    assert (
        "Run: quick preset; decks: the spells and creatures recipes with 8 and 2 of each basic "
        "land (basic_lands.json, cards.json), cycled among the seats; concessions: 1 decision "
        "in 200; full checks every 10 answers." in text
    )

    # Each game's numbers, counted here from its final state.
    answers: list[int] = []
    turns: list[int] = []
    lands = mana = cast = resolved = reversed_ = abilities_reversed = 0
    did_not_resolve = damage = countered = 0
    casts: Counter[str] = Counter()
    gaps: Counter[str] = Counter()
    endings: Counter[str] = Counter()
    attempts: Counter[str] = Counter()
    reversed_by: Counter[str] = Counter()
    for result in recorder.results:
        state = result.state
        assert state.turn is not None
        answers.append(result.answers)
        turns.append(state.turn.number)
        records = [entry.record for entry in state.event_log]
        played = sum(1 for record in records if isinstance(record, LandPlayed))
        assert played <= state.turn.number  # 305.2: one land per turn
        lands += played
        mana += sum(1 for record in records if isinstance(record, ManaAdded))
        for record in records:
            if isinstance(record, SpellCast):
                cast += 1
                casts[record.name or "?"] += 1
        for record in records:
            if isinstance(record, SpellCast | ActionReversed) and (
                not isinstance(record, ActionReversed) or record.card is not None
            ):
                seat = "auto-pay" if record.player % 2 else "random"
                attempts[seat] += 1
                if isinstance(record, ActionReversed):
                    reversed_by[seat] += 1
        resolved += sum(
            1 for record in records if isinstance(record, PermanentSpellResolved | SpellResolved)
        )
        did_not_resolve += sum(1 for record in records if isinstance(record, SpellDidNotResolve))
        countered += sum(1 for record in records if isinstance(record, SpellCountered))
        damage += sum(record.total for record in records if isinstance(record, DamageDealt))
        reversed_ += sum(
            1
            for record in records
            if isinstance(record, ActionReversed) and record.card is not None
        )
        abilities_reversed += sum(
            1
            for record in records
            if isinstance(record, ActionReversed) and record.source is not None
        )
        if result.gap is not None:
            endings["rules gap"] += 1
            gaps[result.gap.split(": ")[0]] += 1
            continue
        assert state.result is not None
        last_loss = [record for record in records if isinstance(record, PlayerLost)][-1]
        endings[
            {"704.5b": "decked", "704.5a": "life total", "104.3a": "concession"}[last_loss.rules[0]]
        ] += 1
    assert max(turns) >= 10, "some game reaches a later turn"
    assert lands > 0 and mana > 0
    assert cast > 0 and resolved > 0 and reversed_ > 0, "spells are cast, resolve and are reversed"
    assert set(gaps) <= set(fuzz_tool.ALLOWED_GAPS)

    total = sum(answers)
    assert numbers(r"5 games passed: (\d+) answers accepted, (\d+) rejected\.", text) == (total, 0)
    assert numbers(r"Answers per game: min (\d+), average ([\d.]+), max (\d+)\.", text) == (
        min(answers),
        round(total / len(answers), 1),
        max(answers),
    )
    assert numbers(r"Turns per game: min (\d+), average ([\d.]+), max (\d+)\.", text) == (
        min(turns),
        round(sum(turns) / len(turns), 1),
        max(turns),
    )
    assert numbers(
        r"Endings: decked x(\d+), life total x(\d+), concession x(\d+), draw x(\d+), "
        r"rules gap x(\d+)\.",
        text,
    ) == (
        endings["decked"],
        endings["life total"],
        endings["concession"],
        0,
        endings["rules gap"],
    )
    assert numbers(
        r"Played: (\d+) lands, (\d+) mana abilities activated, (\d+) reversed\.", text
    ) == (lands, mana, abilities_reversed)
    assert numbers(
        r"Spells: (\d+) cast, (\d+) resolved, (\d+) didn't resolve, (\d+) countered, "
        r"(\d+) reversed\.",
        text,
    ) == (cast, resolved, did_not_resolve, countered, reversed_)
    assert numbers(r"Damage: (\d+) dealt\.", text) == (damage,)
    payable_reversed = Counter(
        "auto-pay" if player % 2 else "random"
        for result in recorder.results
        for player in result.payable_reversed
    )
    payable = {
        seat: payable_reversed[seat] + attempts[seat] - reversed_by[seat] for seat in attempts
    }
    assert numbers(
        r"Reversed casts: auto-pay seats (\d+) of (\d+) attempts, (\d+) of (\d+) payable; random "
        r"seats (\d+) of (\d+), (\d+) of (\d+) payable\.",
        text,
    ) == (
        reversed_by["auto-pay"],
        attempts["auto-pay"],
        payable_reversed["auto-pay"],
        payable["auto-pay"],
        reversed_by["random"],
        attempts["random"],
        payable_reversed["random"],
        payable["random"],
    )
    # M2.5's "done when" (docs/decisions.md): of the casts that could be paid when their payment
    # began, the auto-paying seats reverse none, while the random seats reverse some.
    assert payable["auto-pay"] > 0 and payable["random"] > 0
    assert payable_reversed["auto-pay"] == 0
    assert payable_reversed["random"] > 0
    per_card = ", ".join(f"{name} x{casts[name]}" for name in sorted(casts))
    assert f"Casts per card: {per_card}." in text
    per_gap = ", ".join(f"{rule} x{gaps[rule]}" for rule in sorted(gaps)) or "none"
    assert f"Gaps: {per_gap}." in text
    assert "Formats: standard x5" in text


def test_every_other_commander_game_gives_the_seats_commanders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Commander games with an odd seed: each seat's deck has one of the excerpt's creatures as
    its commander (903.3), cycled; with an even seed, none."""
    recorder = Recorder(canned_result())
    run_main(monkeypatch, recorder, "--format", "commander", "--games", "4", "--jobs", "1")
    creatures = CREATURES
    for config, decks, seed, _ in recorder.calls:
        assert config.commander is not None
        for player_deck in decks:
            commanders = [card.data.name for card in player_deck.commanders]
            if seed % 2:
                assert len(commanders) == 1 and commanders[0] in creatures
            else:
                assert commanders == []


def canned_result() -> FuzzResult:
    """A finished game, returned by a stubbed ``fuzz_game`` so preset tests don't play."""
    return fuzz_game(GameConfig.standard(), [Deck(()), Deck(())], 0)


def test_the_presets() -> None:
    """Quick: ten games, one of each player count (2 to 6) in each format, 40- and 10-card
    decks. Thorough: ten times as many, longer (40- and 20-card decks, rarer concessions), and
    every check before every decision."""
    assert (
        fuzz_tool.Preset(games=10, copies=(8, 2), concessions=200, check_every=10)
        == fuzz_tool.QUICK
    )
    assert (
        fuzz_tool.Preset(games=100, copies=(8, 4), concessions=500, check_every=1)
        == fuzz_tool.THOROUGH
    )


def test_the_default_run_cycles_every_player_count_in_both_formats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = Recorder(canned_result())
    text = run_main(monkeypatch, recorder, "--jobs", "1")
    shapes = [(len(decks), config.commander is not None) for config, decks, _, _ in recorder.calls]
    assert shapes == [(n, False) for n in range(2, 7)] + [(n, True) for n in range(2, 7)]
    assert "Run: quick preset;" in text


def test_thorough_runs_more_and_longer_games_with_every_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = Recorder(canned_result())
    text = run_main(monkeypatch, recorder, "--thorough", "--jobs", "1")
    assert len(recorder.calls) == 100
    for _, decks, seed, options in recorder.calls:
        assert options == {"concession_chance": 500, "check_every": 1}
        pool = [("spells", 8), ("creatures", 8), ("spells", 4), ("creatures", 4)]
        for seat, player_deck in enumerate(decks):
            names = Counter(card.data.name for card in player_deck.cards)
            assert names == expected_deck(*pool[(seed + seat) % len(pool)])
    assert (
        "Run: thorough preset; decks: the spells and creatures recipes with 8 and 4 of each basic "
        "land (basic_lands.json, cards.json), cycled among the seats; concessions: 1 decision in "
        "500; full checks every answer." in text
    )
    assert "100 games passed" in text
    # Progress every 10 games, before the summary.
    progress = [line for line in text.splitlines() if line.endswith("games passed...")]
    assert progress == [f"{done} of 100 games passed..." for done in range(10, 100, 10)]
    assert text.splitlines()[0].startswith("Run: thorough preset;")
    assert text.splitlines()[1:10] == progress


def test_explicit_options_override_the_preset(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder(canned_result())
    text = run_main(
        monkeypatch, recorder, "--thorough", "--games", "3", "--check-every", "5",
        "--concessions", "0", "--copies", "3", "--jobs", "1",
    )  # fmt: skip
    assert len(recorder.calls) == 3
    for _, decks, _, options in recorder.calls:
        assert options == {"concession_chance": 0, "check_every": 5}
        for player_deck in decks:
            names = Counter(card.data.name for card in player_deck.cards)
            assert names in (expected_deck("spells", 3), expected_deck("creatures", 3))
    assert (
        "decks: the spells and creatures recipes with 3 of each basic land (basic_lands.json, "
        "cards.json), cycled among the seats; concessions: never; full checks every 5" in text
    )


def test_a_failure_prints_the_reproduce_message(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing(config: GameConfig, decks: Sequence[Deck], seed: int, **options: Any) -> Any:
        raise fuzz_tool.FuzzFailure(f"game seed {seed}: broken")

    monkeypatch.setattr(fuzz_tool, "fuzz_game", failing)
    output = io.StringIO()
    with redirect_stdout(output):
        status = fuzz_tool.main(["--seed", "7", "--jobs", "1"])
    assert status == 1
    assert output.getvalue().splitlines()[1:] == [
        "FAILED: game seed 7: broken",
        "This run's options: --copies 8 2 --concessions 200 --check-every 10",
    ]


def test_parallel_jobs_play_the_same_games() -> None:
    """Games run in worker processes (the "spawn" start method, as on Windows) end exactly as
    when run one after another: only the timing line differs."""
    args = ["--games", "20", "--players", "2", "3", "--copies", "2", "--concessions", "50"]
    outputs: list[list[str]] = []
    for jobs in ("1", "3"):
        output = io.StringIO()
        with redirect_stdout(output):
            assert fuzz_tool.main([*args, "--jobs", jobs]) == 0
        outputs.append(output.getvalue().splitlines())
    assert outputs[0][:-1] == outputs[1][:-1]
    assert outputs[0][:2] == [
        "Run: quick preset; decks: the spells and creatures recipes with 2 of each basic land "
        "(basic_lands.json, cards.json), cycled among the seats; concessions: 1 decision in 50; "
        "full checks every 10 answers.",
        "10 of 20 games passed...",
    ]
    assert outputs[0][-1].endswith("(1 job).") and outputs[1][-1].endswith("(3 jobs).")


def test_the_script_runs_games_in_worker_processes() -> None:
    """Run as a script, as users do: the workers re-import the script itself (``__mp_main__``),
    the way Windows starts every worker."""
    completed = subprocess.run(
        [sys.executable, str(fuzz_tool.__file__), "--games", "2", "--jobs", "2", "--empty-decks"],
        capture_output=True,
        check=False,
        encoding="utf-8",
    )
    assert completed.returncode == 0, completed.stderr
    assert "2 games passed: 2 answers accepted, 0 rejected." in completed.stdout
    assert completed.stdout.rstrip().endswith("(2 jobs).")
