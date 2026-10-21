"""``allowed``: the one legality check (101.2, design.md §17.2), with land plays first.

From the pinned CR:

- 101.2: when a rule or effect allows or instructs something and another prohibits it, the
  prohibition wins. 101.2a: adding or removing abilities is not a prohibition.
- 305.1, 116.2a: a player may play a land from their hand during a main phase of their turn
  when the stack is empty. 305.3: never on another player's turn.
- 305.2a-b: a player can't play a land if the number of lands they can play this turn is equal
  to or less than the number they've played; this is a prohibition, so it beats any permission.
- 305.9: a land can't be cast.
"""

# Lambdas that replace engine functions take their parameter types from the function.
# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false

from __future__ import annotations

import pytest

from resolve.decisions.spaces import PlayLandOption
from resolve.engine import defaults, legality
from resolve.engine.legality import Ground, PlayLandAction, Verdict, allowed
from resolve.errors import EngineError
from resolve.state.ids import PlayerId
from resolve.state.turn import Phase, Step
from tests.game_fixtures import patch_function, request_of
from tests.scenario import Scenario

P0, P1 = PlayerId(0), PlayerId(1)


def test_305_1_a_land_in_the_hand_may_be_played_in_the_own_main_phase() -> None:
    scenario = Scenario(2)
    (forest,) = scenario.hand(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    verdict = allowed(state, PlayLandAction(P0, forest))
    assert verdict.ok
    assert verdict.rules == ("305.1", "116.2a")
    assert verdict.reasons != ()


def test_305_3_a_land_may_not_be_played_on_another_players_turn() -> None:
    scenario = Scenario(2)
    (forest,) = scenario.hand(P1, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    verdict = allowed(state, PlayLandAction(P1, forest))
    assert not verdict.ok and verdict.rules == ()
    assert verdict.reasons == ("no rule or effect lets the player play this land now",)


def test_305_1_a_land_may_not_be_played_with_a_spell_on_the_stack() -> None:
    scenario = Scenario(2)
    (forest,) = scenario.hand(P0, ["Forest"])
    scenario.stack(P1, ["Test Shock"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    assert not allowed(scenario.build(), PlayLandAction(P0, forest)).ok


def test_305_1_a_land_may_not_be_played_from_the_graveyard_by_default() -> None:
    scenario = Scenario(2)
    (forest,) = scenario.graveyard(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    assert not allowed(scenario.build(), PlayLandAction(P0, forest)).ok


def test_305_2_b_the_land_limit_is_a_prohibition_citing_its_rule() -> None:
    scenario = Scenario(2)
    (forest,) = scenario.hand(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN, lands_played=1)
    verdict = allowed(scenario.build(), PlayLandAction(P0, forest))
    assert not verdict.ok
    assert verdict.rules == ("305.2b",)


def test_305_2_b_the_limit_beats_a_permission_to_play_from_elsewhere(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = Scenario(2)
    (forest,) = scenario.graveyard(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN, lands_played=1)
    state = scenario.build()
    patch_function(monkeypatch, defaults, "land_play_options", lambda state, player: (forest,))
    verdict = allowed(state, PlayLandAction(P0, forest))
    assert not verdict.ok and "305.2b" in verdict.rules


def test_101_2_a_prohibition_beats_a_permission(monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = Scenario(2)
    (forest,) = scenario.hand(P0, ["Forest"])
    scenario.library(P0, ["Forest"] * 3)
    scenario.library(P1, ["Forest"] * 3)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    assert allowed(state, PlayLandAction(P0, forest)).ok
    ban = Ground(("101.2",), "an effect says this player can't play lands")
    patch_function(monkeypatch, legality, "prohibitions", lambda state, action: (ban,))
    verdict = allowed(state, PlayLandAction(P0, forest))
    assert verdict == Verdict(False, (ban.reason,), ("101.2",))


def test_101_2_the_engine_offers_no_land_a_prohibition_forbids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ban = Ground(("101.2",), "an effect says this player can't play lands")
    patch_function(monkeypatch, legality, "prohibitions", lambda state, action: (ban,))
    scenario = Scenario(2)
    scenario.hand(P0, ["Forest"])
    scenario.library(P0, ["Forest"] * 3)
    scenario.library(P1, ["Forest"] * 3)
    scenario.at(Phase.PRECOMBAT_MAIN)
    request = request_of(scenario.build())
    options = getattr(request.space, "options", ())
    assert not any(isinstance(o, PlayLandOption) for o in options)


def test_101_2_all_prohibitions_are_reported() -> None:
    scenario = Scenario(2)
    (forest,) = scenario.hand(P0, ["Forest"])
    scenario.at(Step.UPKEEP, lands_played=1)
    verdict = allowed(scenario.build(), PlayLandAction(P0, forest))
    assert not verdict.ok and verdict.rules == ("305.2b",)  # and no permission either


def test_an_action_that_is_not_a_legality_question_is_an_error() -> None:
    state = Scenario(2).build()
    with pytest.raises(EngineError, match="legality"):
        allowed(state, object())  # pyright: ignore[reportArgumentType]
