"""305: playing lands, and 305.6: the mana abilities of basic land types.

From the pinned CR:

- 305.1, 116.2a, 505.6b: a player with priority may play a land card from their hand during a
  main phase of their turn when the stack is empty. It is a special action: it doesn't use the
  stack, and the player receives priority again afterward (117.3c).
- 305.2, 305.2a: by default a player may play one land per turn; 305.3: never on another
  player's turn.
- 110.5b: the land enters the battlefield untapped; 400.7: as a new object; 305.1: under the
  control of the player who played it.
- 117.4: playing a land is an action, so passes before it don't count toward ending the step.
- 305.6: a land with a basic land type has "{T}: Add [mana symbol]" whatever its text box says;
  305.8: without the basic supertype it is still nonbasic.
"""

from __future__ import annotations

import pytest

from resolve.agents.scripted import Choose, choose
from resolve.cards.primitives.abilities import ActivatedManaAbility
from resolve.cards.primitives.costs import TapSelfCost
from resolve.cards.primitives.effects import AddMana
from resolve.data.types import Supertype
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import (
    ActivateAbilityOption,
    ChooseOne,
    Option,
    PassOption,
    PlayLandOption,
)
from resolve.effects.characteristics import characteristics
from resolve.errors import NotImplementedRule
from resolve.events.permanents import LandPlayed
from resolve.state.game import GameState
from resolve.state.ids import PlayerId
from resolve.state.mana import Mana, ManaType
from resolve.state.turn import Phase, Step
from resolve.state.zones import BATTLEFIELD, Zone
from tests.game_fixtures import pass_until, request_of
from tests.scenario import Scenario, names, run_script

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)


def options(state: GameState) -> tuple[Option, ...]:
    request = request_of(state)
    assert request.kind is DecisionKind.PRIORITY_ACTION
    assert isinstance(request.space, ChooseOne)
    return request.space.options


def pass_(player: PlayerId) -> Choose:
    return choose(PassOption(), player=player, kind=DecisionKind.PRIORITY_ACTION)


def test_305_1_the_active_player_plays_a_land_in_their_main_phase() -> None:
    scenario = Scenario(2)
    (forest,) = scenario.hand(P0, ["Forest"])
    forest_card = scenario.card_of(forest)
    scenario.at(Phase.PRECOMBAT_MAIN, priority=P0, passed=[P1])
    state = scenario.build()
    assert PlayLandOption(forest) in options(state)
    run_script(state, choose(PlayLandOption(forest), player=P0))
    (played,) = state.battlefield
    obj = state.objects[played]
    assert played != forest and obj.card == forest_card  # 400.7
    assert forest not in state.objects  # the hand object is gone
    assert obj.controller == P0 and not obj.tapped  # 305.1, 110.5b
    assert state.player(P0).hand == [] and state.stack == []
    turn = state.turn
    assert turn is not None and turn.lands_played == 1
    # 116.2a / 117.3c: the same player receives priority again, with no pass in between,
    # and the earlier pass by player 1 no longer counts (117.4).
    request = request_of(state)
    assert request.player == P0 and request.kind is DecisionKind.PRIORITY_ACTION
    assert turn.passed == []
    (entry,) = [e for e in state.event_log if isinstance(e.record, LandPlayed)]
    assert entry.visible_to is None  # public
    assert entry.record.rules[:2] == ("305.1", "116.2a")
    run_script(state, pass_(P0))
    assert (turn.phase, turn.step) == (Phase.PRECOMBAT_MAIN, None)  # player 1 must pass again
    run_script(state, pass_(P1))
    assert (turn.phase, turn.step) == (Phase.COMBAT, Step.BEGINNING_OF_COMBAT)


def test_305_2_one_land_per_turn_and_another_on_the_next_turn() -> None:
    scenario = Scenario(2)
    first, second, third = scenario.hand(P0, ["Forest", "Forest", "Forest"])
    for player in scenario.players:
        scenario.library(player, ["Forest"] * 3)
    scenario.at(Phase.PRECOMBAT_MAIN, number=3)
    state = scenario.build()
    run_script(state, choose(PlayLandOption(first)))
    assert not any(isinstance(o, PlayLandOption) for o in options(state))
    # Through combat to the postcombat main phase: still no second land.
    pass_until(state, lambda s: s.turn is not None and s.turn.phase is Phase.POSTCOMBAT_MAIN)
    assert request_of(state).player == P0
    assert not any(isinstance(o, PlayLandOption) for o in options(state))
    # Player 0's next turn (turn 5): a land may be played again.
    pass_until(
        state,
        lambda s: s.turn is not None and (s.turn.number, s.turn.phase) == (5, Phase.PRECOMBAT_MAIN),
    )
    assert PlayLandOption(second) in options(state) and PlayLandOption(third) in options(state)


def test_305_2a_lands_played_counts_toward_the_limit_set_by_the_scenario() -> None:
    scenario = Scenario(2)
    scenario.hand(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN, lands_played=1)
    state = scenario.build()
    assert options(state) == (PassOption(),)


@pytest.mark.parametrize("player", [P1, P2])
def test_305_3_no_land_on_another_players_turn(player: PlayerId) -> None:
    scenario = Scenario(3)
    scenario.hand(player, ["Forest"])
    passed = [P0] if player == P1 else [P0, P1]
    scenario.at(Phase.PRECOMBAT_MAIN, priority=player, passed=passed)
    state = scenario.build()
    assert request_of(state).player == player
    assert options(state) == (PassOption(),)


