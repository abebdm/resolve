"""506-508, 511.3: the combat state, declaring attackers, and leaving combat.

From the pinned CR:

- 506.2: in a two-player game the nonactive player is the defending player; 802.2: in a
  multiplayer game (the attack multiple players option, every multiplayer game here) every
  opponent of the active player is one. 507.1 then has no choice to make.
- 506.3: only a creature can attack. 508.1a: the active player chooses which creatures they
  control, if any, attack; they must be untapped, not battles, and have haste or have been
  controlled continuously since the turn began (302.6). 702.3b: a creature with defender can't
  attack.
- 508.1b, 802.3: in a multiplayer game each attacker's player is chosen as it is declared.
- 508.1f: the chosen creatures tap (not a cost); 702.20b: vigilance keeps them untapped.
- 508.1k: each chosen creature becomes an attacking creature until it is removed from combat or
  the combat phase ends. 506.4: leaving the battlefield removes it from combat; 506.4b: tapping
  or untapping it doesn't.
- 508.8: if no creatures are declared as attackers (or put onto the battlefield attacking), the
  declare blockers and combat damage steps are skipped. An attacker removed before blocks has
  still been declared, so they aren't.
- 511.3: as the end of combat step ends, everything is removed from combat.
- 508.1, 733: an illegal declaration is refused, and the game is as before it.
- 509.1: declaring blockers is M3.3's; until then a defending player who is attacked and
  controls an untapped creature is a gap.
"""

from __future__ import annotations

import copy

import pytest

from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import Assignment
from resolve.engine.api import submit
from resolve.engine.concede import concede
from resolve.errors import InvalidAnswer, NotImplementedRule
from resolve.events.combat import AttackersDeclared, CombatBegan, CombatEnded
from resolve.events.permanents import PermanentTapped
from resolve.events.turn import StepBegan
from resolve.rules import legality
from resolve.state.combat import AttackPlayer, AttackRecord, CombatState
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.invariants import invariant_violations
from resolve.state.spell import TargetObject
from resolve.state.turn import Phase, Step
from resolve.state.zones import EXILE
from tests.casting_support import pass_, records
from tests.combat_support import (
    attack_answer,
    attack_targets,
    declare_attackers,
    may_attack,
    pass_to,
)
from tests.game_fixtures import answer, request_of
from tests.scenario import Scenario, names, run_script

P0, P1, P2, P3 = PlayerId(0), PlayerId(1), PlayerId(2), PlayerId(3)


def attack_allowed(state: GameState, creature: ObjectId, target: PlayerId = P1) -> bool:
    return legality.allowed(
        state, legality.AttackAction(P0, creature, AttackPlayer(target))
    ).allowed


def combat_of(state: GameState) -> CombatState:
    assert state.turn is not None and state.turn.combat is not None
    return state.turn.combat


def steps_begun(state: GameState) -> list[tuple[Phase, Step | None]]:
    return [(record.phase, record.step) for record in records(state, StepBegan)]


# --- 506.2, 507.1: the combat state ------------------------------------------------------------


def test_506_2_two_players_the_opponent_is_attacked_without_choosing() -> None:
    """The combat phase begins with the combat state and its defending player, the nonactive
    player (506.2), with no 507.1 decision: the first decision is priority in the beginning of
    combat step. In the declaration the attacker's only choice is that player (508.1b)."""
    scenario = Scenario(2)
    (bears,) = scenario.battlefield(P0, ["Grizzly Bears"])
    scenario.at(Step.BEGINNING_OF_COMBAT, begin=True)
    state = scenario.build()
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION
    (began,) = records(state, CombatBegan)
    assert began.defending_players == (P1,)
    assert combat_of(state).defending_players == (P1,)
    assert combat_of(state).attackers == {}
    run_script(state, pass_(P0), pass_(P1))
    assert attack_targets(state, bears) == (P1,)
    declare_attackers(state, {bears: P1})
    assert combat_of(state).attackers == {bears: AttackRecord(bears, AttackPlayer(P1))}


