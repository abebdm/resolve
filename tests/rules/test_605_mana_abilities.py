"""605: mana abilities, 106: mana and mana pools, and 502.3: untapping.

From the pinned CR:

- 605.3a, 117.1d: a player may activate a mana ability whenever they have priority, on any
  player's turn and in any step that gives priority. 602.2: only the object's controller.
- 605.3b: a mana ability doesn't use the stack; it resolves immediately. 117.3c: the player
  receives priority again. 117.4: it is an action, so earlier passes stop counting.
- 107.5, 118.3, 701.26a: {T} taps the permanent; a tapped permanent can't pay it.
- 106.3, 106.4: the mana goes into the controller's mana pool; 106.4b, 117.3d: a player who
  passes with mana in their pool announces it.
- 500.5, 703.4q: as each step and phase ends, unspent mana empties from every pool.
- 502.3: in the untap step the active player untaps their permanents, all at once; other
  players' permanents stay tapped.
- 302.6: a creature's {T} ability needs the creature to have been controlled since the turn
  began; that isn't tracked yet, so it is a gap.
"""

from __future__ import annotations

import copy

import pytest

from resolve.agents.scripted import Choose, choose
from resolve.cards.primitives.abilities import ActivatedManaAbility
from resolve.cards.primitives.costs import TapSelfCost
from resolve.cards.primitives.effects import AddMana
from resolve.cards.registry import CardDefinition, CardRegistry
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.request import DecisionAnswer
from resolve.decisions.spaces import ActivateAbilityOption, ChooseOne, Option, PassOption, Pick
from resolve.engine.api import submit
from resolve.errors import InvalidAnswer, NotImplementedRule
from resolve.events.mana import ManaAdded, ManaPoolEmptied
from resolve.events.permanents import PermanentsUntapped, PermanentTapped
from resolve.events.turn import PriorityPassed
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import Mana, ManaType
from resolve.state.turn import Phase, Step
from tests.game_fixtures import request_of, scenario_registry
from tests.scenario import Scenario, run_script

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)
G = ManaType.GREEN


def options(state: GameState) -> tuple[Option, ...]:
    request = request_of(state)
    assert request.kind is DecisionKind.PRIORITY_ACTION
    assert isinstance(request.space, ChooseOne)
    return request.space.options


def pass_(player: PlayerId) -> Choose:
    return choose(PassOption(), player=player, kind=DecisionKind.PRIORITY_ACTION)


def tap(obj: ObjectId, player: PlayerId) -> Choose:
    return choose(ActivateAbilityOption(obj, 0), player=player)


def events[T](state: GameState, kind: type[T]) -> list[T]:
    return [entry.record for entry in state.event_log if isinstance(entry.record, kind)]


def test_605_3a_any_player_with_priority_may_activate_a_mana_ability() -> None:
    """The nonactive player taps their Forest in the active player's upkeep."""
    scenario = Scenario(2)
    (forest,) = scenario.battlefield(P1, ["Forest"])
    scenario.at(Step.UPKEEP, priority=P1, passed=[P0])
    state = scenario.build()
    assert options(state) == (PassOption(), ActivateAbilityOption(forest, 0))
    run_script(state, tap(forest, P1))
    assert state.player(P1).mana_pool == [Mana(G, forest)]
    assert state.objects[forest].tapped
    assert state.stack == []  # 605.3b
    request = request_of(state)
    assert request.player == P1  # 117.3c
    turn = state.turn
    assert turn is not None and turn.passed == []  # 117.4: player 0's pass no longer counts
    (tapped,) = events(state, PermanentTapped)
    (added,) = events(state, ManaAdded)
    assert tapped.obj == forest and added.mana == (Mana(G, forest),) and added.player == P1
    log = [type(e.record) for e in state.event_log]
    # 602.2b, 601.2h: the cost is paid; then 605.3b: the ability resolves.
    assert log.index(PermanentTapped) < log.index(ManaAdded)


def test_602_2_only_the_controller_may_activate() -> None:
    scenario = Scenario(2)
    scenario.battlefield(P1, ["Forest"])
    scenario.battlefield(P0, ["Forest"], owner=P1)  # controlled by player 0, owned by 1
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    (controlled,) = [o for o in state.battlefield if state.objects[o].controller == P0]
    assert options(state) == (PassOption(), ActivateAbilityOption(controlled, 0))


def test_118_3_a_tapped_land_cant_be_tapped_for_mana() -> None:
    scenario = Scenario(2)
    tapped, untapped = scenario.battlefield(P0, ["Forest", "Forest"])
    scenario.tap(tapped)
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    assert options(state) == (PassOption(), ActivateAbilityOption(untapped, 0))
    run_script(state, tap(untapped, P0))
    assert options(state) == (PassOption(),)


