"""Enchantment spells (303.1-303.2), with Test Totem ({1}, Enchantment, no abilities).

From the pinned CR:

- 303.1: "A player who has priority may cast an enchantment card from their hand during a main
  phase of their turn when the stack is empty."
- 303.2: "When an enchantment spell resolves, its controller puts it onto the battlefield under
  their control."

Auras (303.4) are M4.
"""

from __future__ import annotations

from resolve.decisions.spaces import CastSpellOption
from resolve.events.spells import PermanentSpellResolved
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.turn import Phase, Step
from resolve.state.zones import BATTLEFIELD
from tests.casting_support import activate, cast, options, pass_, records
from tests.scenario import Scenario, names, run_script

P0, P1 = PlayerId(0), PlayerId(1)


def offered(state_options: tuple[object, ...], obj: ObjectId) -> bool:
    return any(isinstance(o, CastSpellOption) and o.object == obj for o in state_options)


def test_303_1_an_enchantment_is_cast_in_its_owners_main_phase_with_an_empty_stack() -> None:
    scenario = Scenario(2)
    (totem,) = scenario.hand(P0, ["Test Totem"])
    scenario.battlefield(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    assert offered(options(scenario.build()), totem)


def test_303_1_not_during_another_players_turn() -> None:
    """In P1's main phase, P0 gets priority after P1 passes: the Totem isn't offered."""
    scenario = Scenario(2)
    (totem,) = scenario.hand(P0, ["Test Totem"])
    scenario.battlefield(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN, active=P1)
    state = scenario.build()
    run_script(state, pass_(P1))
    assert not offered(options(state), totem)


def test_303_1_not_while_the_stack_isnt_empty() -> None:
    """P0's own main phase, with P1's Grizzly Bears on the stack: the Totem isn't offered."""
    scenario = Scenario(2)
    (totem,) = scenario.hand(P0, ["Test Totem"])
    scenario.battlefield(P0, ["Forest"])
    scenario.stack(P1, ["Grizzly Bears"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    assert not offered(options(scenario.build()), totem)


def test_303_1_not_in_its_owners_upkeep() -> None:
    """P0's own turn, but the upkeep (503) isn't a main phase: the Totem isn't offered."""
    scenario = Scenario(2)
    (totem,) = scenario.hand(P0, ["Test Totem"])
    scenario.battlefield(P0, ["Forest"])
    scenario.at(Step.UPKEEP)
    assert not offered(options(scenario.build()), totem)


def test_303_1_only_from_the_hand() -> None:
    """A Test Totem in P0's graveyard isn't offered in P0's main phase ("from their hand")."""
    scenario = Scenario(2)
    (totem,) = scenario.graveyard(P0, ["Test Totem"])
    scenario.battlefield(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    assert not offered(options(scenario.build()), totem)


def test_303_2_its_controller_not_the_active_player_gets_it() -> None:
    """P1's Test Totem on the stack during P0's main phase: both pass, and it enters under P1's
    control (its controller), not P0's (the active player)."""
    scenario = Scenario(2)
    scenario.stack(P1, ["Test Totem"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1))
    (permanent,) = [obj for obj in state.objects.values() if obj.zone == BATTLEFIELD]
    assert state.card_of(permanent).data.name == "Test Totem"
    assert permanent.controller == P1


def test_303_2_a_resolved_enchantment_enters_the_battlefield_under_its_controller() -> None:
    """P0 casts the Totem, both players pass, and it resolves onto the battlefield under P0's
    control."""
    scenario = Scenario(2)
    (totem,) = scenario.hand(P0, ["Test Totem"])
    (forest,) = scenario.battlefield(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(totem), activate(forest), pass_(P0), pass_(P1))
    assert len(records(state, PermanentSpellResolved)) == 1
    assert "Test Totem" in names(state, BATTLEFIELD)
    (permanent,) = [
        obj
        for obj in state.objects.values()
        if obj.zone == BATTLEFIELD and state.card_of(obj).data.name == "Test Totem"
    ]
    assert permanent.controller == P0
