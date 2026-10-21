"""Seam tests: the engine obeys the rule-default functions everywhere (CLAUDE.md rule 12).

Each test replaces one function of ``resolve.rules.defaults`` with ``monkeypatch`` and checks the
engine follows it at every place the rule applies. Nothing in M2 can change these defaults yet;
M5 replaces the tests with real effects (docs/plans/m2.md §5.1). Expected values are worked from
the pinned CR:

- 305.2a-b: a player may play a land only while the lands they've played this turn are fewer
  than the lands they can play this turn.
- 402.2, 514.1: the active player discards down to their maximum hand size at cleanup; with no
  maximum hand size (402.2) nobody discards.
- 504.1: the draw step's turn-based action is the active player drawing the number of cards the
  function says.
- 500.8-500.10: effects add phases and steps; 500.11: a skipped step or phase doesn't begin.
- 500.7: extra turns are taken directly after the specified turn, the most recently created first;
  800.4k: a player who left the game doesn't begin a turn.
- 724: ending the turn removes the rest of the turn and goes to the cleanup step.
- 502.3: the permanents the function returns untap; 500.5: the mana it returns empties.
- 104.3, 704.5a-b: a player who can't lose the game doesn't lose at 0 life or after drawing
  from an empty library.
- 103.1: turn order proceeds clockwise (or the direction the game says).
- 103.4-103.6: starting life, opening hand size, mulligan choices and opening-hand actions.
- 117.1a: sorcery timing and flash; 302.6: tapping for costs.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass

import pytest

from resolve.agents.scripted import choose
from resolve.cards.primitives.costs import TapSelfCost
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import (
    ActivateAbilityOption,
    CastSpellOption,
    ChooseOne,
    ChooseSubset,
    Option,
    PassOption,
    Pick,
    PlayLandOption,
)
from resolve.engine.api import new_game, submit
from resolve.engine.sba import state_based_actions
from resolve.engine.turns import turn_frame_index
from resolve.errors import EngineError, NotImplementedRule
from resolve.events.cards import CardDrawn
from resolve.events.game import MulliganDeclared, PlayerLost
from resolve.events.mana import ManaPoolEmptied
from resolve.events.permanents import PermanentsUntapped
from resolve.events.turn import StepBegan, TurnBegan
from resolve.rules import defaults
from resolve.rules.defaults import LossReason, NextTurn
from resolve.state.config import GameConfig
from resolve.state.game import GameState, next_in_turn_order, players_in_game, turn_order
from resolve.state.ids import PlayerId
from resolve.state.invariants import invariant_violations
from resolve.state.mana import Mana, ManaType
from resolve.state.turn import TURN_SEQUENCE, Phase, Segment, Step
from resolve.tasks import Done, Task, TaskResult
from tests.game_fixtures import answer, decks, pass_until, request_of
from tests.scenario import Scenario, run_script
from tests.seams import patch, patch_card, patch_loss, patch_next_turn, patch_object, patch_skip

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)


def options(state: GameState) -> tuple[Option, ...]:
    request = request_of(state)
    assert request.kind is DecisionKind.PRIORITY_ACTION
    assert isinstance(request.space, ChooseOne)
    return request.space.options


def with_libraries(scenario: Scenario, cards: int = 3) -> Scenario:
    for player in scenario.players:
        scenario.library(player, ["Forest"] * cards)
    return scenario


def began(state: GameState) -> list[tuple[Phase, Step | None]]:
    """Every ``StepBegan`` of the turn the scenario started in: those logged before the first
    ``TurnBegan``."""
    steps: list[tuple[Phase, Step | None]] = []
    for entry in state.event_log:
        record = entry.record
        if isinstance(record, TurnBegan):
            break
        if isinstance(record, StepBegan):
            steps.append((record.phase, record.step))
    return steps


def turn_starts(state: GameState) -> list[tuple[int, PlayerId]]:
    return [
        (e.record.number, e.record.player)
        for e in state.event_log
        if isinstance(e.record, TurnBegan)
    ]


def until_turn(number: int) -> Callable[[GameState], bool]:
    return lambda state: state.turn is not None and state.turn.number >= number


# --- 305.2: land plays ------------------------------------------------------------------------


def test_305_2_a_second_land_is_offered_when_two_are_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = Scenario(2)
    first, second = scenario.hand(P0, ["Forest", "Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN, lands_played=1)
    patch(monkeypatch, "land_plays_allowed", lambda state, player: 2)
    state = scenario.build()
    assert PlayLandOption(first) in options(state)
    assert PlayLandOption(second) in options(state)


def test_305_2b_at_the_default_of_one_a_second_land_isnt_offered() -> None:
    scenario = Scenario(2)
    scenario.hand(P0, ["Forest", "Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN, lands_played=1)
    state = scenario.build()
    assert not [o for o in options(state) if isinstance(o, PlayLandOption)]


def test_305_2b_with_no_land_plays_allowed_no_land_is_offered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = Scenario(2)
    scenario.hand(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    patch(monkeypatch, "land_plays_allowed", lambda state, player: 0)
    state = scenario.build()
    assert not [o for o in options(state) if isinstance(o, PlayLandOption)]


def test_305_2a_the_limit_is_asked_of_the_player_playing(monkeypatch: pytest.MonkeyPatch) -> None:
    """The function gets the playing player, so an effect can give one player more plays."""
    asked: list[PlayerId] = []

    def plays(state: GameState, player: PlayerId) -> int:
        asked.append(player)
        return 1

    scenario = Scenario(2)
    scenario.hand(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    patch(monkeypatch, "land_plays_allowed", plays)
    scenario.build()
    assert asked and set(asked) == {P0}


# --- 117.1a, 601.3: timing --------------------------------------------------------------------


def test_117_1a_sorcery_timing_comes_from_the_function(monkeypatch: pytest.MonkeyPatch) -> None:
    """With sorcery timing everywhere, a land and a sorcery are offered in the upkeep step."""
    scenario = Scenario(2)
    forest, ponder = scenario.hand(P0, ["Forest", "Test Ponder"])
    scenario.at(Step.UPKEEP)
    patch(monkeypatch, "has_sorcery_timing", lambda state, player: True)
    state = scenario.build()
    assert PlayLandOption(forest) in options(state)
    assert CastSpellOption(ponder) in options(state)


def test_117_1a_without_sorcery_timing_neither_is_offered_in_the_main_phase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = Scenario(2)
    shock, forest, ponder = scenario.hand(P0, ["Test Shock", "Forest", "Test Ponder"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    patch(monkeypatch, "has_sorcery_timing", lambda state, player: False)
    state = scenario.build()
    assert PlayLandOption(forest) not in options(state)
    assert CastSpellOption(ponder) not in options(state)
    assert CastSpellOption(shock) in options(state)  # an instant needs no sorcery timing


def test_117_1a_may_cast_now_is_the_one_place_flash_would_plug_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A sorcery that may be cast now is offered at instant speed; an instant that may not be
    cast now isn't offered in the main phase."""
    scenario = Scenario(2)
    shock, ponder = scenario.hand(P0, ["Test Shock", "Test Ponder"])
    scenario.at(Step.UPKEEP)
    patch_card(monkeypatch, "may_cast_now", lambda state, player, obj: obj == ponder)
    state = scenario.build()
    assert CastSpellOption(ponder) in options(state)
    assert CastSpellOption(shock) not in options(state)


