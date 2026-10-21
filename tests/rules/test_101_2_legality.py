"""101.2: when a rule or effect allows and another prohibits, the prohibition wins.

``allowed(state, action)`` (design.md §17.2) collects the permissions for an action (the rules'
own, here 305.1 and 117.1a for playing a land), requires at least one, collects the
prohibitions, and lets any applicable prohibition win. 101.2a: adding or removing abilities is
not a prohibition. The actions so far are playing a land and casting a spell (601.3: a player
may begin to cast a spell only if a rule or effect allows it and none prohibits it).

Expected values are worked from the pinned CR:

- 305.1, 116.2a: a player may play a land from their hand during their main phase, with an
  empty stack. 305.2a-b: only while the number of lands they have played this turn is below the
  number they can play this turn.
- 101.2: "When a rule or effect allows or instructs a player to do something, and another rule
  or effect prohibits it, the prohibition takes precedence."
"""

from __future__ import annotations

import pytest

from resolve.agents.scripted import choose
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import CastSpellOption, ChooseOne, PlayLandOption
from resolve.rules import defaults, legality
from resolve.rules.legality import Action, CastAction, Permission, PlayLand, Prohibition
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.spell import COMMANDER, FROM_HAND, NORMAL
from resolve.state.turn import Phase, Step
from tests.game_fixtures import request_of
from tests.scenario import Scenario, run_script
from tests.seams import patch, patch_permissions

P0, P1 = PlayerId(0), PlayerId(1)