def test_802_3_each_attacker_chooses_a_defending_player() -> None:
    """Four players: P0's opponents are all defending players, in APNAP order (802.2, 101.4),
    and each attacker chooses one of them (802.3). Grizzly Bears attacks P1, Hill Giant P3;
    Savannah Lions stays home. Each defending player is dealt its attacker's damage."""
    scenario = Scenario(4)
    bears, giant, lions = scenario.battlefield(
        P0, ["Grizzly Bears", "Hill Giant", "Savannah Lions"]
    )
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    assert may_attack(state) == (bears, giant, lions)
    for creature in (bears, giant, lions):
        assert attack_targets(state, creature) == (P1, P2, P3)
    declare_attackers(state, {bears: P1, giant: P3})
    (declared,) = records(state, AttackersDeclared)
    assert declared.attacks == ((bears, AttackPlayer(P1)), (giant, AttackPlayer(P3)))
    assert combat_of(state).attackers == {
        bears: AttackRecord(bears, AttackPlayer(P1)),
        giant: AttackRecord(giant, AttackPlayer(P3)),
    }
    assert not state.objects[lions].tapped
    pass_to(state, Phase.POSTCOMBAT_MAIN)
    assert [state.player(p).life for p in (P0, P1, P2, P3)] == [20, 18, 20, 17]


# --- 508.1a, 506.3, 702.3b: who may attack -----------------------------------------------------


def test_508_1a_only_untapped_creatures_the_active_player_controls_can_attack() -> None:
    """P0's untapped Grizzly Bears may attack; their tapped Hill Giant and P1's Savannah Lions
    may not (508.1a, 506.2)."""
    scenario = Scenario(2)
    bears, giant = scenario.battlefield(P0, ["Grizzly Bears", "Hill Giant"])
    (lions,) = scenario.battlefield(P1, ["Savannah Lions"])
    scenario.tap(giant)
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    assert request_of(state).player == P0
    assert request_of(state).rules[0] == "508.1"
    assert may_attack(state) == (bears,)
    assert attack_allowed(state, bears)
    assert not attack_allowed(state, giant)
    lions_attack = legality.AttackAction(P1, lions, AttackPlayer(P0))
    assert not legality.allowed(state, lions_attack).allowed


def test_508_1a_a_creature_cant_attack_its_own_controller_or_a_nonplayer() -> None:
    """Only a defending player may be attacked (506.2): P0 can't attack themselves."""
    scenario = Scenario(2)
    (bears,) = scenario.battlefield(P0, ["Grizzly Bears"])
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    assert not attack_allowed(state, bears, P0)
    assert attack_allowed(state, bears, P1)


def test_508_1a_attacking_is_allowed_only_in_a_combat() -> None:
    """Outside the combat phase there is no combat state, so nothing may attack."""
    scenario = Scenario(2)
    (bears,) = scenario.battlefield(P0, ["Grizzly Bears"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    verdict = legality.allowed(state, legality.AttackAction(P0, bears, AttackPlayer(P1)))
    assert not verdict.allowed and "508.1a" in verdict.rules


def test_702_3b_wall_of_stone_cant_attack() -> None:
    """Wall of Stone has defender: it isn't offered, and the verdict cites 702.3b's prohibition
    (101.2: the prohibition wins over 508.1a's permission)."""
    scenario = Scenario(2)
    wall, bears = scenario.battlefield(P0, ["Wall of Stone", "Grizzly Bears"])
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    assert may_attack(state) == (bears,)
    verdict = legality.allowed(state, legality.AttackAction(P0, wall, AttackPlayer(P1)))
    assert not verdict.allowed
    assert "702.3b" in verdict.rules and "101.2" in verdict.rules


def test_702_3b_only_a_defender_means_no_declaration() -> None:
    """With Wall of Stone as their only creature P0 isn't asked to declare (no creature may
    attack): the step goes on to priority, and 508.8 skips blockers and damage."""
    scenario = Scenario(2)
    scenario.battlefield(P0, ["Wall of Stone"])
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION
    pass_to(state, Phase.POSTCOMBAT_MAIN)
    assert (Phase.COMBAT, Step.DECLARE_BLOCKERS) not in steps_begun(state)


def test_506_3_a_noncreature_cant_attack() -> None:
    """Sol Ring and Darksteel Relic aren't creatures: neither may attack, so nothing is asked."""
    scenario = Scenario(2)
    ring, relic = scenario.battlefield(P0, ["Sol Ring", "Darksteel Relic"])
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION
    assert not attack_allowed(state, ring)
    assert not attack_allowed(state, relic)


# --- 508.1f, 702.20b, 506.4b: tapping ----------------------------------------------------------


def test_508_1f_attacking_taps_the_creature() -> None:
    """Grizzly Bears attacks and becomes tapped as it is declared (508.1f), before it becomes an
    attacking creature (508.1k); Hill Giant, not declared, stays untapped."""
    scenario = Scenario(2)
    bears, giant = scenario.battlefield(P0, ["Grizzly Bears", "Hill Giant"])
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    declare_attackers(state, {bears: P1})
    assert state.objects[bears].tapped and not state.objects[giant].tapped
    (tapped,) = records(state, PermanentTapped)
    assert tapped.obj == bears and tapped.rules[0] == "508.1f"
    log = [entry.record for entry in state.event_log]
    assert log.index(tapped) < log.index(records(state, AttackersDeclared)[0])


def test_702_20b_vigilance_doesnt_tap_it() -> None:
    """Alaborn Grenadier attacks without tapping (702.20b), and is attacking."""
    scenario = Scenario(2)
    (grenadier,) = scenario.battlefield(P0, ["Alaborn Grenadier"])
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    declare_attackers(state, {grenadier: P1})
    assert not state.objects[grenadier].tapped
    assert records(state, PermanentTapped) == []
    assert grenadier in combat_of(state).attackers


def test_506_4b_tapping_an_attacker_keeps_it_attacking() -> None:
    """Alaborn Grenadier attacks untapped (vigilance). In the declare attackers step P1's Cryptic
    Command ("tap all creatures your opponents control", "draw a card") taps it: it stays an
    attacking creature (506.4b) and deals its combat damage, 2."""
    scenario = Scenario(2)
    (grenadier,) = scenario.battlefield(P0, ["Alaborn Grenadier"])
    scenario.library(P1, ["Forest"])
    (cryptic,) = scenario.stack(P1, ["Cryptic Command"])
    scenario.modes(cryptic, 2, 3)
    scenario.at(Step.DECLARE_ATTACKERS)
    scenario.attacking(P1, grenadier)
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1))
    assert state.objects[grenadier].tapped
    assert grenadier in combat_of(state).attackers
    pass_to(state, Phase.POSTCOMBAT_MAIN)
    assert state.player(P1).life == 18


