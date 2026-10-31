"""302.6: summoning sickness, for the {T} abilities of creatures (602.5a), and haste (702.10c).

From the pinned CR:

- 302.6: a creature's activated ability with {T} in its cost can't be activated unless the
  creature has been under its controller's control continuously since their most recent turn
  began. 602.5a says the same, and that haste ignores it: 702.10c, a creature with haste may
  activate its {T} abilities even if it hasn't been controlled continuously since its
  controller's most recent turn began. 702.10d: multiple instances are redundant.
- 605.3a: a mana ability may be activated whenever its controller has priority or is paying a
  cost, so the rule applies in both places.
- Only creatures are affected (302.6 is in the creature section): a land or a noncreature
  artifact taps the turn it enters (305.1, Sol Ring). A land that is also a creature (305.9) is a
  creature, so it is affected.
- 400.7: a permanent that entered this turn is a new object, which hasn't been under anyone's
  control since any turn began.

``defaults.summoning_sick(state, obj, TAP_ABILITY)`` is the one place this is decided (rule 12).
Its attack half (302.6, 702.10b, 508.1a) is tested with declaring attackers (M3.2).
"""

from __future__ import annotations

import pytest

from resolve.agents.scripted import choose
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import ActivateAbilityOption, PassOption, Pick, PlayLandOption
from resolve.engine.api import submit
from resolve.errors import InvalidAnswer
from resolve.events.spells import ActionReversed, PermanentSpellResolved
from resolve.rules import defaults
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import Mana, ManaType
from resolve.state.turn import Phase, Step
from resolve.state.zones import STACK
from tests.casting_support import (
    activate,
    activate_with_priority,
    answered,
    cast,
    options,
    pass_,
    pay,
    records,
)
from tests.game_fixtures import answer, request_of
from tests.scenario import Scenario, names, run_script
from tests.seams import patch_sickness

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)
G = ManaType.GREEN
TAP = defaults.SicknessPurpose.TAP_ABILITY


def offered(state: GameState, obj: ObjectId) -> bool:
    return ActivateAbilityOption(obj, 0) in options(state)


