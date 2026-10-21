"""608: resolving spells, 405: the stack, and priority around them (117.1a, 117.3b, 117.4).

From the pinned CR:

- 117.4, 405.5, 608.1: when all players pass in succession, the top (last-added) object on the
  stack resolves. Every player still in the game must pass, however many there are.
- 608.3a: a permanent spell with no targets becomes a permanent on the battlefield under its
  controller's control; 400.7: as a new object. 400.7d: the permanent can know how its spell was
  cast.
- 117.3b: the active player receives priority after a spell resolves (passing starts over).
- 117.1a: a noninstant spell may be cast only while the stack is empty.
- 608.2c, 608.2n: an instant or sorcery follows its instructions, then goes to its owner's
  graveyard. Spell abilities don't exist until M2.6, so resolving one is a gap; the destination
  is the rule default ``resolved_spell_destination``.
"""

from __future__ import annotations

import pytest

from resolve.data.mana_cost import parse_mana_cost
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import CastSpellOption
from resolve.errors import NotImplementedRule
from resolve.events.spells import PermanentSpellResolved
from resolve.rules import defaults
from resolve.state.ids import PlayerId
from resolve.state.mana import Mana, ManaType
from resolve.state.spell import FROM_HAND, NORMAL, CastChoices
from resolve.state.turn import Phase, Step
from resolve.state.zones import BATTLEFIELD, Zone
from tests.casting_support import activate, cast, options, pass_, records
from tests.game_fixtures import request_of
from tests.scenario import Scenario, names, run_script

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)
G = ManaType.GREEN


def test_608_1_when_all_pass_the_top_object_resolves() -> None:
    """P1's Grizzly Bears on the stack in P0's upkeep: once both pass it becomes P1's permanent
    (608.3a), a new object (400.7); then P0, the active player, receives priority (117.3b)."""
    scenario = Scenario(2)
    (spell,) = scenario.stack(P1, ["Grizzly Bears"])
    card = scenario.card_of(spell)
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    run_script(state, pass_(P0))
    assert state.stack == [spell]
    run_script(state, pass_(P1))
    assert state.stack == [] and spell not in state.objects
    (permanent,) = state.battlefield
    obj = state.objects[permanent]
    assert obj.card == card and obj.controller == P1 and obj.zone == BATTLEFIELD
    assert obj.spell is None
    (resolved,) = records(state, PermanentSpellResolved)
    assert (resolved.spell, resolved.permanent) == (spell, permanent)
    assert "608.3a" in resolved.rules
    request = request_of(state)
    assert request.player == P0 and request.kind is DecisionKind.PRIORITY_ACTION
    turn = state.turn
    assert turn is not None and turn.passed == [] and turn.step is Step.UPKEEP


def test_117_4_every_player_must_pass_in_multiplayer() -> None:
    scenario = Scenario(3)
    (spell,) = scenario.stack(P0, ["Grizzly Bears"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1))
    assert state.stack == [spell] and request_of(state).player == P2
    run_script(state, pass_(P2))
    assert state.stack == [] and names(state, BATTLEFIELD) == ["Grizzly Bears"]
    assert request_of(state).player == P0


def test_405_5_the_stack_resolves_last_in_first_out() -> None:
    scenario = Scenario(2)
    top, bottom = scenario.stack(P0, ["Hill Giant", "Grizzly Bears"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1))
    assert state.stack == [bottom] and names(state, BATTLEFIELD) == ["Hill Giant"]
    run_script(state, pass_(P0), pass_(P1))
    assert state.stack == [] and names(state, BATTLEFIELD) == ["Hill Giant", "Grizzly Bears"]
    assert top not in state.objects


def test_117_1a_a_noninstant_spell_can_be_cast_only_with_an_empty_stack() -> None:
    scenario = Scenario(2)
    giant, shock = scenario.hand(P0, ["Hill Giant", "Test Shock"])
    scenario.stack(P0, ["Grizzly Bears"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    offered = [o for o in options(state) if isinstance(o, CastSpellOption)]
    assert offered == [CastSpellOption(shock, NORMAL, FROM_HAND)]
    run_script(state, pass_(P0), pass_(P1))
    offered = [o for o in options(state) if isinstance(o, CastSpellOption)]
    assert offered == [
        CastSpellOption(giant, NORMAL, FROM_HAND),
        CastSpellOption(shock, NORMAL, FROM_HAND),
    ]


@pytest.mark.parametrize("card", ["Test Shock", "Test Ponder"])
def test_608_2c_resolving_an_instant_is_a_gap_until_spell_abilities_exist(card: str) -> None:
    scenario = Scenario(2)
    scenario.stack(P0, [card])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, pass_(P0))
    with pytest.raises(NotImplementedRule) as gap:
        run_script(state, pass_(P1))
    assert gap.value.rule == "608.2c"


def test_608_2n_the_destination_is_the_owners_graveyard() -> None:
    """A spell P0 controls but P1 owns goes to P1's graveyard (608.2n, 400.3)."""
    scenario = Scenario(3)
    (spell,) = scenario.stack(P0, ["Test Shock"], owner=P1)
    state = scenario.build()
    assert defaults.resolved_spell_destination(state, spell) == Zone.graveyard(P1)


def test_400_7d_the_permanent_records_how_its_spell_was_cast() -> None:
    scenario = Scenario(2)
    (bears,) = scenario.hand(P0, ["Grizzly Bears"])
    forest_a, forest_b = scenario.battlefield(P0, ["Forest", "Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(bears, P0), activate(forest_a), activate(forest_b), pass_(P0), pass_(P1))
    (permanent,) = [o for o in state.battlefield if o not in (forest_a, forest_b)]
    assert state.objects[permanent].cast_record == CastChoices(
        NORMAL,
        FROM_HAND,
        Zone.hand(P0),
        total_cost=parse_mana_cost("{1}{G}"),
        mana_spent=(Mana(G, forest_a), Mana(G, forest_b)),
    )


def test_608_3a_the_permanent_enters_under_the_spells_controller_not_its_owner() -> None:
    """A spell P0 controls but P1 owns becomes P0's permanent (608.3a), still owned by P1
    (108.3)."""
    scenario = Scenario(3)
    (spell,) = scenario.stack(P0, ["Grizzly Bears"], owner=P1)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1), pass_(P2))
    (permanent,) = state.battlefield
    obj = state.objects[permanent]
    assert (obj.controller, obj.owner) == (P0, P1)
    assert spell not in state.objects
