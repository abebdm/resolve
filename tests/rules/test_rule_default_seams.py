"""Rule defaults are tested through their seam (CLAUDE.md, rule 12 and "Testing requirements").

Each test replaces one function of ``resolve.engine.defaults`` with ``monkeypatch`` and checks
the engine obeys it everywhere it applies. That proves the function is the one place effects
plug into. M5, when real effects change these defaults, replaces these tests with tests that use
them.
"""

# Lambdas that replace engine functions take their parameter types from the function.
# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false

from __future__ import annotations

import pytest

from resolve.agents.scripted import Choose, choose
from resolve.cards.primitives.abilities import ActivatedManaAbility
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.request import DecisionAnswer
from resolve.decisions.spaces import (
    ActivateAbilityOption,
    CastSpellOption,
    ChooseOne,
    ChooseSubset,
    ObjectOption,
    Option,
    PassOption,
    Pick,
    PlayLandOption,
)
from resolve.effects.characteristics import characteristics
from resolve.engine import defaults
from resolve.engine.api import new_game, submit, view_for
from resolve.engine.concede import concede
from resolve.engine.deck import Deck
from resolve.engine.defaults import KEEP, MULLIGAN, LossReason, NextTurn
from resolve.engine.loop import run
from resolve.engine.setup import initial_state
from resolve.engine.turns import TakeTurn, cut_rest_of_turn
from resolve.errors import InvalidAnswer, NotImplementedRule
from resolve.events.turn import PriorityPassed, StepBegan, TurnBegan
from resolve.state.config import GameConfig
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.invariants import invariant_violations
from resolve.state.mana import Mana, ManaType
from resolve.state.turn import TURN_SEQUENCE, Phase, Segment, Step
from tests.game_fixtures import Passer, decks, pass_until, patch_function, request_of
from tests.scenario import Scenario, run_script

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)


def priority_options(state: GameState) -> tuple[Option, ...]:
    request = request_of(state)
    assert request.kind is DecisionKind.PRIORITY_ACTION
    assert isinstance(request.space, ChooseOne)
    return request.space.options


def pass_(player: PlayerId) -> Choose:
    return choose(PassOption(), player=player, kind=DecisionKind.PRIORITY_ACTION)


def stocked(players: int = 2) -> Scenario:
    scenario = Scenario(players)
    for player in scenario.players:
        scenario.library(player, ["Forest"] * 4)
    return scenario


def begun(state: GameState) -> list[Segment]:
    return [(r.phase, r.step) for e in state.event_log if isinstance(r := e.record, StepBegan)]


# --- 305.2: land plays ----------------------------------------------------------------------


def test_305_2_b_a_second_land_isnt_offered_at_the_default_of_one() -> None:
    scenario = stocked()
    scenario.hand(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN, lands_played=1)
    state = scenario.build()
    assert not any(isinstance(o, PlayLandOption) for o in priority_options(state))


def test_305_2_a_second_land_is_offered_when_two_are_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_function(monkeypatch, defaults, "land_plays_allowed", lambda state, player: 2)
    scenario = stocked()
    (forest,) = scenario.hand(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN, lands_played=1)
    state = scenario.build()
    assert PlayLandOption(forest) in priority_options(state)
    # ...and a third isn't (305.2b).
    scenario = stocked()
    scenario.hand(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN, lands_played=2)
    assert not any(isinstance(o, PlayLandOption) for o in priority_options(scenario.build()))