@pytest.mark.parametrize(
    "where",
    [Step.UPKEEP, Step.DRAW, Step.BEGINNING_OF_COMBAT, Step.DECLARE_ATTACKERS, Step.END],
)
def test_116_2a_no_land_outside_the_main_phases(where: Step) -> None:
    scenario = Scenario(2)
    scenario.hand(P0, ["Forest"])
    scenario.at(where)
    state = scenario.build()
    assert options(state) == (PassOption(),)


def test_305_1_no_land_with_an_object_on_the_stack() -> None:
    scenario = Scenario(2)
    scenario.hand(P0, ["Forest"])
    scenario.stack(P1, ["Test Shock"])
    scenario.at(Phase.POSTCOMBAT_MAIN)
    state = scenario.build()
    assert options(state) == (PassOption(),)


def test_305_6_each_basic_land_type_has_its_mana_ability() -> None:
    scenario = Scenario(2)
    lands = scenario.battlefield(P0, ["Plains", "Island", "Swamp", "Mountain", "Forest"])
    state = scenario.build()
    expected = [ManaType.WHITE, ManaType.BLUE, ManaType.BLACK, ManaType.RED, ManaType.GREEN]
    for land, mana in zip(lands, expected, strict=True):
        (ability,) = characteristics(state, land).abilities
        assert ability == ActivatedManaAbility((TapSelfCost(),), AddMana((mana,)))
        assert ability.text == "{T}: Add {" + mana.value + "}."


@pytest.mark.parametrize(
    ("land", "mana"),
    [
        ("Plains", ManaType.WHITE),
        ("Island", ManaType.BLUE),
        ("Swamp", ManaType.BLACK),
        ("Mountain", ManaType.RED),
        ("Forest", ManaType.GREEN),
    ],
)
def test_305_6_each_basic_land_type_taps_for_its_color(land: str, mana: ManaType) -> None:
    scenario = Scenario(2)
    (obj,) = scenario.battlefield(P0, [land])
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    run_script(state, choose(ActivateAbilityOption(obj, 0), player=P0))
    assert state.player(P0).mana_pool == [Mana(mana, obj)]
    assert state.objects[obj].tapped


def test_305_6_the_ability_comes_from_the_land_type_not_the_text() -> None:
    """A land with a basic land type and an empty text box still taps for mana (305.6), and
    without the basic supertype it is nonbasic (305.8)."""
    scenario = Scenario(2)
    (land,) = scenario.battlefield(P0, ["Test Nonbasic Forest"])
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    chars = characteristics(state, land)
    assert Supertype.BASIC not in chars.supertypes
    assert len(chars.abilities) == 1
    run_script(state, choose(ActivateAbilityOption(land, 0)))
    assert state.player(P0).mana_pool == [Mana(ManaType.GREEN, land)]


def test_305_6_a_basic_land_type_outside_the_battlefield_has_the_ability_but_cant_use_it() -> None:
    """The ability is intrinsic to the object (305.6), but {T} needs a permanent (107.5, 110.5d),
    so a Forest in hand offers no activation."""
    scenario = Scenario(2)
    (forest,) = scenario.hand(P0, ["Forest"])
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    assert len(characteristics(state, forest).abilities) == 1
    assert options(state) == (PassOption(),)


def test_305_1_a_played_land_can_tap_for_mana_at_once() -> None:
    """A land has no summoning sickness (302.6 is about creatures)."""
    scenario = Scenario(2)
    (forest,) = scenario.hand(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, choose(PlayLandOption(forest)))
    (played,) = state.battlefield
    assert ActivateAbilityOption(played, 0) in options(state)
    assert names(state, BATTLEFIELD) == ["Forest"]
    assert names(state, Zone.hand(P0)) == []


def test_305_1_a_land_may_be_played_in_the_postcombat_main_phase() -> None:
    scenario = Scenario(2)
    (forest,) = scenario.hand(P0, ["Forest"])
    scenario.at(Phase.POSTCOMBAT_MAIN)
    state = scenario.build()
    assert options(state) == (PassOption(), PlayLandOption(forest))
    run_script(state, choose(PlayLandOption(forest)))
    assert names(state, BATTLEFIELD) == ["Forest"]
    assert state.turn is not None and state.turn.lands_played == 1


def test_305_9_a_land_that_is_also_a_creature_is_played_never_cast() -> None:
    scenario = Scenario(2)
    (card,) = scenario.hand(P0, ["Test Land Creature"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    assert options(state) == (PassOption(), PlayLandOption(card))
    scenario = Scenario(2)
    scenario.hand(P0, ["Test Land Creature"])
    scenario.at(Step.UPKEEP)
    assert options(scenario.build()) == (PassOption(),)


def test_302_6_a_land_creatures_mana_ability_is_a_gap() -> None:
    """On the battlefield its {T} ability is a creature's (302.6), which isn't tracked yet."""
    scenario = Scenario(2)
    scenario.battlefield(P0, ["Test Land Creature"])
    scenario.at(Step.UPKEEP)
    with pytest.raises(NotImplementedRule) as gap:
        scenario.build()
    assert gap.value.rule == "302.6"


def test_305_6_two_basic_land_types_give_one_ability_each_in_type_line_order() -> None:
    scenario = Scenario(2)
    (dual,) = scenario.battlefield(P0, ["Test Dual"])
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    assert [a.text for a in characteristics(state, dual).abilities] == [
        "{T}: Add {G}.",
        "{T}: Add {U}.",
    ]
    assert options(state) == (
        PassOption(),
        ActivateAbilityOption(dual, 0),
        ActivateAbilityOption(dual, 1),
    )
    run_script(state, choose(ActivateAbilityOption(dual, 1)))
    assert state.player(P0).mana_pool == [Mana(ManaType.BLUE, dual)]
    assert options(state) == (PassOption(),)  # 118.3: both share the one {T}
