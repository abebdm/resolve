"""Chandra's Ignition: {3}{R}{R}, Sorcery. "Target creature you control deals damage equal to
its power to each other creature and each opponent."

Oracle text and rulings checked against the Scryfall snapshot of 2026-10-22
(``tools/excerpts/cards.json``). The rulings (2015-06-22):

- if the creature is an illegal target as Chandra's Ignition tries to resolve, it doesn't resolve
  and no damage is dealt;
- the power of the target creature as it resolves is the damage dealt;
- the creature is the source of the damage, not Chandra's Ignition.

From the pinned CR: the damage to every creature and opponent is dealt at once (one damage
event, 120.4b); damage to a creature is marked on it (120.3e) and to a player makes them lose
that much life (120.3a); 0 damage isn't dealt (120.8). Lethal damage destroys creatures only when
state-based actions are next checked (704.5g, 704.3), all at once; a player at 0 life loses
(704.5a). "Each opponent" is each opponent still in the game (102.2, 800.4a).

The ruling "its power as it resolves" can't be told apart from the printed power until effects
can change power (M5).
"""

from __future__ import annotations

from pathlib import Path

from resolve.cards.definitions.removal import CHANDRAS_IGNITION
from resolve.cards.registry import default_registry
from resolve.data.cards import load_card_excerpt
from resolve.decisions.spaces import CastSpellOption, ObjectOption
from resolve.engine.concede import concede
from resolve.events.damage import DamageDealt
from resolve.events.permanents import PermanentDestroyed
from resolve.events.spells import SpellDidNotResolve, SpellResolved
from resolve.state.ids import PlayerId
from resolve.state.mana import ManaType
from resolve.state.spell import TargetObject
from resolve.state.turn import Phase, Step
from resolve.state.zones import Zone
from tests.casting_support import cast, choose_targets, options, pass_, records
from tests.rules.test_115_targets import target_options
from tests.scenario import Scenario, names, run_script

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)
R, W = ManaType.RED, ManaType.WHITE
EXCERPT = Path(__file__).resolve().parents[2] / "tools" / "excerpts" / "cards.json"
ORACLE = (
    "Target creature you control deals damage equal to its power to each other creature and "
    "each opponent."
)


def test_its_definition_is_its_oracle_text() -> None:
    assert default_registry().get("Chandra's Ignition") is CHANDRAS_IGNITION
    assert CHANDRAS_IGNITION.spell is not None and CHANDRAS_IGNITION.spell.text == ORACLE
    card = load_card_excerpt(EXCERPT).get("Chandra's Ignition")
    assert card.faces[0].oracle_text == ORACLE
    assert (card.faces[0].mana_cost, card.type_line) == ("{3}{R}{R}", "Sorcery")


def test_120_3_damage_marks_creatures_and_costs_players_life() -> None:
    """Three players. P0's Hill Giant (3/3) is the target; P0 also has Grizzly Bears, P1 Savannah
    Lions, P2 Test Wall (0/4). One damage event with the Giant as its source: 3 to the Bears,
    the Lions and the Wall, none to the Giant; 3 to P1 and P2, none to P0. Then state-based
    actions destroy the Bears and the Lions together (704.5g); the Wall survives with 3 damage."""
    scenario = Scenario(3)
    (spell,) = scenario.stack(P0, ["Chandra's Ignition"])
    giant, bears = scenario.battlefield(P0, ["Hill Giant", "Grizzly Bears"])
    (lions,) = scenario.battlefield(P1, ["Savannah Lions"])
    (wall,) = scenario.battlefield(P2, ["Test Wall"])
    scenario.targets(spell, [TargetObject(giant)])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1), pass_(P2))
    (damage,) = records(state, DamageDealt)
    assert damage.source == giant
    assert damage.to_objects == ((bears, 3), (lions, 3), (wall, 3))
    assert damage.to_players == ((P1, 3), (P2, 3))
    destroyed = records(state, PermanentDestroyed)
    assert sorted(r.obj for r in destroyed) == sorted([bears, lions])
    assert all("704.5g" in r.rules for r in destroyed)
    # Destroyed together: one state-based action check (704.3), logged one after the other.
    first, second = [e.index for e in state.event_log if isinstance(e.record, PermanentDestroyed)]
    assert second == first + 1
    assert state.battlefield == [giant, wall] and state.objects[wall].damage == 3
    assert state.objects[giant].damage == 0
    assert [p.life for p in state.players] == [20, 17, 17]
    assert names(state, Zone.graveyard(P0)) == ["Grizzly Bears", "Chandra's Ignition"]