def test_305_2_no_land_plays_allowed_offers_no_land(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_function(monkeypatch, defaults, "land_plays_allowed", lambda state, player: 0)
    scenario = stocked()
    scenario.hand(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    assert not any(isinstance(o, PlayLandOption) for o in priority_options(scenario.build()))


def test_305_1_the_zones_lands_may_be_played_from_come_from_the_function(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = stocked()
    scenario.hand(P0, ["Forest"])
    (from_graveyard,) = scenario.graveyard(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    default = [o for o in priority_options(scenario.build()) if isinstance(o, PlayLandOption)]
    assert len(default) == 1  # the land in the hand
    patch_function(
        monkeypatch, defaults, "land_play_options", lambda state, player: (from_graveyard,)
    )
    scenario = stocked()
    scenario.hand(P0, ["Forest"])
    (from_graveyard,) = scenario.graveyard(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    lands = [o for o in priority_options(state) if isinstance(o, PlayLandOption)]
    assert lands == [PlayLandOption(from_graveyard)]


def test_117_1a_timing_comes_from_the_function(monkeypatch: pytest.MonkeyPatch) -> None:
    """With sorcery timing everywhere, a creature may be cast in the upkeep."""
    scenario = stocked()
    scenario.hand(P0, ["Grizzly Bears"])
    scenario.at(Step.UPKEEP)
    assert not any(isinstance(o, CastSpellOption) for o in priority_options(scenario.build()))
    patch_function(monkeypatch, defaults, "has_sorcery_timing", lambda state, player: True)
    scenario = stocked()
    scenario.hand(P0, ["Grizzly Bears"])
    scenario.at(Step.UPKEEP)
    assert any(isinstance(o, CastSpellOption) for o in priority_options(scenario.build()))


def test_117_1a_may_cast_now_decides_whether_a_spell_is_offered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_function(monkeypatch, defaults, "may_cast_now", lambda state, player, obj: False)
    scenario = stocked()
    scenario.hand(P0, ["Test Shock", "Grizzly Bears"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    assert not any(isinstance(o, CastSpellOption) for o in priority_options(scenario.build()))


# --- 402.2, 504.1: hand size and drawing -----------------------------------------------------

NINE = ["Forest", "Llanowar Elves", "Forest", "Test Shock", "Forest", "Forest", "Test Ponder",
        "Forest", "Forest"]  # fmt: skip


def test_402_2_no_maximum_hand_size_means_no_cleanup_discard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_function(monkeypatch, defaults, "maximum_hand_size", lambda state, player: None)
    scenario = stocked()
    scenario.hand(P0, NINE)
    scenario.at(Step.CLEANUP)
    state = scenario.build()
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION  # turn 2's upkeep
    assert len(state.player(P0).hand) == 9


def test_402_2_a_maximum_of_five_discards_four_and_the_prompt_names_five(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_function(monkeypatch, defaults, "maximum_hand_size", lambda state, player: 5)
    scenario = stocked()
    hand = scenario.hand(P0, NINE)
    scenario.at(Step.CLEANUP)
    state = scenario.build()
    request = request_of(state)
    assert request.kind is DecisionKind.DISCARD
    assert request.space == ChooseSubset(tuple(ObjectOption(o) for o in hand), 4, 4)
    assert "5" in request.prompt and "seven" not in request.prompt


def test_402_2_the_maximum_is_asked_per_player(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_function(monkeypatch, defaults, "maximum_hand_size", lambda state, player: 9)
    scenario = stocked()
    scenario.hand(P0, NINE)
    scenario.at(Step.CLEANUP)
    assert request_of(scenario.build()).kind is DecisionKind.PRIORITY_ACTION


def test_504_1_the_draw_step_draws_what_the_function_says(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_function(monkeypatch, defaults, "draw_step_draws", lambda state, player: 3)
    scenario = stocked()
    scenario.at(Step.DRAW, number=2, begin=True)
    state = scenario.build()
    assert len(state.player(P0).hand) == 3


def test_504_1_a_draw_step_that_draws_nothing_draws_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_function(monkeypatch, defaults, "draw_step_draws", lambda state, player: 0)
    scenario = stocked()
    scenario.at(Step.DRAW, number=2, begin=True)
    state = scenario.build()
    assert state.player(P0).hand == [] and len(state.player(P0).library) == 4


# --- 500: the structure of the turn ----------------------------------------------------------


def test_500_8_an_inserted_segment_is_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """An extra precombat main phase after the first one: ``StepBegan`` twice, in order."""
    extra = (
        *TURN_SEQUENCE[:4],
        (Phase.PRECOMBAT_MAIN, None),
        *TURN_SEQUENCE[4:],
    )
    patch_function(monkeypatch, defaults, "turn_structure", lambda state, player: extra)
    scenario = stocked()
    scenario.at(Step.UNTAP)
    state = scenario.build()
    pass_until(state, lambda s: s.turn is not None and s.turn.number == 2)
    first_turn = begun(state)[: len(extra)]
    assert first_turn.count((Phase.PRECOMBAT_MAIN, None)) == 2
    main = first_turn.index((Phase.PRECOMBAT_MAIN, None))
    assert first_turn[main + 1] == (Phase.PRECOMBAT_MAIN, None)
    assert first_turn[main + 2] == (Phase.COMBAT, Step.BEGINNING_OF_COMBAT)


def test_500_8_effects_may_add_a_segment_to_the_turn_in_progress() -> None:
    scenario = stocked()
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    assert state.turn is not None
    state.turn.segments.insert(0, (Phase.POSTCOMBAT_MAIN, None))  # e.g. an additional phase
    pass_until(state, lambda s: s.turn is not None and s.turn.number == 2)
    assert begun(state)[:2] == [
        (Phase.POSTCOMBAT_MAIN, None),
        (Phase.COMBAT, Step.BEGINNING_OF_COMBAT),
    ]


def test_500_11_a_skipped_step_doesnt_begin(monkeypatch: pytest.MonkeyPatch) -> None:
    original = defaults.is_skipped
    patch_function(
        monkeypatch,
        defaults,
        "is_skipped",
        lambda state, segment: segment[1] is Step.UPKEEP or original(state, segment),
    )
    scenario = stocked()
    scenario.at(Step.UNTAP, number=2)
    state = scenario.build()
    assert state.turn is not None and state.turn.step is Step.DRAW  # the upkeep never began
    assert (Phase.BEGINNING, Step.UPKEEP) not in begun(state)
    assert (Phase.BEGINNING, Step.UNTAP) in begun(state)


def test_500_7_an_extra_turn_comes_first() -> None:
    scenario = stocked(3)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    state.extra_turns = [P0]
    pass_until(state, lambda s: s.turn is not None and s.turn.number == 4)
    turns = [(r.number, r.player) for e in state.event_log if isinstance(r := e.record, TurnBegan)]
    assert turns == [(2, P0), (3, P1), (4, P2)]
    assert state.extra_turns == []


def test_500_7_the_next_turn_comes_from_the_function(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_function(monkeypatch, defaults, "next_turn", lambda state: NextTurn(P2, ()))
    scenario = stocked(3)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    pass_until(state, lambda s: s.turn is not None and s.turn.number == 2)
    assert state.turn is not None and state.turn.active_player == P2


def test_103_1_reversed_turn_order_goes_to_the_previous_seat() -> None:
    scenario = stocked(3)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    state.turn_direction = -1
    pass_until(state, lambda s: s.turn is not None and s.turn.number == 3)
    turns = [r.player for e in state.event_log if isinstance(r := e.record, TurnBegan)]
    assert turns == [P2, P1]


def test_724_the_turn_frame_lets_the_rest_of_a_turn_be_removed() -> None:
    """724.1d: the game skips straight to the cleanup step, skipping the steps between."""
    scenario = stocked()
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    assert any(isinstance(task, TakeTurn) for task in state.tasks)  # the turn frame
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION
    cut_rest_of_turn(state)
    assert state.pending is None
    assert [type(task) for task in state.tasks] == [TakeTurn]  # only the frame is left
    run(state)
    assert begun(state)[:2] == [(Phase.ENDING, Step.CLEANUP), (Phase.BEGINNING, Step.UNTAP)]
    assert state.turn is not None and (state.turn.number, state.turn.active_player) == (2, P1)
    assert invariant_violations(state) == []


# --- 502.3, 500.5: untapping and emptying ----------------------------------------------------


def test_502_3_only_the_returned_permanents_untap(monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = stocked()
    first, second = scenario.battlefield(P0, ["Forest", "Forest"])
    scenario.tap(first, second)
    patch_function(monkeypatch, defaults, "permanents_that_untap", lambda state, player: (first,))
    scenario.at(Step.UNTAP, number=2)
    state = scenario.build()
    assert not state.objects[first].tapped
    assert state.objects[second].tapped


def test_502_3_all_untap_by_default() -> None:
    scenario = stocked()
    first, second = scenario.battlefield(P0, ["Forest", "Forest"])
    scenario.tap(first, second)
    scenario.at(Step.UNTAP, number=2)
    state = scenario.build()
    assert not state.objects[first].tapped and not state.objects[second].tapped


def test_500_5_unspent_mana_empties_by_default() -> None:
    scenario = stocked()
    scenario.mana(P0, ManaType.GREEN)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1))
    assert state.player(P0).mana_pool == []


def test_500_5_kept_mana_doesnt_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_function(monkeypatch, defaults, "mana_that_empties", lambda state, player: ())
    scenario = stocked()
    scenario.mana(P0, ManaType.GREEN)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1))
    assert state.turn is not None and state.turn.step is Step.BEGINNING_OF_COMBAT
    assert state.player(P0).mana_pool == [Mana(ManaType.GREEN)]


def test_500_5_part_of_a_pool_may_stay(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the mana the function returns empties; the rest stays (500.5, 106.4)."""

    def only_red(state: GameState, player: PlayerId) -> tuple[Mana, ...]:
        return tuple(m for m in state.player(player).mana_pool if m.type is ManaType.RED)

    patch_function(monkeypatch, defaults, "mana_that_empties", only_red)
    scenario = stocked()
    scenario.mana(P0, ManaType.GREEN, ManaType.RED, ManaType.GREEN)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1))
    assert state.player(P0).mana_pool == [Mana(ManaType.GREEN), Mana(ManaType.GREEN)]


# --- 104.3: losing -----------------------------------------------------------------------------


def test_104_3_a_player_who_cant_lose_stays_in_at_zero_life(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[tuple[PlayerId, LossReason]] = []

    def cant_lose(state: GameState, player: PlayerId, reason: LossReason) -> bool:
        asked.append((player, reason))
        return False

    patch_function(monkeypatch, defaults, "can_lose_game", cant_lose)
    scenario = stocked()
    scenario.life(P0, 0)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    assert state.result is None and not state.player(P0).left_game
    assert (P0, LossReason.ZERO_LIFE) in asked


def test_104_3_a_player_at_zero_life_loses_by_default() -> None:
    scenario = stocked()
    scenario.life(P0, 0)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    assert state.result is not None and state.result.winners == (P1,)


def test_104_3_the_reason_matters(monkeypatch: pytest.MonkeyPatch) -> None:
    """A player who can't lose to drawing from an empty library still loses at 0 life."""
    patch_function(
        monkeypatch,
        defaults,
        "can_lose_game",
        lambda state, player, reason: reason is LossReason.ZERO_LIFE,
    )
    scenario = Scenario(2)
    scenario.library(P1, ["Forest"] * 2)
    scenario.at(Step.DRAW, number=2, begin=True)  # P1's turn would draw; P0 has an empty library
    scenario.hand(P0, [])
    state = scenario.build()
    state.player(P0).drew_from_empty_library = True
    pass_until(state, lambda s: s.turn is not None and s.turn.number == 3)
    assert state.result is None and not state.player(P0).left_game


# --- 723: who decides and who sees -------------------------------------------------------------


def control_p0(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_function(
        monkeypatch,
        defaults,
        "deciding_player",
        lambda state, player: P1 if player == P0 else player,
    )


def test_723_5_the_deciding_player_receives_the_request(monkeypatch: pytest.MonkeyPatch) -> None:
    control_p0(monkeypatch)
    scenario = stocked()
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    request = request_of(state)
    assert (request.player, request.for_player) == (P1, P0)
    assert request.kind is DecisionKind.PRIORITY_ACTION
    # The controlled player can't answer (723.5); nothing changes.
    before = len(state.event_log)
    with pytest.raises(InvalidAnswer):
        submit(state, DecisionAnswer(request.id, P0, Pick(0)))
    assert len(state.event_log) == before and state.pending == request
    # The controller answers for them: P0 passes priority (723.5).
    submit(state, DecisionAnswer(request.id, P1, Pick(0)))
    passes = [r for e in state.event_log if isinstance(r := e.record, PriorityPassed)]
    assert [p.player for p in passes] == [P0]
    assert request_of(state).for_player == P1 and request_of(state).player == P1
    assert invariant_violations(state) == []


def test_723_5_decisions_default_to_the_player_themselves() -> None:
    scenario = stocked()
    scenario.at(Phase.PRECOMBAT_MAIN)
    request = request_of(scenario.build())
    assert request.player == request.for_player == P0


def test_723_5_other_decisions_are_remapped_too(monkeypatch: pytest.MonkeyPatch) -> None:
    """The discard to hand size (514.1) is P0's decision, made by P1."""
    control_p0(monkeypatch)
    scenario = stocked()
    scenario.hand(P0, NINE)
    scenario.at(Step.CLEANUP)
    request = request_of(scenario.build())
    assert request.kind is DecisionKind.DISCARD
    assert (request.player, request.for_player) == (P1, P0)


def test_723_4_the_controller_sees_what_the_controlled_player_sees(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = stocked(3)
    scenario.hand(P0, ["Forest", "Test Shock"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    plain = scenario.build()
    assert [o.name for o in view_for(plain, P1).players[0].hand] == [None, None]
    control_p0(monkeypatch)
    scenario = stocked(3)
    scenario.hand(P0, ["Forest", "Test Shock"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    assert [o.name for o in view_for(state, P1).players[0].hand] == ["Forest", "Test Shock"]
    assert [o.name for o in view_for(state, P2).players[0].hand] == [None, None]
    assert [o.name for o in view_for(state, P0).players[0].hand] == ["Forest", "Test Shock"]


def test_723_4_a_controller_doesnt_see_the_controlled_players_library(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cards outside the game stay private, and a library shows only its size (401.3)."""
    control_p0(monkeypatch)
    scenario = stocked()
    scenario.at(Phase.PRECOMBAT_MAIN)
    view = view_for(scenario.build(), P1)
    assert view.players[0].library_size == 4


def test_723_6_the_controller_cant_make_the_controlled_player_concede(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P1 conceding while controlling P0 concedes P1's own game, not P0's."""
    control_p0(monkeypatch)
    scenario = stocked(3)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    assert request_of(state).player == P1
    concede(state, P1)
    assert state.player(P1).left_game and not state.player(P0).left_game
    assert state.result is None


def test_723_6_a_controlled_player_may_concede_at_any_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """104.3a: the player whose decisions another player makes can still concede."""
    control_p0(monkeypatch)
    scenario = stocked(3)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    concede(state, P0)
    assert state.player(P0).left_game and not state.player(P1).left_game


def test_800_4a_control_of_a_player_ends_when_the_controller_leaves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A deciding player who left the game no longer decides for another (800.4a)."""
    control_p0(monkeypatch)
    scenario = stocked(3)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    concede(state, P1)
    request = request_of(state)
    assert (request.player, request.for_player) == (P0, P0)


# --- 103.5, 103.6: starting the game -------------------------------------------------------------


def test_103_5_a_mulligan_isnt_asked_when_it_isnt_offered(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_function(monkeypatch, defaults, "mulligan_options", lambda state, player: (KEEP,))
    state = new_game(GameConfig.standard(), decks(2), 1)
    submit(state, DecisionAnswer(request_of(state).id, request_of(state).player, Pick(0)))
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION  # no MULLIGAN question
    assert len(state.player(P0).hand) == 7


def test_103_5_both_options_are_offered_by_default() -> None:
    state = new_game(GameConfig.standard(), decks(2), 1)
    submit(state, DecisionAnswer(request_of(state).id, request_of(state).player, Pick(0)))
    request = request_of(state)
    assert request.kind is DecisionKind.MULLIGAN
    assert request.space == ChooseOne((KEEP, MULLIGAN))


def test_103_6_an_opening_hand_action_is_a_loud_gap(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_function(
        monkeypatch,
        defaults,
        "opening_hand_actions",
        lambda state, player: (ObjectId(1),) if player == P1 else (),
    )
    state = new_game(GameConfig.standard(), decks(2), 1)
    submit(state, DecisionAnswer(request_of(state).id, request_of(state).player, Pick(0)))
    passer = Passer()
    with pytest.raises(NotImplementedRule, match=r"103\.6"):
        for _ in range(50):
            request = request_of(state)
            submit(state, passer.decide(view_for(state, request.player), request))


# --- config readers and tapping -----------------------------------------------------------------


def test_103_4_starting_life_comes_from_the_function(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_function(monkeypatch, defaults, "starting_life", lambda state, player: 33 + player)
    state = initial_state(GameConfig.standard(), [Deck(())] * 2, 1)
    assert [p.life for p in state.players] == [33, 34]


def test_103_5_the_opening_hand_size_comes_from_the_function(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_function(monkeypatch, defaults, "starting_hand_size", lambda state, player: 3)
    state = new_game(GameConfig.standard(), decks(2), 1)
    submit(state, DecisionAnswer(request_of(state).id, request_of(state).player, Pick(0)))
    assert len(state.player(P0).hand) == len(state.player(P1).hand) == 3


def test_302_6_a_tap_cost_may_be_refused_by_the_function(monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = stocked()
    (forest,) = scenario.battlefield(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    mana = [o for o in priority_options(state) if isinstance(o, ActivateAbilityOption)]
    assert mana == [ActivateAbilityOption(forest, 0)]
    assert isinstance(characteristics(state, forest).abilities[0], ActivatedManaAbility)
    patch_function(monkeypatch, defaults, "can_tap_for_cost", lambda state, obj: False)
    scenario = stocked()
    scenario.battlefield(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    assert not any(isinstance(o, ActivateAbilityOption) for o in priority_options(state))
