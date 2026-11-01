"""509: the declare blockers step (M3.3).

From the pinned CR:

- 509.1a: the defending player chooses which creatures they control, if any, will block. The
  chosen creatures must be untapped and can't be battles. Each blocks one creature attacking
  that player (Palace Guard, "can block any number of creatures", blocks more:
  ``defaults.blocks_allowed``).
- 509.1g: each chosen creature becomes a blocking creature, blocking the attackers chosen for it.
- 509.1h: an attacker with blockers declared for it becomes blocked; one without becomes
  unblocked. It stays blocked even if all its blockers are removed from combat.
- 509.2: then the active player gets priority.
- 802.4: with several defending players, each declares blockers in APNAP order, the first all
  their blocks, then the second; 802.4a: a defending player blocks only with their own creatures,
  and only creatures attacking them; 802.4b: their blocks are judged ignoring other players'
  attackers and blockers.
- 702.16f: an attacking creature with protection can't be blocked by creatures that have the
  stated quality; 702.16j: one with protection from everything can't be blocked by creatures.
  Protection on the *blocker* doesn't stop it blocking (its damage is prevented, 702.16e: a gap
  until M6). The user moved this part of protection from M3.4 into M3.3 (2026-10-31): without it
  blocks illegal under 702.16f would be accepted.
- 702.3b: defender stops a creature attacking, not blocking.
- 800.4a: a player who leaves the game takes their objects with them; 104.3a: a player may
  concede at any time, and the pending decision is asked again.
"""

from __future__ import annotations

import pytest

from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import Assignment
from resolve.engine.api import submit, view_for
from resolve.engine.concede import concede
from resolve.errors import InvalidAnswer
from resolve.events.combat import BlockersDeclared
from resolve.rules import legality
from resolve.state.combat import BlockRecord, CombatState
from resolve.state.game import GameState, move_object
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.invariants import invariant_violations
from resolve.state.turn import Phase, Step
from resolve.state.zones import Zone
from tests.casting_support import records
from tests.combat_support import (
    block_answer,
    block_space,
    blockable,
    declare_attackers,
    declare_blockers,
    may_block,
    pass_to,
)
from tests.game_fixtures import answer, request_of
from tests.scenario import Scenario

P0, P1, P2, P3 = PlayerId(0), PlayerId(1), PlayerId(2), PlayerId(3)


def combat_of(state: GameState) -> CombatState:
    assert state.turn is not None and state.turn.combat is not None
    return state.turn.combat


def block_allowed(
    state: GameState, blocker: ObjectId, attacker: ObjectId, player: PlayerId = P1
) -> bool:
    return legality.allowed(state, legality.BlockAction(player, blocker, attacker)).allowed


# --- 509.1a: who may block, and what ------------------------------------------------------------


def test_509_1a_an_untapped_creature_blocks_an_attacker() -> None:
    """Hill Giant attacks P1, who controls an untapped Grizzly Bears: P1 is asked to declare
    blockers (509.1a), may block the Giant with the Bears, and after the declaration the Bears
    are blocking the Giant (509.1g), which is blocked (509.1h); then P0 gets priority (509.2)."""
    scenario = Scenario(2)
    (giant,) = scenario.battlefield(P0, ["Hill Giant"])
    (bears,) = scenario.battlefield(P1, ["Grizzly Bears"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, giant)
    state = scenario.build()
    request = request_of(state)
    assert (request.kind, request.player) == (DecisionKind.DECLARE_BLOCKERS, P1)
    assert "509.1a" in request.rules
    assert may_block(state) == (bears,)
    assert blockable(state, bears) == (giant,)
    declare_blockers(state, {bears: (giant,)})
    combat = combat_of(state)
    assert combat.blockers == {bears: BlockRecord(bears, (giant,))}
    assert combat.attackers[giant].blocked is True
    (declared,) = records(state, BlockersDeclared)
    assert declared.blocks == ((bears, (giant,)),)
    after = request_of(state)
    assert (after.kind, after.player) == (DecisionKind.PRIORITY_ACTION, P0)  # 509.2
    assert state.turn is not None and state.turn.step is Step.DECLARE_BLOCKERS


def test_509_1a_a_tapped_creature_cant_block() -> None:
    """P1's tapped Grizzly Bears can't block (509.1a: blockers must be untapped); their untapped
    Savannah Lions can. With only tapped creatures, P1 isn't asked and the Giant is unblocked."""
    scenario = Scenario(2)
    (giant,) = scenario.battlefield(P0, ["Hill Giant"])
    bears, lions = scenario.battlefield(P1, ["Grizzly Bears", "Savannah Lions"])
    scenario.tap(bears)
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, giant)
    state = scenario.build()
    assert may_block(state) == (lions,)
    assert not block_allowed(state, bears, giant)

    scenario = Scenario(2)
    (giant,) = scenario.battlefield(P0, ["Hill Giant"])
    (bears,) = scenario.battlefield(P1, ["Grizzly Bears"])
    scenario.tap(bears)
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, giant)
    state = scenario.build()
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION
    assert combat_of(state).attackers[giant].blocked is False