# --- 508.8: skipping blockers and damage -------------------------------------------------------


def test_508_8_no_attackers_skips_blockers_and_damage() -> None:
    """P0 declares no attackers: no ``AttackersDeclared``; the declare blockers and combat damage
    steps don't begin; the end of combat step does."""
    scenario = Scenario(2)
    scenario.battlefield(P0, ["Grizzly Bears"])
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    declare_attackers(state, {})
    assert records(state, AttackersDeclared) == []
    assert not combat_of(state).attacks_happened
    pass_to(state, Phase.POSTCOMBAT_MAIN)
    steps = steps_begun(state)
    assert (Phase.COMBAT, Step.DECLARE_BLOCKERS) not in steps
    assert (Phase.COMBAT, Step.COMBAT_DAMAGE) not in steps
    assert (Phase.COMBAT, Step.END_OF_COMBAT) in steps


def test_508_8_an_attacker_removed_before_blocks_doesnt_skip_them() -> None:
    """Hill Giant attacks; in the declare attackers step P1's Swords to Plowshares exiles it, so
    it leaves combat (506.4) and no creature is attacking. A creature was declared, though, so
    the declare blockers and combat damage steps still begin (508.8), and no damage is dealt."""
    scenario = Scenario(2)
    (giant,) = scenario.battlefield(P0, ["Hill Giant"])
    (swords,) = scenario.stack(P1, ["Swords to Plowshares"])
    scenario.targets(swords, [TargetObject(giant)])
    scenario.at(Step.DECLARE_ATTACKERS)
    scenario.attacking(P1, giant)
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1))
    assert names(state, EXILE) == ["Hill Giant"]
    assert combat_of(state).attackers == {}
    assert combat_of(state).attacks_happened
    pass_to(state, Phase.POSTCOMBAT_MAIN)
    steps = steps_begun(state)
    assert (Phase.COMBAT, Step.DECLARE_BLOCKERS) in steps
    assert (Phase.COMBAT, Step.COMBAT_DAMAGE) in steps
    assert state.player(P1).life == 20


# --- 506.4: removed from combat ----------------------------------------------------------------


def test_506_4_a_blocker_that_leaves_is_removed_and_its_attacker_stays_blocked() -> None:
    """Three players: Grizzly Bears attacks P2, blocked by P2's Test Wall. P2 concedes: their
    Wall leaves the game (800.4a), so it is removed from combat (506.4); the Bears stay blocked
    (509.1h) and the combat state stays consistent."""
    scenario = Scenario(3)
    (bears,) = scenario.battlefield(P0, ["Grizzly Bears"])
    (wall,) = scenario.battlefield(P2, ["Test Wall"])
    scenario.at(Step.DECLARE_BLOCKERS)
    scenario.attacking(P2, bears)
    scenario.blocking(wall, bears)
    state = scenario.build()
    concede(state, P2)
    assert combat_of(state).blockers == {}
    assert combat_of(state).attackers[bears].blocked is True
    assert invariant_violations(state) == []