def test_117_4_an_action_resets_passing_in_succession() -> None:
    """Player 0 passes, player 1 taps a land and passes: player 0 receives priority again, and
    the step ends only when player 0 passes once more."""
    scenario = Scenario(2)
    (forest,) = scenario.battlefield(P1, ["Forest"])
    scenario.library(P0, ["Forest"])
    scenario.at(Step.UPKEEP, number=3)  # not turn 1, so the draw step isn't skipped (103.8a)
    state = scenario.build()
    run_script(state, pass_(P0), tap(forest, P1), pass_(P1))
    turn = state.turn
    assert turn is not None and turn.step is Step.UPKEEP
    assert request_of(state).player == P0
    run_script(state, pass_(P0))
    assert turn.step is Step.DRAW


def test_500_5_703_4q_unspent_mana_empties_as_the_step_ends() -> None:
    scenario = Scenario(2)
    (forest,) = scenario.battlefield(P0, ["Forest"])
    scenario.library(P0, ["Forest"])
    scenario.at(Step.UPKEEP, number=3)
    state = scenario.build()
    run_script(state, tap(forest, P0), pass_(P0))
    assert state.player(P0).mana_pool == [Mana(G, forest)]  # still there while in the upkeep
    run_script(state, pass_(P1))
    turn = state.turn
    assert turn is not None and turn.step is Step.DRAW
    assert state.player(P0).mana_pool == []
    (emptied,) = events(state, ManaPoolEmptied)
    assert emptied.player == P0 and emptied.mana == (Mana(G, forest),)
    assert emptied.rules[:2] == ("500.5", "703.4q")
    assert state.objects[forest].tapped  # only the mana empties; the land stays tapped


def test_500_5_mana_empties_when_a_main_phase_ends_too() -> None:
    scenario = Scenario(3)
    (mine,) = scenario.battlefield(P0, ["Forest"])
    (theirs,) = scenario.battlefield(P2, ["Mountain"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, tap(mine, P0), pass_(P0), pass_(P1), tap(theirs, P2), pass_(P2))
    turn = state.turn
    assert turn is not None and turn.phase is Phase.PRECOMBAT_MAIN  # player 2 acted last
    run_script(state, pass_(P0), pass_(P1))
    assert turn.step is Step.BEGINNING_OF_COMBAT
    assert all(player.mana_pool == [] for player in state.players)
    emptied = events(state, ManaPoolEmptied)
    assert [(e.player, e.mana) for e in emptied] == [
        (P0, (Mana(G, mine),)),
        (P2, (Mana(ManaType.RED, theirs),)),
    ]


def test_500_5_an_empty_pool_logs_no_emptying() -> None:
    scenario = Scenario(2)
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1))
    assert events(state, ManaPoolEmptied) == []


def test_106_4b_117_3d_passing_announces_unspent_mana() -> None:
    scenario = Scenario(2)
    forest, other = scenario.battlefield(P0, ["Forest", "Forest"])
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    run_script(state, tap(forest, P0), tap(other, P0), pass_(P0), pass_(P1))
    first, second = events(state, PriorityPassed)
    assert first.mana_in_pool == (Mana(G, forest), Mana(G, other))
    assert "106.4b" in first.rules
    assert second.mana_in_pool == ()


def test_502_3_the_active_player_untaps_their_permanents_only() -> None:
    scenario = Scenario(2)
    mine = scenario.battlefield(P1, ["Forest", "Forest", "Mountain"])
    theirs = scenario.battlefield(P0, ["Forest"])
    scenario.tap(*mine[:2], *theirs)
    scenario.library(P1, ["Forest"])
    scenario.at(Step.UNTAP, active=P1, number=2)
    state = scenario.build()
    assert not any(state.objects[obj].tapped for obj in mine)
    assert state.objects[theirs[0]].tapped
    (untapped,) = events(state, PermanentsUntapped)  # one event: all at once
    assert untapped.objs == tuple(mine[:2])
    assert untapped.rules[0] == "502.3"


def test_502_3_nothing_tapped_logs_no_untap() -> None:
    scenario = Scenario(2)
    scenario.battlefield(P0, ["Forest"])
    scenario.at(Step.UNTAP, number=3)
    scenario.library(P0, ["Forest"])
    state = scenario.build()
    assert events(state, PermanentsUntapped) == []


def test_302_6_a_creatures_tap_ability_is_a_gap() -> None:
    elf = CardDefinition(
        "Llanowar Elves",
        (ActivatedManaAbility((TapSelfCost(),), AddMana((G,))),),
    )
    registry = CardRegistry([elf, *(scenario_registry().get(n) for n in ("Forest",))])
    scenario = Scenario(2, registry=registry)
    scenario.battlefield(P0, ["Llanowar Elves"])
    scenario.at(Step.UPKEEP)
    with pytest.raises(NotImplementedRule) as gap:
        scenario.build()
    assert gap.value.rule == "302.6"


def test_activating_an_ability_that_cant_be_activated_is_rejected() -> None:
    """The option list is the space: a tapped land's ability isn't offered (118.3)."""
    scenario = Scenario(2)
    (forest,) = scenario.battlefield(P0, ["Forest"])
    scenario.tap(forest)
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    request = request_of(state)
    before = copy.deepcopy(state)
    with pytest.raises(InvalidAnswer):
        submit(state, DecisionAnswer(request.id, P0, Pick(1)))
    assert state == before
