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
  graveyard; the destination is the rule default ``resolved_spell_destination``.
- 608.2b: as it resolves, a spell checks its targets again. A target that left the zone it was
  in, or that no longer fits, is illegal. If every target, for every instance of the word
  "target", is illegal, the spell doesn't resolve: it is removed from the stack and put into its
  owner's graveyard, and none of its effects happen.
"""

from __future__ import annotations

from resolve.data.mana_cost import parse_mana_cost
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import CastSpellOption
from resolve.engine.concede import concede
from resolve.events.damage import DamageDealt
from resolve.events.life import LifeGained
from resolve.events.spells import PermanentSpellResolved, SpellDidNotResolve, SpellResolved
from resolve.rules import defaults
from resolve.state.ids import PlayerId
from resolve.state.mana import Mana, ManaType
from resolve.state.spell import FROM_HAND, NORMAL, CastChoices, TargetObject, TargetPlayer
from resolve.state.turn import Phase, Step
from resolve.state.zones import BATTLEFIELD, EXILE, Zone
from tests.casting_support import activate, cast, options, pass_, records
from tests.game_fixtures import request_of
from tests.scenario import Scenario, names, run_script

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)
G, W = ManaType.GREEN, ManaType.WHITE


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


def test_608_2c_an_instant_follows_its_instructions() -> None:
    """Test Shock targeting P1 resolves: it deals 2 damage to P1, who loses 2 life (120.3a),
    then it goes to its owner's graveyard (608.2n). Then P0, the active player, receives
    priority (117.3b)."""
    scenario = Scenario(2)
    (spell,) = scenario.stack(P0, ["Test Shock"])
    scenario.targets(spell, [TargetPlayer(P1)])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1))
    assert state.player(P1).life == 18 and state.player(P0).life == 20
    (damage,) = records(state, DamageDealt)
    assert (damage.source, damage.to_players, damage.to_objects) == (spell, ((P1, 2),), ())
    assert state.stack == [] and names(state, Zone.graveyard(P0)) == ["Test Shock"]
    (resolved,) = records(state, SpellResolved)
    assert resolved.spell == spell and resolved.destination == Zone.graveyard(P0)
    assert resolved.moved == state.player(P0).graveyard[-1]
    assert "608.2n" in resolved.rules
    assert request_of(state).player == P0


def test_608_2c_a_sorcery_without_targets_follows_its_instructions() -> None:
    """Test Ponder ("Draw a card.") has no targets: its controller draws a card (121.1)."""
    scenario = Scenario(2)
    scenario.stack(P0, ["Test Ponder"])
    (top,) = scenario.library(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1))
    assert names(state, Zone.hand(P0)) == ["Forest"] and state.player(P0).library == []
    assert names(state, Zone.graveyard(P0)) == ["Test Ponder"]
    assert top not in state.objects


def test_608_2n_a_resolved_instant_goes_to_its_owners_graveyard() -> None:
    """A Test Shock P0 controls but P1 owns goes to P1's graveyard after resolving (608.2n,
    400.3), not its controller's."""
    scenario = Scenario(3)
    (spell,) = scenario.stack(P0, ["Test Shock"], owner=P1)
    scenario.targets(spell, [TargetPlayer(P2)])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1), pass_(P2))
    assert names(state, Zone.graveyard(P1)) == ["Test Shock"]
    assert state.player(P0).graveyard == [] and state.player(P2).life == 18


def test_608_2b_a_spell_whose_only_target_left_doesnt_resolve() -> None:
    """P0's Swords to Plowshares targets P1's Grizzly Bears; P1 responds with their own Swords
    on the same Bears. P1's resolves first: the Bears are exiled and P1, their controller, gains
    2. P0's then finds its only target gone (608.2b): it doesn't resolve and goes to P0's
    graveyard, so P1 gains life only once."""
    scenario = Scenario(2)
    (theirs,) = scenario.stack(P0, ["Swords to Plowshares"])
    (bears,) = scenario.battlefield(P1, ["Grizzly Bears"])
    scenario.targets(theirs, [TargetObject(bears)])
    (swords,) = scenario.hand(P1, ["Swords to Plowshares"])
    scenario.mana(P1, W)
    scenario.at(Phase.PRECOMBAT_MAIN, priority=P1, passed=[P0])
    state = scenario.build()
    run_script(state, cast(swords, P1))  # the Bears are the only legal target: not asked
    run_script(state, pass_(P1), pass_(P0))  # P1's Swords resolves
    assert state.player(P1).life == 22 and names(state, EXILE) == ["Grizzly Bears"]
    assert state.stack == [theirs]
    run_script(state, pass_(P0), pass_(P1))
    (failed,) = records(state, SpellDidNotResolve)
    assert failed.spell == theirs and failed.rules[0] == "608.2b"
    assert names(state, Zone.graveyard(P0)) == ["Swords to Plowshares"]
    assert failed.moved == state.player(P0).graveyard[-1]
    assert state.player(P1).life == 22 and len(records(state, LifeGained)) == 1
    assert len(records(state, SpellResolved)) == 1  # P1's only


def test_608_2b_a_player_who_left_is_an_illegal_target() -> None:
    """P0's Test Shock targets P2; P2 concedes before it resolves. P2 has left the game (800.4a),
    so the Shock's only target is illegal: it doesn't resolve, and no damage is dealt."""
    scenario = Scenario(3)
    (spell,) = scenario.stack(P0, ["Test Shock"])
    scenario.targets(spell, [TargetPlayer(P2)])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    concede(state, P2)
    run_script(state, pass_(P0), pass_(P1))
    assert [r.spell for r in records(state, SpellDidNotResolve)] == [spell]
    assert records(state, DamageDealt) == []
    assert names(state, Zone.graveyard(P0)) == ["Test Shock"]


def test_115_6_a_spell_without_targets_isnt_checked() -> None:
    """608.2b applies to a spell with targets; Test Ponder has none and always resolves."""
    scenario = Scenario(2)
    scenario.stack(P0, ["Test Ponder"])
    scenario.library(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1))
    assert records(state, SpellDidNotResolve) == [] and len(records(state, SpellResolved)) == 1


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