def test_506_4_an_attacker_that_leaves_is_removed_from_its_blockers() -> None:
    """Hill Giant and Grizzly Bears attack P1; P1's Test Wall blocks the Giant. P1's Swords to
    Plowshares exiles the Giant: it leaves combat, and the Wall blocks nothing (510.1d)."""
    scenario = Scenario(2)
    giant, bears = scenario.battlefield(P0, ["Hill Giant", "Grizzly Bears"])
    (wall,) = scenario.battlefield(P1, ["Test Wall"])
    (swords,) = scenario.stack(P1, ["Swords to Plowshares"])
    scenario.targets(swords, [TargetObject(giant)])
    scenario.at(Step.DECLARE_BLOCKERS)
    scenario.attacking(P1, giant, bears)
    scenario.blocking(wall, giant)
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1))
    combat = combat_of(state)
    assert list(combat.attackers) == [bears]
    assert combat.blockers[wall].blocking == ()
    assert invariant_violations(state) == []


# --- 511.3: the end of combat ------------------------------------------------------------------


def test_511_3_no_creature_is_attacking_after_combat() -> None:
    """Grizzly Bears is still attacking in the end of combat step (508.1k); as that step ends it
    is removed from combat (511.3): there is no combat state in the postcombat main phase."""
    scenario = Scenario(2)
    (bears,) = scenario.battlefield(P0, ["Grizzly Bears"])
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    declare_attackers(state, {bears: P1})
    pass_to(state, Phase.COMBAT, Step.END_OF_COMBAT)
    assert bears in combat_of(state).attackers
    pass_to(state, Phase.POSTCOMBAT_MAIN)
    assert state.turn is not None and state.turn.combat is None
    (ended,) = records(state, CombatEnded)
    assert ended.rules[0] == "511.3"


# --- 508.1, 733: an illegal declaration ---------------------------------------------------------


def test_508_1_an_illegal_attacker_is_rejected_and_nothing_changes() -> None:
    """The declaration offers only Grizzly Bears (the Hill Giant is tapped). An answer that
    names a second attacker, or a target the Bears can't attack, is refused (``InvalidAnswer``)
    and the state is unchanged; the legal answer is then accepted."""
    scenario = Scenario(2)
    bears, giant = scenario.battlefield(P0, ["Grizzly Bears", "Hill Giant"])
    scenario.tap(giant)
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    before = copy.deepcopy(state)
    for bad in (Assignment(((0,), (0,))), Assignment(((1,),)), Assignment(((0, 0),))):
        with pytest.raises(InvalidAnswer):
            submit(state, answer(state, bad))
        assert state == before
    submit(state, answer(state, attack_answer(state, {bears: P1})))
    assert list(combat_of(state).attackers) == [bears]


# --- 509.1: blocks are M3.3's ------------------------------------------------------------------


def test_509_1_blocks_are_a_gap_until_m3_3() -> None:
    """Hill Giant attacks P1, who controls an untapped Grizzly Bears: P1 could block, so the
    declare blockers step stops at the 509.1 gap (until M3.3)."""
    scenario = Scenario(2)
    (giant,) = scenario.battlefield(P0, ["Hill Giant"])
    scenario.battlefield(P1, ["Grizzly Bears"])
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    declare_attackers(state, {giant: P1})
    with pytest.raises(NotImplementedRule) as gap:
        pass_to(state, Phase.POSTCOMBAT_MAIN)
    assert gap.value.rule == "509.1"


def test_509_1_no_possible_blocker_means_no_gap() -> None:
    """Three players. Hill Giant attacks P1, whose only creature is tapped; P2 controls an
    untapped Grizzly Bears, but P2 isn't attacked, so it can't block (509.1a, 802.4a). No
    blocks are possible: the Giant is unblocked (509.1h) and deals its damage."""
    scenario = Scenario(3)
    (giant,) = scenario.battlefield(P0, ["Hill Giant"])
    (lions,) = scenario.battlefield(P1, ["Savannah Lions"])
    scenario.battlefield(P2, ["Grizzly Bears"])
    scenario.tap(lions)
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    declare_attackers(state, {giant: P1})
    pass_to(state, Phase.COMBAT, Step.COMBAT_DAMAGE)
    assert combat_of(state).attackers[giant].blocked is False
    pass_to(state, Phase.POSTCOMBAT_MAIN)
    assert [state.player(p).life for p in (P0, P1, P2)] == [20, 17, 20]
