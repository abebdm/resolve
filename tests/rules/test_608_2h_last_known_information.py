"""608.2h and 113.7a: last known information.

From the pinned CR: an effect that needs information about an object uses its current information
if it is in the public zone it was expected to be in; if it has left that zone, the effect uses
its last known information. The engine records it (``GameState.last_known``) as an object leaves
the battlefield or the stack, and forgets it when a player is about to receive priority with an
empty stack, when nothing still resolving can ask for it (design.md §17.9).
"""

from __future__ import annotations

from resolve.effects.evaluation import information
from resolve.state.game import move_object
from resolve.state.ids import PlayerId
from resolve.state.spell import TargetPlayer
from resolve.state.turn import Phase
from resolve.state.zones import EXILE, Zone
from tests.casting_support import pass_
from tests.scenario import Scenario, run_script

P0, P1 = PlayerId(0), PlayerId(1)


def test_608_2h_a_permanent_leaving_records_its_last_known_information() -> None:
    """P1 controls Hill Giant (owned by P0), tapped, with 2 damage: all of that is recorded as it
    leaves the battlefield."""
    scenario = Scenario(2)
    (giant,) = scenario.battlefield(P1, ["Hill Giant"], owner=P0)
    scenario.tap(giant).damage(giant, 2)
    state = scenario.build()
    move_object(state, giant, Zone.graveyard(P0))
    known = state.last_known[giant]
    assert known.characteristics.name == "Hill Giant" and known.characteristics.power == 3
    assert (known.controller, known.owner, known.zone.kind.value) == (P1, P0, "battlefield")
    assert (known.tapped, known.damage, known.spell) == (True, 2, None)
    assert information(state, giant) == known


def test_608_2h_a_spell_leaving_the_stack_records_its_record() -> None:
    scenario = Scenario(2)
    (spell,) = scenario.stack(P0, ["Test Shock"])
    scenario.targets(spell, [TargetPlayer(P1)])
    state = scenario.build()
    record = state.objects[spell].spell
    move_object(state, spell, EXILE)
    known = state.last_known[spell]
    assert known.spell == record and known.controller == P0
    assert known.characteristics.name == "Test Shock"


def test_608_2h_other_zones_record_nothing() -> None:
    """Only the battlefield and the stack (design.md §17.9): a card moving from a hand to a
    graveyard leaves no last known information."""
    scenario = Scenario(2)
    (card,) = scenario.hand(P0, ["Grizzly Bears"])
    state = scenario.build()
    move_object(state, card, Zone.graveyard(P0))
    assert state.last_known == {}
    assert information(state, card) is None


def test_608_2h_current_information_while_the_object_exists() -> None:
    scenario = Scenario(2)
    (bears,) = scenario.battlefield(P1, ["Grizzly Bears"])
    scenario.damage(bears, 1)
    state = scenario.build()
    known = information(state, bears)
    assert known is not None and (known.controller, known.damage) == (P1, 1)
    assert bears not in state.last_known


def test_608_2h_last_known_information_is_forgotten_once_the_stack_is_empty() -> None:
    """While the stack holds a spell, the record of a creature that left stays; once a player
    is about to receive priority with an empty stack, it is gone."""
    scenario = Scenario(2)
    (bears,) = scenario.battlefield(P1, ["Grizzly Bears"])
    scenario.stack(P0, ["Test Ponder"])
    scenario.library(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    move_object(state, bears, EXILE)
    run_script(state, pass_(P0))
    assert bears in state.last_known  # P1 has priority, the Ponder still on the stack
    run_script(state, pass_(P1))  # the Ponder resolves; P0 receives priority, stack empty
    assert state.last_known == {}