def test_509_1a_a_creature_blocks_only_one_attacker() -> None:
    """Hill Giant and Grizzly Bears attack P1; P1's Test Wall may block either, but only one
    (509.1a): its maximum is 1, and a declaration making it block both is refused, changing
    nothing (733)."""
    scenario = Scenario(2)
    giant, bears = scenario.battlefield(P0, ["Hill Giant", "Grizzly Bears"])
    (wall,) = scenario.battlefield(P1, ["Test Wall"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, giant, bears)
    state = scenario.build()
    assert blockable(state, wall) == (giant, bears)
    assert block_space(state).maxima == (1,)
    request = request_of(state)
    with pytest.raises(InvalidAnswer):
        submit(state, answer(state, Assignment(((0, 1),))))
    assert request_of(state) == request
    assert combat_of(state).blockers == {}
    declare_blockers(state, {wall: (bears,)})
    combat = combat_of(state)
    assert (combat.attackers[giant].blocked, combat.attackers[bears].blocked) == (False, True)


def test_509_1a_declaring_no_blockers_leaves_every_attacker_unblocked() -> None:
    """P1 may declare no blockers ("if any", 509.1a): the attackers become unblocked (509.1h)
    and nothing blocks."""
    scenario = Scenario(2)
    giant, bears = scenario.battlefield(P0, ["Hill Giant", "Grizzly Bears"])
    scenario.battlefield(P1, ["Test Wall"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, giant, bears)
    state = scenario.build()
    declare_blockers(state, {})
    combat = combat_of(state)
    assert combat.blockers == {}
    assert [combat.attackers[a].blocked for a in (giant, bears)] == [False, False]


def test_509_1a_two_creatures_may_block_one_attacker() -> None:
    """Two blockers may block the same attacker: each picks it (509.1a's "one creature for it
    to block" is per blocker)."""
    scenario = Scenario(2)
    (giant,) = scenario.battlefield(P0, ["Hill Giant"])
    bears, lions = scenario.battlefield(P1, ["Grizzly Bears", "Savannah Lions"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, giant)
    state = scenario.build()
    declare_blockers(state, {bears: (giant,), lions: (giant,)})
    assert combat_of(state).blockers_of(giant) == (bears, lions)


def test_702_3b_a_creature_with_defender_can_block() -> None:
    """Wall of Stone has defender, which stops it attacking (702.3b), not blocking."""
    scenario = Scenario(2)
    (giant,) = scenario.battlefield(P0, ["Hill Giant"])
    (wall,) = scenario.battlefield(P1, ["Wall of Stone"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, giant)
    state = scenario.build()
    assert may_block(state) == (wall,)
    declare_blockers(state, {wall: (giant,)})
    assert combat_of(state).blockers_of(giant) == (wall,)


def test_509_1a_a_noncreature_and_the_attacking_players_creatures_cant_block() -> None:
    """Only a creature a defending player controls may block (509.1a, 506.3): P1's Sol Ring
    isn't offered, nor is P0's own untapped Grizzly Bears; nothing blocks outside a combat."""
    scenario = Scenario(2)
    giant, own = scenario.battlefield(P0, ["Hill Giant", "Grizzly Bears"])
    ring, wall = scenario.battlefield(P1, ["Sol Ring", "Test Wall"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, giant)
    state = scenario.build()
    assert may_block(state) == (wall,)
    assert not block_allowed(state, ring, giant)
    assert not block_allowed(state, own, giant, P0)
    assert not block_allowed(state, own, giant, P1)
    assert not block_allowed(state, wall, own)  # not an attacking creature

    scenario = Scenario(2)
    (giant,) = scenario.battlefield(P0, ["Hill Giant"])
    (wall,) = scenario.battlefield(P1, ["Test Wall"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    assert not block_allowed(scenario.build(), wall, giant)


# --- 509.1h ------------------------------------------------------------------------------------


def test_509_1h_blocked_stays_blocked_when_its_blocker_leaves() -> None:
    """Hill Giant attacks P1 and is blocked by Grizzly Bears. The Bears then die (here: moved to
    the graveyard in the declare blockers step): the Giant stays blocked (509.1h) and, with no
    creature blocking it, deals no combat damage (510.1c): P1 stays at 20."""
    scenario = Scenario(2)
    (giant,) = scenario.battlefield(P0, ["Hill Giant"])
    (bears,) = scenario.battlefield(P1, ["Grizzly Bears"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, giant)
    state = scenario.build()
    declare_blockers(state, {bears: (giant,)})
    move_object(state, bears, Zone.graveyard(P1))
    combat = combat_of(state)
    assert combat.blockers == {}
    assert combat.attackers[giant].blocked is True
    pass_to(state, Phase.POSTCOMBAT_MAIN)
    assert state.player(P1).life == 20


# --- 702.16f, 702.16j: protection's blocking part ----------------------------------------------


def test_702_16f_protection_from_artifacts_cant_be_blocked_by_an_artifact_creature() -> None:
    """Nacatl Savage (protection from artifacts) attacks P1: P1's Darksteel Myr, an artifact
    creature, can't block it (702.16f); P1's Grizzly Bears can."""
    scenario = Scenario(2)
    (savage,) = scenario.battlefield(P0, ["Nacatl Savage"])
    myr, bears = scenario.battlefield(P1, ["Darksteel Myr", "Grizzly Bears"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, savage)
    state = scenario.build()
    assert may_block(state) == (bears,)
    verdict = legality.allowed(state, legality.BlockAction(P1, myr, savage))
    assert not verdict.allowed and "702.16f" in verdict.rules


def test_702_16f_protection_from_red_cant_be_blocked_by_a_red_creature() -> None:
    """Repentant Blacksmith (protection from red) and Hill Giant attack P1, whose Raging Goblin
    (red) may block the Giant but not the Blacksmith (702.16f). P1's Palace Guard (white) may
    block both."""
    scenario = Scenario(2)
    smith, giant = scenario.battlefield(P0, ["Repentant Blacksmith", "Hill Giant"])
    goblin, guard = scenario.battlefield(P1, ["Raging Goblin", "Palace Guard"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, smith, giant)
    state = scenario.build()
    assert blockable(state, goblin) == (giant,)
    assert blockable(state, guard) == (smith, giant)


def test_702_16j_protection_from_everything_cant_be_blocked() -> None:
    """Test Untouchable (protection from everything) attacks P1: no creature can block it
    (702.16j), so with only it attacking P1 isn't asked and it is unblocked."""
    scenario = Scenario(2)
    (untouchable,) = scenario.battlefield(P0, ["Test Untouchable"])
    (bears,) = scenario.battlefield(P1, ["Grizzly Bears"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, untouchable)
    state = scenario.build()
    verdict = legality.allowed(state, legality.BlockAction(P1, bears, untouchable))
    assert not verdict.allowed and "702.16j" in verdict.rules
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION
    assert combat_of(state).attackers[untouchable].blocked is False


def test_702_16f_protection_on_the_blocker_doesnt_stop_it_blocking() -> None:
    """Repentant Blacksmith (protection from red) may block Raging Goblin (red): 702.16f is about
    attacking creatures with protection. (The Goblin's damage to it would be prevented, 702.16e:
    a gap until M6, not reached here.)"""
    scenario = Scenario(2)
    (goblin,) = scenario.battlefield(P0, ["Raging Goblin"])
    (smith,) = scenario.battlefield(P1, ["Repentant Blacksmith"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, goblin)
    state = scenario.build()
    assert blockable(state, smith) == (goblin,)


# --- 802.4: several defending players ----------------------------------------------------------


def test_802_4_defending_players_declare_in_apnap_order() -> None:
    """Four players; P0 attacks P1 and P3 (P2 isn't attacked). P1 declares first, then P3 (APNAP
    order, 802.4); P2, not attacked, isn't asked. Each declaration is applied as it is made:
    after P1's, the attacker of P1 is fixed (blocked), the attacker of P3 still undecided."""
    scenario = Scenario(4)
    giant, bears = scenario.battlefield(P0, ["Hill Giant", "Grizzly Bears"])
    (wall1,) = scenario.battlefield(P1, ["Test Wall"])
    scenario.battlefield(P2, ["Test Wall"])
    (wall3,) = scenario.battlefield(P3, ["Test Wall"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, giant)
    scenario.attacking(P3, bears)
    state = scenario.build()
    first = request_of(state)
    assert (first.kind, first.player) == (DecisionKind.DECLARE_BLOCKERS, P1)
    declare_blockers(state, {wall1: (giant,)})
    combat = combat_of(state)
    assert (combat.attackers[giant].blocked, combat.attackers[bears].blocked) == (True, None)
    second = request_of(state)
    assert (second.kind, second.player) == (DecisionKind.DECLARE_BLOCKERS, P3)
    declare_blockers(state, {wall3: (bears,)})
    combat = combat_of(state)
    assert combat.blockers_of(giant) == (wall1,) and combat.blockers_of(bears) == (wall3,)
    assert [r.defending_player for r in records(state, BlockersDeclared)] == [P1, P3]
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION


def test_802_4a_they_block_only_creatures_attacking_them() -> None:
    """Three players; Hill Giant attacks P1 and Grizzly Bears attack P2. P1's Test Wall may block
    only the Giant, P2's only the Bears (802.4a); P1 can't block the Bears and P2's creatures
    aren't P1's to declare."""
    scenario = Scenario(3)
    giant, bears = scenario.battlefield(P0, ["Hill Giant", "Grizzly Bears"])
    (wall1,) = scenario.battlefield(P1, ["Test Wall"])
    (wall2,) = scenario.battlefield(P2, ["Test Wall"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, giant)
    scenario.attacking(P2, bears)
    state = scenario.build()
    assert may_block(state) == (wall1,)
    assert blockable(state, wall1) == (giant,)
    assert not block_allowed(state, wall1, bears)
    assert not block_allowed(state, wall2, giant, P1)
    assert not block_allowed(state, wall2, giant, P2)
    declare_blockers(state, {})
    assert request_of(state).player == P2
    assert may_block(state) == (wall2,) and blockable(state, wall2) == (bears,)


def test_802_4_a_defending_player_with_no_possible_block_isnt_asked() -> None:
    """Three players; P0 attacks P1 and P2. P1's only creature is tapped, so P1 isn't asked;
    P2 is. After P2's declaration the attacker of P1 is unblocked too (509.1h)."""
    scenario = Scenario(3)
    giant, bears = scenario.battlefield(P0, ["Hill Giant", "Grizzly Bears"])
    (tapped,) = scenario.battlefield(P1, ["Test Wall"])
    (wall2,) = scenario.battlefield(P2, ["Test Wall"])
    scenario.tap(tapped)
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, giant)
    scenario.attacking(P2, bears)
    state = scenario.build()
    assert request_of(state).player == P2
    declare_blockers(state, {wall2: (bears,)})
    combat = combat_of(state)
    assert (combat.attackers[giant].blocked, combat.attackers[bears].blocked) == (False, True)


def test_800_4a_a_defending_player_leaving_while_another_declares() -> None:
    """Three players; P0 attacks P1 and P2. P1 blocks the Giant with Test Wall. While P2 is
    declaring, P1 concedes: P1's Wall leaves (800.4a, 506.4), the Giant stays blocked (509.1h),
    and P2 is asked again (104.3a) and declares; the state stays consistent."""
    scenario = Scenario(3)
    giant, bears = scenario.battlefield(P0, ["Hill Giant", "Grizzly Bears"])
    (wall1,) = scenario.battlefield(P1, ["Test Wall"])
    (wall2,) = scenario.battlefield(P2, ["Test Wall"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, giant)
    scenario.attacking(P2, bears)
    state = scenario.build()
    declare_blockers(state, {wall1: (giant,)})
    old = request_of(state)
    assert old.player == P2
    concede(state, P1)
    again = request_of(state)
    assert (again.kind, again.player) == (DecisionKind.DECLARE_BLOCKERS, P2)
    assert again.id != old.id
    declare_blockers(state, {wall2: (bears,)})
    combat = combat_of(state)
    assert combat.attackers[giant].blocked is True and combat.blockers_of(giant) == ()
    assert combat.blockers_of(bears) == (wall2,)
    assert invariant_violations(state) == []


def test_509_1_a_full_combat_from_attacks_to_damage() -> None:
    """Hill Giant (3/3) and Grizzly Bears (2/2) attack P1; P1's Savannah Lions (2/1) blocks the
    Bears. The Giant deals 3 to P1; the Bears and the Lions deal 2 to each other and both die
    (510.2, 704.5g)."""
    scenario = Scenario(2)
    giant, bears = scenario.battlefield(P0, ["Hill Giant", "Grizzly Bears"])
    (lions,) = scenario.battlefield(P1, ["Savannah Lions"])
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    declare_attackers(state, {giant: P1, bears: P1})
    pass_to(state, Phase.COMBAT, Step.DECLARE_BLOCKERS)
    assert request_of(state).kind is DecisionKind.DECLARE_BLOCKERS
    assert block_answer(state, {lions: (bears,)}).picks == ((1,),)
    declare_blockers(state, {lions: (bears,)})
    pass_to(state, Phase.POSTCOMBAT_MAIN)
    assert state.player(P1).life == 17
    assert all(obj not in state.battlefield for obj in (bears, lions))
    assert giant in state.battlefield


# --- From the test review: APNAP with another active player, concessions, 302.6, views ---------


def test_802_4_apnap_order_starts_after_the_active_player() -> None:
    """Four players with P2 active (101.4: APNAP order is P2, P3, P0, P1). P2 attacks P3, P0 and
    P1, each of whom controls a Palace Guard: they declare in the order P3, P0, P1 (802.4), not
    in seat order."""
    scenario = Scenario(4)
    attackers = scenario.battlefield(P2, ["Grizzly Bears", "Hill Giant", "Savannah Lions"])
    for player in (P0, P1, P3):
        scenario.battlefield(player, ["Palace Guard"])
    scenario.at(Step.DECLARE_BLOCKERS, active=P2, begin=True)
    scenario.attacking(P0, attackers[0])
    scenario.attacking(P1, attackers[1])
    scenario.attacking(P3, attackers[2])
    state = scenario.build()
    order: list[PlayerId] = []
    while request_of(state).kind is DecisionKind.DECLARE_BLOCKERS:
        order.append(request_of(state).player)
        declare_blockers(state, {})
    assert order == [P3, P0, P1]


def test_800_4a_the_player_declaring_concedes() -> None:
    """Three players; P0 attacks P1 (the Giant) and P2 (the Bears). P1 concedes while asked to
    declare (104.3a): P1 leaves (800.4a) and P2 is asked next. The Giant, attacking a player who
    left, ends up unblocked (509.1h) and deals no damage (800.4e)."""
    scenario = Scenario(3)
    giant, bears = scenario.battlefield(P0, ["Hill Giant", "Grizzly Bears"])
    scenario.battlefield(P1, ["Test Wall"])
    (wall2,) = scenario.battlefield(P2, ["Test Wall"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, giant)
    scenario.attacking(P2, bears)
    state = scenario.build()
    assert request_of(state).player == P1
    concede(state, P1)
    request = request_of(state)
    assert (request.kind, request.player) == (DecisionKind.DECLARE_BLOCKERS, P2)
    declare_blockers(state, {wall2: (bears,)})
    combat = combat_of(state)
    assert (combat.attackers[giant].blocked, combat.attackers[bears].blocked) == (False, True)
    pass_to(state, Phase.POSTCOMBAT_MAIN)
    assert state.player(P0).life == 20 and state.player(P2).life == 20
    assert invariant_violations(state) == []


def test_800_4j_the_active_player_concedes_during_the_declaration() -> None:
    """Three players; P0 attacks P1 and concedes while P1 is asked to declare. P0's creatures
    leave the game (800.4a), so no creature is attacking: P1 isn't asked again (nothing to
    block), the turn continues without an active player (800.4j), and the state stays
    consistent."""
    scenario = Scenario(3)
    (giant,) = scenario.battlefield(P0, ["Hill Giant"])
    scenario.battlefield(P1, ["Test Wall"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, giant)
    state = scenario.build()
    concede(state, P0)
    assert combat_of(state).attackers == {} and combat_of(state).blockers == {}
    assert request_of(state).kind is not DecisionKind.DECLARE_BLOCKERS
    assert invariant_violations(state) == []


def test_302_6_a_creature_that_just_arrived_can_block() -> None:
    """Summoning sickness limits attacking and {T} abilities (302.6), not blocking: P1's Grizzly
    Bears, under P1's control only since this turn, may block."""
    scenario = Scenario(2)
    (giant,) = scenario.battlefield(P0, ["Hill Giant"])
    (bears,) = scenario.battlefield(P1, ["Grizzly Bears"], entered_turn=3)
    scenario.at(Step.DECLARE_BLOCKERS, number=3, begin=True)
    scenario.attacking(P1, giant)
    state = scenario.build()
    assert may_block(state) == (bears,)


def test_702_16j_a_creature_with_protection_from_everything_can_block() -> None:
    """Protection from everything stops the creature being blocked, not blocking (702.16j):
    Test Untouchable may block Hill Giant."""
    scenario = Scenario(2)
    (giant,) = scenario.battlefield(P0, ["Hill Giant"])
    (untouchable,) = scenario.battlefield(P1, ["Test Untouchable"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, giant)
    state = scenario.build()
    assert blockable(state, untouchable) == (giant,)


def test_509_1g_every_player_sees_the_blocks() -> None:
    """The combat state is public (design.md §17.18): after P1's declaration, every player's
    view shows the Bears blocking the Giant, and the Giant blocked."""
    scenario = Scenario(3)
    (giant,) = scenario.battlefield(P0, ["Hill Giant"])
    (bears,) = scenario.battlefield(P1, ["Grizzly Bears"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, giant)
    state = scenario.build()
    declare_blockers(state, {bears: (giant,)})
    for player in (P0, P1, P2):
        view = view_for(state, player).combat
        assert view is not None
        assert view.blockers == (BlockRecord(bears, (giant,)),)
        assert [record.blocked for record in view.attackers] == [True]