def test_chandras_ignition_illegal_target_means_no_damage() -> None:
    """P0 casts Chandra's Ignition with their Hill Giant; P1 exiles the Giant in response. The
    only target is illegal, so Chandra's Ignition doesn't resolve and no damage is dealt (the
    ruling; 608.2b)."""
    scenario = Scenario(2)
    (spell,) = scenario.stack(P0, ["Chandra's Ignition"])
    (giant,) = scenario.battlefield(P0, ["Hill Giant"])
    (lions,) = scenario.battlefield(P1, ["Savannah Lions"])
    scenario.targets(spell, [TargetObject(giant)])
    (swords,) = scenario.hand(P1, ["Swords to Plowshares"])
    scenario.mana(P1, W)
    scenario.at(Phase.PRECOMBAT_MAIN, priority=P1, passed=[P0])
    state = scenario.build()
    run_script(state, cast(swords, P1), choose_targets(giant))
    run_script(state, pass_(P1), pass_(P0), pass_(P0), pass_(P1))
    assert [r.spell for r in records(state, SpellDidNotResolve)] == [spell]
    assert records(state, DamageDealt) == []
    assert lions in state.battlefield and state.player(P1).life == 20
    assert state.player(P0).life == 23  # the Giant's controller gained 3 from Swords


def test_120_8_zero_damage_isnt_dealt() -> None:
    """Test Wall (0/4) as the target: its power is 0, so it deals no damage at all (120.8): no
    damage event. Chandra's Ignition still resolves."""
    scenario = Scenario(2)
    (spell,) = scenario.stack(P0, ["Chandra's Ignition"])
    (wall,) = scenario.battlefield(P0, ["Test Wall"])
    scenario.battlefield(P1, ["Savannah Lions"])
    scenario.targets(spell, [TargetObject(wall)])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1))
    assert records(state, DamageDealt) == []
    assert [r.spell for r in records(state, SpellResolved)] == [spell]
    assert state.player(P1).life == 20 and len(state.battlefield) == 2


def test_chandras_ignition_targets_only_your_creatures() -> None:
    """"Target creature you control": only P0's creatures are offered, not P1's."""
    scenario = Scenario(2)
    (ignition,) = scenario.hand(P0, ["Chandra's Ignition"])
    giant, bears = scenario.battlefield(P0, ["Hill Giant", "Grizzly Bears"])
    scenario.battlefield(P1, ["Savannah Lions"])
    scenario.mana(P0, R, R, R, R, R)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(ignition, P0))
    assert target_options(state) == (ObjectOption(giant), ObjectOption(bears))


def test_307_1_it_is_cast_with_sorcery_timing() -> None:
    scenario = Scenario(2)
    scenario.hand(P0, ["Chandra's Ignition"])
    scenario.battlefield(P0, ["Hill Giant"])
    scenario.at(Step.UPKEEP)
    assert not any(isinstance(o, CastSpellOption) for o in options(scenario.build()))


def test_704_5a_damage_from_a_spell_can_end_the_game() -> None:
    """P1 at 3 life takes 3 from the Hill Giant: at 0 life they lose (704.5a), and P0 wins
    (104.2a)."""
    scenario = Scenario(2)
    (spell,) = scenario.stack(P0, ["Chandra's Ignition"])
    (giant,) = scenario.battlefield(P0, ["Hill Giant"])
    scenario.targets(spell, [TargetObject(giant)])
    scenario.life(P1, 3)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1))
    assert state.player(P1).life == 0 and state.player(P1).lost
    assert state.result is not None and state.result.winners == (P0,)


def test_800_4_each_opponent_skips_players_who_left() -> None:
    """Three players; P2 concedes while Chandra's Ignition is on the stack. P2's Savannah Lions
    left the game with them (800.4a); the damage goes to P1 and P1's creature only."""
    scenario = Scenario(3)
    (spell,) = scenario.stack(P0, ["Chandra's Ignition"])
    (giant,) = scenario.battlefield(P0, ["Hill Giant"])
    (bears,) = scenario.battlefield(P1, ["Grizzly Bears"])
    scenario.battlefield(P2, ["Savannah Lions"])
    scenario.targets(spell, [TargetObject(giant)])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    concede(state, P2)
    run_script(state, pass_(P0), pass_(P1))
    (damage,) = records(state, DamageDealt)
    assert damage.to_players == ((P1, 3),) and damage.to_objects == ((bears, 3),)


def test_608_2n_a_resolved_sorcery_goes_to_its_owners_graveyard() -> None:
    scenario = Scenario(2)
    (spell,) = scenario.stack(P0, ["Chandra's Ignition"])
    (giant,) = scenario.battlefield(P0, ["Hill Giant"])
    scenario.targets(spell, [TargetObject(giant)])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1))
    assert names(state, Zone.graveyard(P0)) == ["Chandra's Ignition"] and state.stack == []
    assert state.player(P1).life == 17