def test_601_3_the_cast_options_come_from_the_function(monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = Scenario(2)
    shock, ponder = scenario.hand(P0, ["Test Shock", "Test Ponder"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    patch(monkeypatch, "cast_options", lambda state, player: (ponder,))
    state = scenario.build()
    assert CastSpellOption(ponder) in options(state)
    assert CastSpellOption(shock) not in options(state)


# --- 402.2, 514.1: maximum hand size ----------------------------------------------------------

NINE = ["Forest"] * 9


def test_402_2_no_maximum_hand_size_means_no_cleanup_discard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = with_libraries(Scenario(2))
    scenario.hand(P0, NINE)
    scenario.at(Step.CLEANUP)
    patch(monkeypatch, "maximum_hand_size", lambda state, player: None)
    state = scenario.build()
    assert len(state.player(P0).hand) == 9
    assert request_of(state).kind is not DecisionKind.DISCARD
    assert not state.player(P0).graveyard


def test_402_2_a_maximum_of_5_discards_4_with_the_prompt_naming_5(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = with_libraries(Scenario(2))
    scenario.hand(P0, NINE)
    scenario.at(Step.CLEANUP)
    patch(monkeypatch, "maximum_hand_size", lambda state, player: 5)
    state = scenario.build()
    request = request_of(state)
    assert request.kind is DecisionKind.DISCARD and request.player == P0
    assert isinstance(request.space, ChooseSubset)
    assert (request.space.minimum, request.space.maximum) == (4, 4)
    assert "5" in request.prompt and "seven" not in request.prompt
    assert request.rules == ("514.1", "402.2")


def test_402_2_the_maximum_is_the_active_players(monkeypatch: pytest.MonkeyPatch) -> None:
    """514.1: only the active player discards; the function is asked about them."""
    asked: list[PlayerId] = []

    def maximum(state: GameState, player: PlayerId) -> int | None:
        asked.append(player)
        return 9

    scenario = with_libraries(Scenario(2))
    scenario.hand(P0, NINE)
    scenario.hand(P1, ["Forest"] * 12)
    scenario.at(Step.CLEANUP)
    patch(monkeypatch, "maximum_hand_size", maximum)
    state = scenario.build()
    assert set(asked) == {P0}
    assert len(state.player(P1).hand) == 12 and len(state.player(P0).hand) == 9


# --- 504.1: the draw step ---------------------------------------------------------------------


@pytest.mark.parametrize("count", [0, 1, 2, 3])
def test_504_1_the_draw_step_draws_what_the_function_says(
    monkeypatch: pytest.MonkeyPatch, count: int
) -> None:
    scenario = Scenario(3)
    scenario.library(P0, ["Forest"] * 5)
    scenario.at(Step.DRAW, begin=True)
    patch(monkeypatch, "draw_step_draws", lambda state, player: count)
    state = scenario.build()
    assert len(state.player(P0).hand) == count
    drawn = [e.record for e in state.event_log if isinstance(e.record, CardDrawn)]
    assert len(drawn) == count and all(d.rules[0] == "504.1" for d in drawn)


# --- 500.8-500.11: turn structure -------------------------------------------------------------


def test_500_8_an_inserted_segment_is_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """An additional postcombat main phase in the turn's structure: it begins twice in a row (the
    log's ``StepBegan`` entries show two), in order."""
    extended: tuple[Segment, ...] = (
        *TURN_SEQUENCE[:-2],
        (Phase.POSTCOMBAT_MAIN, None),
        *TURN_SEQUENCE[-2:],
    )
    patch(monkeypatch, "turn_structure", lambda state, player: extended)
    scenario = with_libraries(Scenario(2))
    scenario.at(Step.UNTAP, number=2)
    state = scenario.build()
    pass_until(state, until_turn(3))
    assert began(state) == [
        (Phase.BEGINNING, Step.UNTAP),
        (Phase.BEGINNING, Step.UPKEEP),
        (Phase.BEGINNING, Step.DRAW),
        (Phase.PRECOMBAT_MAIN, None),
        (Phase.COMBAT, Step.BEGINNING_OF_COMBAT),
        (Phase.COMBAT, Step.DECLARE_ATTACKERS),
        (Phase.COMBAT, Step.END_OF_COMBAT),
        (Phase.POSTCOMBAT_MAIN, None),
        (Phase.POSTCOMBAT_MAIN, None),
        (Phase.ENDING, Step.END),
        (Phase.ENDING, Step.CLEANUP),
    ]


def test_500_8_remaining_segments_are_data_an_effect_can_insert_into() -> None:
    """500.8: an additional combat phase after the precombat main phase. The turn in progress
    keeps its remaining segments as data (``TurnState.segments``), so inserting the combat phase's
    segments at the front makes it happen next, once more than normal."""
    scenario = with_libraries(Scenario(2))
    scenario.at(Phase.PRECOMBAT_MAIN, number=2)
    state = scenario.build()
    turn = state.turn
    assert turn is not None
    assert turn.segments[0] == (Phase.COMBAT, Step.BEGINNING_OF_COMBAT)
    combat = [segment for segment in TURN_SEQUENCE if segment[0] is Phase.COMBAT]
    turn.segments[0:0] = combat
    assert invariant_violations(state) == []
    state = copy.deepcopy(state)  # the segments are plain data: a copy keeps them
    pass_until(state, until_turn(3))
    steps = began(state)
    assert [s for s in steps if s[0] is Phase.COMBAT] == [
        (Phase.COMBAT, Step.BEGINNING_OF_COMBAT),
        (Phase.COMBAT, Step.DECLARE_ATTACKERS),
        (Phase.COMBAT, Step.END_OF_COMBAT),
    ] * 2


def test_500_11_a_skipped_step_doesnt_begin(monkeypatch: pytest.MonkeyPatch) -> None:
    """The function says the upkeep step is skipped: no ``StepBegan`` for it, the untap step is
    followed directly by the draw step."""
    patch_skip(monkeypatch, lambda state, segment: segment == (Phase.BEGINNING, Step.UPKEEP))
    scenario = with_libraries(Scenario(2))
    scenario.at(Step.UNTAP, number=2)
    state = scenario.build()
    pass_until(state, until_turn(3))
    steps = began(state)
    assert (Phase.BEGINNING, Step.UPKEEP) not in steps
    assert steps[:3] == [
        (Phase.BEGINNING, Step.UNTAP),
        (Phase.BEGINNING, Step.DRAW),
        (Phase.PRECOMBAT_MAIN, None),
    ]
    # The function replaced the default skips too: declare blockers and combat damage now begin.
    assert (Phase.COMBAT, Step.COMBAT_DAMAGE) in steps


def test_500_11_the_skip_question_is_asked_about_each_segment_of_the_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[Segment] = []

    def skipped(state: GameState, segment: Segment) -> bool:
        asked.append(segment)
        return False

    patch_skip(monkeypatch, skipped)
    scenario = with_libraries(Scenario(2))
    scenario.at(Step.UNTAP, number=2)
    state = scenario.build()
    pass_until(state, until_turn(3))
    # The scenario starts at the beginning of the untap step, which is already running.
    assert asked[: len(TURN_SEQUENCE) - 1] == list(TURN_SEQUENCE[1:])


# --- 500.7: extra turns -----------------------------------------------------------------------


def test_500_7_an_extra_turn_comes_first() -> None:
    """Player 0's turn 3 has an extra turn added for player 0: the next turn is theirs again
    (number 4), then the normal order resumes with player 1 (500.7: directly after the
    specified turn; 103.1)."""
    scenario = with_libraries(Scenario(2), cards=6)
    scenario.at(Phase.POSTCOMBAT_MAIN, number=3, active=P0)
    state = scenario.build()
    state.extra_turns.append(P0)
    pass_until(state, until_turn(5))
    assert turn_starts(state) == [(4, P0), (5, P1)]
    assert state.extra_turns == []


def test_500_7_the_most_recently_created_extra_turn_is_taken_first() -> None:
    """Turn 3 is player 1's. Extra turns for player 2 and then player 0 were created, in that
    order: player 0's is taken first, then player 2's, then the normal turn after player 1's
    turn, which is player 2's."""
    scenario = with_libraries(Scenario(3), cards=8)
    scenario.at(Phase.POSTCOMBAT_MAIN, number=3, active=P1)
    state = scenario.build()
    state.extra_turns.extend([P2, P0])
    pass_until(state, until_turn(6))
    assert turn_starts(state) == [(4, P0), (5, P2), (6, P2)]


def test_800_4k_an_extra_turn_of_a_player_who_left_doesnt_begin() -> None:
    scenario = with_libraries(Scenario(3), cards=8)
    scenario.at(Phase.POSTCOMBAT_MAIN, number=3, active=P0)
    state = scenario.build()
    state.extra_turns.append(P1)
    state.player(P1).left_game = True
    state.player(P1).lost = True
    pass_until(state, until_turn(4))
    assert turn_starts(state) == [(4, P2)]  # P1 is gone: the normal order skips them too
    assert state.extra_turns == []


def test_500_7_the_next_turn_function_is_obeyed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The function names the player of the next turn; here always player 1, even after
    player 1's own turn."""
    patch_next_turn(monkeypatch, lambda state, after: NextTurn(P1, extra=False))
    scenario = with_libraries(Scenario(3), cards=8)
    scenario.at(Phase.POSTCOMBAT_MAIN, number=3, active=P1)
    state = scenario.build()
    pass_until(state, until_turn(5))
    assert turn_starts(state) == [(4, P1), (5, P1)]


def test_103_1_turn_order_follows_the_direction_the_game_records() -> None:
    state = Scenario(3, starting_player=0).build()
    assert turn_order(state) == (P0, P1, P2) and next_in_turn_order(state, P0) == P1
    state.turn_direction = -1
    assert turn_order(state) == (P0, P2, P1)
    assert next_in_turn_order(state, P0) == P2 and next_in_turn_order(state, P2) == P1
    assert players_in_game(state) == (P0, P2, P1)
    assert invariant_violations(state) == []


# --- 724: the turn frame ----------------------------------------------------------------------


@dataclass(slots=True)
class CutTheTurn(Task):
    """Test-only stand-in for ending the turn (724.1d): removes the tasks between this one and
    the turn's frame, and leaves only the cleanup step among the remaining segments."""

    def run(self, state: GameState) -> TaskResult:
        frame = turn_frame_index(state)
        del state.tasks[frame + 1 : -1]
        assert state.turn is not None
        state.turn.segments[:] = [
            segment for segment in TURN_SEQUENCE if segment[1] is Step.CLEANUP
        ]
        return Done()


def test_724_the_turn_frame_lets_the_rest_of_a_turn_be_removed() -> None:
    """The turn frame is a marker in the task stack; everything above it belongs to the turn in
    progress. Removing those tasks and the remaining segments skips straight to the cleanup step
    (724.1d): no combat, no postcombat main phase and no end step begin (724.1e), and the next
    turn begins normally."""
    scenario = with_libraries(Scenario(2), cards=6)
    scenario.at(Phase.PRECOMBAT_MAIN, number=2)
    state = scenario.build(CutTheTurn())
    pass_until(state, until_turn(3))
    assert began(state) == [(Phase.ENDING, Step.CLEANUP)]
    assert turn_starts(state) == [(3, P1)]


def test_724_there_is_no_turn_frame_outside_a_turn() -> None:
    state = Scenario(2).build()
    with pytest.raises(EngineError, match="turn"):
        turn_frame_index(state)


# --- 502.3, 500.5 ------------------------------------------------------------------------------


def test_502_3_only_the_returned_permanents_untap(monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = Scenario(2)
    first, second = scenario.battlefield(P0, ["Forest", "Forest"])
    theirs = scenario.battlefield(P1, ["Forest"])[0]
    scenario.tap(first, second, theirs)
    scenario.at(Step.UNTAP, number=2)
    patch(monkeypatch, "permanents_that_untap", lambda state, player: (first,))
    state = scenario.build()
    assert not state.objects[first].tapped
    assert state.objects[second].tapped and state.objects[theirs].tapped
    untapped = [e.record for e in state.event_log if isinstance(e.record, PermanentsUntapped)]
    assert [u.objs for u in untapped] == [(first,)]


def test_502_3_when_none_untap_no_untap_event_happens(monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = Scenario(2)
    (forest,) = scenario.battlefield(P0, ["Forest"])
    scenario.tap(forest)
    scenario.at(Step.UNTAP, number=2)
    patch(monkeypatch, "permanents_that_untap", lambda state, player: ())
    state = scenario.build()
    assert state.objects[forest].tapped
    assert not [e for e in state.event_log if isinstance(e.record, PermanentsUntapped)]


def test_500_5_kept_mana_doesnt_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = with_libraries(Scenario(2))
    scenario.mana(P0, ManaType.GREEN, ManaType.RED)
    scenario.at(Step.UPKEEP, number=2, priority=P0, passed=[P1])
    patch(monkeypatch, "mana_that_empties", lambda state, player: ())
    state = scenario.build()
    run_script(state, choose(PassOption(), player=P0))
    assert state.turn is not None and state.turn.step is Step.DRAW  # the upkeep ended
    assert state.player(P0).mana_pool == [Mana(ManaType.GREEN), Mana(ManaType.RED)]
    assert not [e for e in state.event_log if isinstance(e.record, ManaPoolEmptied)]


def test_500_5_only_the_returned_mana_empties(monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = with_libraries(Scenario(2))
    scenario.mana(P0, ManaType.GREEN, ManaType.RED, ManaType.GREEN)
    scenario.at(Step.UPKEEP, number=2, priority=P0, passed=[P1])
    patch(
        monkeypatch,
        "mana_that_empties",
        lambda state, player: tuple(
            u for u in state.player(player).mana_pool if u.type is ManaType.GREEN
        ),
    )
    state = scenario.build()
    run_script(state, choose(PassOption(), player=P0))
    assert state.player(P0).mana_pool == [Mana(ManaType.RED)]
    (emptied,) = [e.record for e in state.event_log if isinstance(e.record, ManaPoolEmptied)]
    assert emptied.mana == (Mana(ManaType.GREEN),) * 2 and emptied.kept == (Mana(ManaType.RED),)


# --- 104.3: losing the game -------------------------------------------------------------------


def test_104_3_a_player_who_cant_lose_stays_in_at_zero_life(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[tuple[PlayerId, LossReason]] = []

    def cant_lose(state: GameState, player: PlayerId, reason: LossReason) -> bool:
        asked.append((player, reason))
        return player != P1

    patch_loss(monkeypatch, cant_lose)
    scenario = Scenario(2)
    scenario.life(P1, 0)
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    assert state.result is None and not state.player(P1).lost
    assert (P1, LossReason.LIFE_TOTAL) in asked
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION
    assert not [e for e in state.event_log if isinstance(e.record, PlayerLost)]


def test_104_3_a_player_who_can_lose_still_does_at_zero_life_with_the_function_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_loss(monkeypatch, lambda state, player, reason: player != P0)
    scenario = Scenario(2)
    scenario.life(P1, 0)
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    assert state.result is not None and state.result.winners == (P0,)


def test_704_5b_a_player_who_cant_lose_after_drawing_from_an_empty_library_stays_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """704.5b: the loss is asked for with the empty-library reason; refused, the player stays in
    (the draw attempt is remembered: when they can lose again they do)."""
    asked: list[LossReason] = []

    def cant_lose(state: GameState, player: PlayerId, reason: LossReason) -> bool:
        asked.append(reason)
        return False

    patch_loss(monkeypatch, cant_lose)
    scenario = Scenario(2)
    scenario.at(Step.DRAW, begin=True, number=2, active=P1)
    state = scenario.build()
    assert LossReason.EMPTY_LIBRARY in asked
    assert state.result is None and state.player(P1).drew_from_empty_library
    patch_loss(monkeypatch, lambda state, player, reason: True)
    events = state_based_actions(state)
    assert [e.player for e in events if isinstance(e, PlayerLost)] == [P1]


# --- 103.4-103.6: starting the game ----------------------------------------------------------


def test_103_4_starting_life_comes_from_the_function(monkeypatch: pytest.MonkeyPatch) -> None:
    patch(monkeypatch, "starting_life", lambda state, player: 13 + player)
    state = new_game(GameConfig.standard(), decks(3), seed=1)
    assert [p.life for p in state.players] == [13, 14, 15]


def test_103_5_the_opening_hand_size_comes_from_the_function(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch(monkeypatch, "starting_hand_size", lambda state, player: 3 + player)
    state = new_game(GameConfig.standard(), decks(2), seed=1)
    submit(state, answer(state, Pick(0)))  # the first mulligan question follows the deal
    assert request_of(state).kind is DecisionKind.MULLIGAN
    assert [len(p.hand) for p in state.players] == [3, 4]


def test_103_5_a_mulligan_option_that_isnt_offered_isnt_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With only "keep" on offer no one is asked whether to mulligan (a question with a single
    possible answer isn't asked): the first turn begins at once."""
    patch(monkeypatch, "mulligan_options", lambda state, player: (defaults.KEEP,))
    state = new_game(GameConfig.standard(), decks(2), seed=1)
    submit(state, answer(state, Pick(0)))
    assert state.turn is not None and request_of(state).kind is DecisionKind.PRIORITY_ACTION
    assert not [e for e in state.event_log if isinstance(e.record, MulliganDeclared)]
    assert [len(p.hand) for p in state.players] == [7, 7]


def test_103_5_a_hand_with_cards_is_asked_keep_or_mulligan() -> None:
    """By default the options are keep and mulligan, in that order."""
    state = new_game(GameConfig.standard(), decks(2), seed=1)
    submit(state, answer(state, Pick(0)))
    request = request_of(state)
    assert request.kind is DecisionKind.MULLIGAN
    assert isinstance(request.space, ChooseOne)
    assert request.space.options == (defaults.KEEP, defaults.MULLIGAN)


def test_103_6_an_action_from_the_opening_hand_is_a_gap_not_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """103.6: once the mulligan process is complete, the starting player and then the others may
    take actions with cards from their opening hand. The engine can't do any yet, so a function
    that offers one stops the game loudly instead of skipping the step."""
    patch(
        monkeypatch,
        "opening_hand_actions",
        lambda state, player: (state.player(player).hand[0],) if player == P1 else (),
    )
    state = new_game(GameConfig.standard(), decks(2), seed=1)
    with pytest.raises(NotImplementedRule, match=r"103\.6"):
        submit(state, answer(state, Pick(0)))
        pass_until(state, lambda s: s.turn is not None)


# --- 302.6: tapping for costs ------------------------------------------------------------------


def test_302_6_a_permanent_that_cant_tap_for_a_cost_offers_no_ability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = Scenario(2)
    (forest,) = scenario.battlefield(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    patch_object(monkeypatch, "can_tap_for_cost", lambda state, obj: False)
    state = scenario.build()
    assert not [o for o in options(state) if isinstance(o, ActivateAbilityOption)]
    assert not TapSelfCost().can_pay(state, forest, P0)


def test_302_6_a_creature_the_function_allows_to_tap_offers_its_ability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A land creature (305.9) has the intrinsic mana ability of its basic land type (305.6): a
    {T} cost on a creature."""
    scenario = Scenario(2)
    (dryad,) = scenario.battlefield(P0, ["Test Land Creature"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    patch_object(monkeypatch, "can_tap_for_cost", lambda state, obj: True)
    state = scenario.build()
    assert ActivateAbilityOption(dryad, 0) in options(state)


def test_118_3_an_already_tapped_permanent_cant_pay_a_tap_cost_whatever_the_function_says(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = Scenario(2)
    (forest,) = scenario.battlefield(P0, ["Forest"])
    scenario.tap(forest)
    scenario.at(Phase.PRECOMBAT_MAIN)
    patch_object(monkeypatch, "can_tap_for_cost", lambda state, obj: True)
    state = scenario.build()
    assert not TapSelfCost().can_pay(state, forest, P0)