def main_with_forests() -> tuple[Scenario, ObjectId, ObjectId]:
    scenario = Scenario(2)
    first, second = scenario.hand(P0, ["Forest", "Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN, priority=P0)
    return scenario, first, second


def test_305_1_playing_a_land_from_the_hand_in_the_main_phase_is_allowed() -> None:
    scenario, forest, _ = main_with_forests()
    state = scenario.build()
    verdict = legality.allowed(state, PlayLand(P0, forest))
    assert verdict.allowed
    assert "305.1" in verdict.rules


def test_305_3_a_land_play_on_another_players_turn_has_no_permission() -> None:
    scenario = Scenario(2)
    (forest,) = scenario.hand(P1, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN, priority=P0)
    state = scenario.build()
    verdict = legality.allowed(state, PlayLand(P1, forest))
    assert not verdict.allowed and legality.permissions(state, PlayLand(P1, forest)) == ()


def test_117_1a_a_land_play_outside_a_main_phase_has_no_permission() -> None:
    scenario = Scenario(2)
    (forest,) = scenario.hand(P0, ["Forest"])
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    assert not legality.allowed(state, PlayLand(P0, forest)).allowed


def test_305_1_only_a_card_in_the_players_own_hand_may_be_played() -> None:
    scenario = Scenario(2)
    (theirs,) = scenario.hand(P1, ["Forest"])
    (graveyard,) = scenario.graveyard(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN, priority=P0)
    state = scenario.build()
    assert not legality.allowed(state, PlayLand(P0, theirs)).allowed
    assert not legality.allowed(state, PlayLand(P0, graveyard)).allowed


def test_305_2b_no_permission_once_the_lands_played_reach_the_allowed_number() -> None:
    scenario = Scenario(2)
    (forest,) = scenario.hand(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN, priority=P0, lands_played=1)
    state = scenario.build()
    verdict = legality.allowed(state, PlayLand(P0, forest))
    assert not verdict.allowed
    assert "305.2b" in verdict.rules


def test_101_2_a_prohibition_beats_a_permission(monkeypatch: pytest.MonkeyPatch) -> None:
    """The land play has its permissions (305.1), and a prohibition applies: the play is not
    allowed, the verdict cites 101.2 and the prohibition's own rule, and the land isn't offered
    at priority. The other land, which the prohibition doesn't name, still is."""
    scenario, forest, other = main_with_forests()

    def prohibit(state: GameState, action: Action) -> tuple[Prohibition, ...]:
        if isinstance(action, PlayLand) and action.card == forest:
            return (Prohibition("101.2", "this land can't be played"),)
        return ()

    monkeypatch.setattr(legality, "prohibitions", prohibit)
    state = scenario.build()
    assert legality.permissions(state, PlayLand(P0, forest))  # it has a permission
    verdict = legality.allowed(state, PlayLand(P0, forest))
    assert not verdict.allowed
    assert "101.2" in verdict.rules and "this land can't be played" in verdict.reason
    assert legality.allowed(state, PlayLand(P0, other)).allowed
    request = request_of(state)
    assert isinstance(request.space, ChooseOne)
    assert PlayLandOption(forest) not in request.space.options
    assert PlayLandOption(other) in request.space.options
    assert request.kind is DecisionKind.PRIORITY_ACTION


def test_101_2_an_extra_permission_doesnt_beat_the_limit_of_305_2b(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """305.2b says a player *can't* play a land once they've played all they can: a prohibition.
    An effect's permission to play the land doesn't override it (101.2); an effect that raises
    the number of lands they can play does lift it (305.2a)."""
    scenario = Scenario(2)
    (forest,) = scenario.hand(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN, priority=P0, lands_played=1)
    state = scenario.build()
    real = legality.permissions

    def grant(state: GameState, action: Action) -> tuple[Permission, ...]:
        return (*real(state, action), Permission("305.2", "an effect lets them play it"))

    monkeypatch.setattr(legality, "permissions", grant)
    verdict = legality.allowed(state, PlayLand(P0, forest))
    assert not verdict.allowed and verdict.rules[:2] == ("101.2", "305.2b")
    patch(monkeypatch, "land_plays_allowed", lambda state, player: 2)
    assert legality.allowed(state, PlayLand(P0, forest)).allowed


def test_101_2_an_effects_permission_alone_allows_the_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no rule of its own allowing it (the land is in the graveyard), a permission from an
    effect is enough; a prohibition on the same action still wins."""
    scenario = Scenario(2)
    (forest,) = scenario.graveyard(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN, priority=P0)
    state = scenario.build()
    assert not legality.allowed(state, PlayLand(P0, forest)).allowed

    def grant(state: GameState, action: Action) -> tuple[Permission, ...]:
        return (Permission("305.1", "play lands from the graveyard"),)

    monkeypatch.setattr(legality, "permissions", grant)
    assert legality.allowed(state, PlayLand(P0, forest)).allowed

    def forbid(state: GameState, action: Action) -> tuple[Prohibition, ...]:
        return (Prohibition("101.2", "never"),)

    monkeypatch.setattr(legality, "prohibitions", forbid)
    assert not legality.allowed(state, PlayLand(P0, forest)).allowed


def test_101_2_without_any_permission_a_missing_prohibition_isnt_enough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario, forest, _ = main_with_forests()
    patch_permissions(monkeypatch, lambda state, action: ())
    state = scenario.build()
    assert not legality.allowed(state, PlayLand(P0, forest)).allowed
    assert defaults.land_play_options(state, P0) == ()


def test_101_2_the_engine_plays_the_land_the_prohibition_leaves() -> None:
    scenario, forest, _ = main_with_forests()
    state = scenario.build()
    run_script(state, choose(PlayLandOption(forest), player=P0))
    assert state.turn is not None and state.turn.lands_played == 1


# --- Casting (601.3) --------------------------------------------------------------------------


def test_601_3_casting_from_the_hand_with_its_timing_is_allowed() -> None:
    scenario = Scenario(2)
    (bears,) = scenario.hand(P0, ["Grizzly Bears"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    verdict = legality.allowed(state, CastAction(P0, bears, NORMAL, FROM_HAND))
    assert verdict.allowed and verdict.rules == ("601.3",)
    # Another player's card, or this one under a permission for another zone: nothing allows it.
    assert not legality.allowed(state, CastAction(P1, bears, NORMAL, FROM_HAND)).allowed
    assert not legality.allowed(state, CastAction(P0, bears, NORMAL, COMMANDER)).allowed


def test_101_2_a_prohibition_on_casting_removes_that_spell_from_priority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A "can't cast" effect (Kutzil's Flanker-style, M5) forbids Grizzly Bears: it isn't
    offered; Hill Giant, which nothing forbids, still is."""
    scenario = Scenario(2)
    bears, giant = scenario.hand(P0, ["Grizzly Bears", "Hill Giant"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    original = legality.prohibitions

    def no_bears(state: GameState, action: Action) -> tuple[Prohibition, ...]:
        if isinstance(action, CastAction) and action.card == bears:
            return (Prohibition("101.2", "can't cast it"),)
        return original(state, action)

    monkeypatch.setattr(legality, "prohibitions", no_bears)
    state = scenario.build()
    space = request_of(state).space
    assert isinstance(space, ChooseOne)
    assert CastSpellOption(bears, NORMAL, FROM_HAND) not in space.options
    assert CastSpellOption(giant, NORMAL, FROM_HAND) in space.options
    verdict = legality.allowed(state, CastAction(P0, bears, NORMAL, FROM_HAND))
    assert not verdict.allowed and "101.2" in verdict.rules


def test_101_2_an_effects_permission_alone_allows_a_cast(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no permission from the rules (the upkeep: no sorcery timing), an effect's permission
    (patched in) is enough to offer Grizzly Bears."""
    scenario = Scenario(2)
    (bears,) = scenario.hand(P0, ["Grizzly Bears"])
    scenario.at(Step.UPKEEP, number=2)
    original = legality.permissions

    def granted(state: GameState, action: Action) -> tuple[Permission, ...]:
        if isinstance(action, CastAction) and action.card == bears:
            return (Permission("601.3", "a test effect"),)
        return original(state, action)

    patch_permissions(monkeypatch, granted)
    state = scenario.build()
    space = request_of(state).space
    assert isinstance(space, ChooseOne)
    assert CastSpellOption(bears, NORMAL, FROM_HAND) in space.options