def test_302_6_a_creature_cant_tap_for_mana_the_turn_it_arrives() -> None:
    """P0 casts Llanowar Elves in their turn 1 main phase. Once it resolves its {T} ability is
    offered neither with priority nor while paying for Grizzly Bears (605.3a)."""
    scenario = Scenario(2)
    elves_card, bears = scenario.hand(P0, ["Llanowar Elves", "Grizzly Bears"])
    first, second, third = scenario.battlefield(P0, ["Forest", "Forest", "Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN, number=1)
    state = scenario.build()
    run_script(state, cast(elves_card, P0), activate(first), pay(), pass_(P0), pass_(P1))
    (resolved,) = records(state, PermanentSpellResolved)
    elves = resolved.permanent
    assert elves is not None and elves in state.battlefield
    assert state.objects[elves].entered_turn == 1
    assert defaults.summoning_sick(state, elves, TAP)
    assert not offered(state, elves)
    run_script(state, cast(bears, P0))
    request = request_of(state)
    assert request.kind is DecisionKind.ACTIVATE_MANA_ABILITIES
    assert ActivateAbilityOption(elves, 0) not in options(state)
    assert ActivateAbilityOption(second, 0) in options(state)
    assert ActivateAbilityOption(third, 0) in options(state)


def test_302_6_it_can_once_its_controllers_turn_has_begun() -> None:
    """Elves came under P0's control during P1's turn 2: not on that turn (P0's most recent turn,
    1, began before it arrived), but from P0's turn 3 on."""
    scenario = Scenario(2)
    (elves,) = scenario.battlefield(P0, ["Llanowar Elves"], entered_turn=2)
    scenario.library(P0, ["Forest"])  # P0 draws in turn 3
    scenario.at(Phase.PRECOMBAT_MAIN, active=P1, number=2, passed=[P1], priority=P0)
    state = scenario.build()
    assert state.player(P0).last_turn_began == 1
    assert request_of(state).player == P0
    assert options(state) == (PassOption(),)
    while not (
        state.turn is not None
        and state.turn.number == 3
        and request_of(state).kind is DecisionKind.PRIORITY_ACTION
        and request_of(state).player == P0
    ):
        assert not offered(state, elves)
        run_script(state, pass_())
    assert state.turn.step is Step.UPKEEP
    assert state.player(P0).last_turn_began == 3
    assert not defaults.summoning_sick(state, elves, TAP)
    run_script(state, activate_with_priority(elves))
    assert state.player(P0).mana_pool == [Mana(G, elves)]


def test_302_6_a_creature_under_its_controllers_control_since_before_their_turn_began_taps() -> (
    None
):
    """Entered during P0's turn 1 under P1's control: P1's turn 2 began after that, so P1 may tap
    it in turn 2; and during P0's turn 3, P1 still may (since P1's turn 2 began)."""
    scenario = Scenario(2)
    (elves,) = scenario.battlefield(P1, ["Llanowar Elves"], entered_turn=1)
    scenario.at(Phase.PRECOMBAT_MAIN, active=P1, number=2)
    state = scenario.build()
    assert offered(state, elves)

    scenario = Scenario(2)
    (elves,) = scenario.battlefield(P1, ["Llanowar Elves"], entered_turn=1)
    scenario.at(Phase.PRECOMBAT_MAIN, active=P0, number=3, passed=[P0], priority=P1)
    state = scenario.build()
    assert offered(state, elves)


def test_302_6_its_controllers_own_turn_counts_only_from_its_beginning() -> None:
    """Entered during P0's turn 3 (say in the upkeep): sick for the rest of turn 3, although P0's
    turn is in progress; their most recent turn began before it arrived."""
    scenario = Scenario(2)
    (elves,) = scenario.battlefield(P0, ["Llanowar Elves"], entered_turn=3)
    scenario.at(Phase.POSTCOMBAT_MAIN, number=3)
    state = scenario.build()
    assert defaults.summoning_sick(state, elves, TAP)
    assert not offered(state, elves)


def test_302_6_a_player_who_hasnt_had_a_turn_cant_tap_creatures() -> None:
    """Three players, P0 starts: in turn 1 P2 has had no turn yet, so even a creature they have
    controlled since before the game (``entered_turn`` 0) is sick; in turn 3 it isn't."""
    scenario = Scenario(3)
    (elves,) = scenario.battlefield(P2, ["Llanowar Elves"])
    scenario.at(Phase.PRECOMBAT_MAIN, number=1, passed=[P0, P1], priority=P2)
    state = scenario.build()
    assert state.player(P2).last_turn_began is None
    assert request_of(state).player == P2
    assert not offered(state, elves)

    scenario = Scenario(3)
    (elves,) = scenario.battlefield(P2, ["Llanowar Elves"], entered_turn=2)
    scenario.at(Phase.PRECOMBAT_MAIN, active=P2, number=3)
    state = scenario.build()
    assert offered(state, elves)


def test_302_6_lands_and_noncreature_artifacts_arent_affected() -> None:
    """A Forest and a Sol Ring that entered this turn tap at once; Test Land Creature (a Forest
    that is also a creature, 305.9) that entered this turn can't, but can if it was there before
    the turn began."""
    scenario = Scenario(2)
    forest, ring, dryad = scenario.battlefield(
        P0, ["Forest", "Sol Ring", "Test Land Creature"], entered_turn=2
    )
    (old_dryad,) = scenario.battlefield(P0, ["Test Land Creature"], entered_turn=1)
    scenario.at(Phase.PRECOMBAT_MAIN, number=2, last_turns={P0: 2})
    state = scenario.build()
    assert offered(state, forest)
    assert offered(state, ring)
    assert not offered(state, dryad)
    assert offered(state, old_dryad)
    assert not defaults.summoning_sick(state, forest, TAP) and not defaults.summoning_sick(
        state, ring, TAP
    )
    assert defaults.summoning_sick(state, dryad, TAP)


def test_302_6_a_land_played_this_turn_taps_but_a_land_creature_played_this_turn_doesnt() -> None:
    """Played lands are new objects that entered this turn (305.1, 400.7)."""
    scenario = Scenario(2)
    (dryad,) = scenario.hand(P0, ["Test Land Creature"])
    scenario.at(Phase.PRECOMBAT_MAIN, number=3)
    state = scenario.build()
    run_script(state, choose(PlayLandOption(dryad)))
    (played,) = state.battlefield
    assert state.objects[played].entered_turn == 3
    assert not offered(state, played)


def test_302_6_goes_through_summoning_sick(monkeypatch: pytest.MonkeyPatch) -> None:
    """Seam: with ``summoning_sick`` saying no (as Thousand-Year Elixir will, M5), a creature
    that arrived this turn offers its ability, with priority and while paying; saying yes hides
    even a Forest's."""
    scenario = Scenario(2)
    (bears,) = scenario.hand(P0, ["Grizzly Bears"])
    (elves,) = scenario.battlefield(P0, ["Llanowar Elves"], entered_turn=1)
    (forest,) = scenario.battlefield(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN, number=1)
    patch_sickness(monkeypatch, lambda state, obj, purpose: False)
    state = scenario.build()
    assert offered(state, elves)
    run_script(state, cast(bears, P0))
    assert ActivateAbilityOption(elves, 0) in options(state)
    run_script(state, activate(elves), activate(forest))
    assert state.objects[elves].tapped

    scenario = Scenario(2)
    (forest,) = scenario.battlefield(P0, ["Forest"])
    (lions,) = scenario.hand(P0, ["Savannah Lions"])
    scenario.at(Phase.PRECOMBAT_MAIN, number=1)
    patch_sickness(monkeypatch, lambda state, obj, purpose: True)
    state = scenario.build()
    assert not offered(state, forest)
    # Nor while paying: no mana ability is offered, so the cast is reversed at once.
    run_script(state, cast(lions, P0))
    assert answered(state, DecisionKind.ACTIVATE_MANA_ABILITIES) == 0
    assert len(records(state, ActionReversed)) == 1


def test_302_6_an_answer_activating_a_sick_creature_is_rejected() -> None:
    """The option isn't offered, so an index naming it is outside the space (117.1)."""
    scenario = Scenario(2)
    scenario.battlefield(P0, ["Llanowar Elves"], entered_turn=1)
    scenario.at(Phase.PRECOMBAT_MAIN, number=1)
    state = scenario.build()
    assert options(state) == (PassOption(),)
    with pytest.raises(InvalidAnswer):
        submit(state, answer(state, Pick(1)))


@pytest.mark.parametrize("name", ["Avacyn's Pilgrim", "Ixalli's Lorekeeper"])
def test_302_6_every_mana_creature_has_summoning_sickness(name: str) -> None:
    scenario = Scenario(2)
    (new,) = scenario.battlefield(P0, [name], entered_turn=1)
    (old,) = scenario.battlefield(P0, [name])
    scenario.at(Phase.PRECOMBAT_MAIN, number=1)
    state = scenario.build()
    assert not offered(state, new)
    assert offered(state, old)


def test_302_6_a_creature_with_haste_can_pay_its_tap_cost_the_turn_it_arrives() -> None:
    """702.10c: Test Hasty Elves (Haste; {T}: Add {G}) came under P0's control this turn, yet
    its {T} ability is offered with priority and while paying, and adds {G}."""
    scenario = Scenario(2)
    (hasty,) = scenario.battlefield(P0, ["Test Hasty Elves"], entered_turn=3)
    (bears,) = scenario.hand(P0, ["Grizzly Bears"])
    (forest,) = scenario.battlefield(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN, number=3)
    state = scenario.build()
    assert not defaults.summoning_sick(state, hasty, TAP)
    assert offered(state, hasty)
    run_script(state, cast(bears, P0))
    assert ActivateAbilityOption(hasty, 0) in options(state)
    run_script(state, activate(hasty), activate(forest))
    assert state.objects[hasty].tapped
    assert names(state, STACK) == ["Grizzly Bears"]  # paid with the hasty Elves' {G}


def test_302_6_without_haste_it_cant() -> None:
    """The same board with Llanowar Elves (no haste): its ability isn't offered (302.6)."""
    scenario = Scenario(2)
    (elves,) = scenario.battlefield(P0, ["Llanowar Elves"], entered_turn=3)
    scenario.at(Phase.PRECOMBAT_MAIN, number=3)
    state = scenario.build()
    assert defaults.summoning_sick(state, elves, TAP)
    assert not offered(state, elves)


def test_702_10c_haste_works_on_another_players_turn_and_for_a_player_who_hasnt_had_a_turn() -> (
    None
):
    """Three players, turn 1: P2 hasn't had a turn (``last_turn_began`` is ``None``), so Llanowar
    Elves is sick, but Test Hasty Elves taps for mana while P2 holds priority."""
    scenario = Scenario(3)
    (elves, hasty) = scenario.battlefield(P2, ["Llanowar Elves", "Test Hasty Elves"])
    scenario.at(Phase.PRECOMBAT_MAIN, number=1, passed=[P0, P1], priority=P2)
    state = scenario.build()
    assert not offered(state, elves)
    assert offered(state, hasty)
    run_script(state, activate_with_priority(hasty))
    assert state.player(P2).mana_pool == [Mana(G, hasty)]


def test_702_10d_two_instances_of_haste_are_one() -> None:
    """Test Twice Hasty Elves (Haste, Haste; {T}: Add {G}) behaves exactly as with one."""
    scenario = Scenario(2)
    (hasty,) = scenario.battlefield(P0, ["Test Twice Hasty Elves"], entered_turn=1)
    scenario.at(Phase.PRECOMBAT_MAIN, number=1)
    state = scenario.build()
    assert not defaults.summoning_sick(state, hasty, TAP)
    assert offered(state, hasty)


def test_702_10_haste_doesnt_let_a_tapped_creature_tap() -> None:
    """Haste lifts only 302.6; an already tapped creature still can't pay {T} (118.3)."""
    scenario = Scenario(2)
    (hasty,) = scenario.battlefield(P0, ["Test Hasty Elves"], entered_turn=1)
    scenario.tap(hasty)
    scenario.at(Phase.PRECOMBAT_MAIN, number=1)
    state = scenario.build()
    assert not offered(state, hasty)
