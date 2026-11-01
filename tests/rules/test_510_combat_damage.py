"""510: the combat damage step (M3.2: unblocked attackers; M3.3: blocked attackers and blockers).

From the pinned CR:

- 510.1a: each attacking creature assigns combat damage equal to its power; one that would
  assign 0 or less assigns none.
- 510.1b: an unblocked creature assigns its combat damage to the player it attacks.
- 510.1: the active player announces how each attacking creature assigns its combat damage,
  then the defending player how each blocking creature does; 802.5: in APNAP order.
- 510.1c: a blocked creature assigns its combat damage to the creatures blocking it: none if
  none is left; all of it to the one blocker; divided as its controller chooses among two or more
  (the example: a 4-power attacker blocked by a 2/3 and a 1/1 has exactly five divisions).
- 510.1d: a blocking creature assigns its combat damage to the creatures it blocks, the same way.
- 510.1e: the total assignment is checked; an illegal one is refused and the game returns to
  before the player began assigning (733).
- 510.2: all combat damage that has been assigned is dealt simultaneously: one set of events,
  ``DamageDealt`` with ``combat=True``, one per source (120.4b).
- 120.3a: damage dealt to a player makes them lose that much life; 704.5a: a player with 0 or
  less life loses the game.
- 800.4e: combat damage that would be assigned to a player who has left the game isn't
  assigned.
- 903.10a: a player dealt 21 or more combat damage by the same commander loses. Commander damage
  isn't tallied until M7, so combat damage from a commander to a player is a gap.
"""

from __future__ import annotations

import pytest

from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import Amounts, AmountsEach, ObjectOption
from resolve.engine.api import submit
from resolve.engine.concede import concede
from resolve.errors import InvalidAnswer, NotImplementedRule
from resolve.events import pipeline
from resolve.events.base import Event
from resolve.events.damage import DamageDealt
from resolve.events.game import PlayerLost
from resolve.state.combat import remove_from_combat
from resolve.state.config import GameConfig
from resolve.state.game import GameState
from resolve.state.ids import PlayerId
from resolve.state.turn import Phase, Step
from resolve.state.zones import BATTLEFIELD
from resolve.tasks import TaskResult
from tests.casting_support import records
from tests.combat_support import (
    assign_damage,
    damage_answer,
    damage_recipients,
    damage_sources,
    damage_space,
    declare_attackers,
    pass_to,
)
from tests.game_fixtures import answer, request_of
from tests.scenario import Scenario

P0, P1, P2, P3 = PlayerId(0), PlayerId(1), PlayerId(2), PlayerId(3)


def test_510_1b_an_unblocked_attacker_deals_its_power_to_the_player() -> None:
    """Hill Giant (3/3) attacks P1 and isn't blocked: it deals 3 combat damage to P1, 20 -> 17
    (510.1a-b, 120.3a)."""
    scenario = Scenario(2)
    (giant,) = scenario.battlefield(P0, ["Hill Giant"])
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    declare_attackers(state, {giant: P1})
    pass_to(state, Phase.POSTCOMBAT_MAIN)
    (dealt,) = records(state, DamageDealt)
    assert (dealt.source, dealt.to_players, dealt.to_objects) == (giant, ((P1, 3),), ())
    assert dealt.combat
    assert "510.2" in dealt.rules
    assert state.player(P1).life == 17 and state.player(P0).life == 20


def test_510_1a_a_creature_with_0_power_deals_no_damage() -> None:
    """Darksteel Myr (0/1) attacks: it assigns no combat damage (510.1a), so no damage event."""
    scenario = Scenario(2)
    (myr,) = scenario.battlefield(P0, ["Darksteel Myr"])
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    declare_attackers(state, {myr: P1})
    pass_to(state, Phase.POSTCOMBAT_MAIN)
    assert records(state, DamageDealt) == []
    assert state.player(P1).life == 20


def test_510_2_combat_damage_is_dealt_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Grizzly Bears and Hill Giant attack P1: their damage is one set of simultaneous events,
    one ``DamageDealt`` per source in declaration order (510.2, 120.4b), 20 -> 15."""
    batches: list[tuple[Event, ...]] = []
    run = pipeline.ApplyEvents.run

    def spy(self: pipeline.ApplyEvents, state: GameState) -> TaskResult:
        batches.append(self.events)
        return run(self, state)

    monkeypatch.setattr(pipeline.ApplyEvents, "run", spy)
    scenario = Scenario(2)
    bears, giant = scenario.battlefield(P0, ["Grizzly Bears", "Hill Giant"])
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    declare_attackers(state, {bears: P1, giant: P1})
    pass_to(state, Phase.POSTCOMBAT_MAIN)
    damage = [batch for batch in batches if any(isinstance(e, DamageDealt) for e in batch)]
    assert len(damage) == 1
    (batch,) = damage
    assert all(isinstance(event, DamageDealt) and event.combat for event in batch)
    assert [(e.source, e.to_players) for e in batch if isinstance(e, DamageDealt)] == [
        (bears, ((P1, 2),)),
        (giant, ((P1, 3),)),
    ]
    assert state.player(P1).life == 15


def test_704_5a_combat_damage_ends_the_game() -> None:
    """P1 at 3 life is dealt 3 by Hill Giant: 704.5a, they lose and P0 wins (104.2a)."""
    scenario = Scenario(2)
    (giant,) = scenario.battlefield(P0, ["Hill Giant"])
    scenario.life(P1, 3)
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    declare_attackers(state, {giant: P1})
    pass_to(state, Phase.POSTCOMBAT_MAIN)
    assert state.result is not None
    (lost,) = records(state, PlayerLost)
    assert lost.player == P1 and lost.rules[0] == "704.5a"
    assert state.result.winners == (P0,)


def test_800_4e_damage_to_a_player_who_left_isnt_assigned() -> None:
    """Three players: Grizzly Bears attacks P1 and Hill Giant P2. P1 concedes in the declare
    attackers step: the Bears stay attacking (P1's leaving doesn't remove them from combat) but
    their damage to P1 isn't assigned (800.4e); the Giant deals 3 to P2."""
    scenario = Scenario(3)
    bears, giant = scenario.battlefield(P0, ["Grizzly Bears", "Hill Giant"])
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    declare_attackers(state, {bears: P1, giant: P2})
    concede(state, P1)
    turn = state.turn
    assert turn is not None and turn.combat is not None and bears in turn.combat.attackers
    pass_to(state, Phase.POSTCOMBAT_MAIN)
    (dealt,) = records(state, DamageDealt)
    assert (dealt.source, dealt.to_players) == (giant, ((P2, 3),))
    assert state.player(P2).life == 17


def test_510_1c_a_blocked_attacker_whose_blockers_left_deals_no_damage() -> None:
    """Grizzly Bears was blocked by Test Wall, which has left combat (removed from the combat
    state as the scenario is set up): the Bears stay blocked (509.1h) and, with no creature
    blocking them, assign no combat damage (510.1c). Hill Giant, unblocked, deals its 3."""
    scenario = Scenario(2)
    bears, giant = scenario.battlefield(P0, ["Grizzly Bears", "Hill Giant"])
    (wall,) = scenario.battlefield(P1, ["Test Wall"])
    scenario.at(Step.COMBAT_DAMAGE, begin=True)
    scenario.attacking(P1, bears, giant)
    scenario.blocking(wall, bears)
    turn = scenario._state.turn  # pyright: ignore[reportPrivateUsage]
    assert turn is not None and turn.combat is not None
    del turn.combat.blockers[wall]
    state = scenario.build()
    assert [(e.source, e.to_players) for e in records(state, DamageDealt)] == [(giant, ((P1, 3),))]
    assert state.player(P1).life == 17


def test_903_10a_combat_damage_from_a_commander_is_a_gap_until_m7() -> None:
    """In a Commander game P0's commander, Grizzly Bears, attacks P1 unblocked: the combat
    damage it would deal to P1 must be tallied for 903.10a, which is M7's, so it is a gap. A
    creature that isn't a commander deals its damage as normal in the same game."""
    scenario = Scenario(2, config=GameConfig.commander_game())
    commander = scenario.commander(P0, "Grizzly Bears", zone=BATTLEFIELD)
    scenario.at(Step.COMBAT_DAMAGE, begin=True)
    scenario.attacking(P1, commander)
    with pytest.raises(NotImplementedRule) as gap:
        scenario.build()
    assert gap.value.rule == "903.10a"

    scenario = Scenario(2, config=GameConfig.commander_game())
    scenario.commander(P0, "Grizzly Bears")
    (giant,) = scenario.battlefield(P0, ["Hill Giant"])
    scenario.at(Step.COMBAT_DAMAGE, begin=True)
    scenario.attacking(P1, giant)
    state = scenario.build()
    assert state.player(P1).life == 40 - 3


# --- From the test review ---------------------------------------------------------------------


def test_510_3_damage_is_dealt_before_the_active_player_gets_priority() -> None:
    """510.2-510.3: combat damage is dealt as the step's turn-based action; when P0 first gets
    priority in the combat damage step, P1 has already lost the 3 life."""
    scenario = Scenario(2)
    (giant,) = scenario.battlefield(P0, ["Hill Giant"])
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    declare_attackers(state, {giant: P1})
    pass_to(state, Phase.COMBAT, Step.COMBAT_DAMAGE)
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION
    assert request_of(state).player == P0
    assert state.player(P1).life == 17


def test_704_5a_two_players_dealt_lethal_combat_damage_lose_together() -> None:
    """Four players: Grizzly Bears hits P1 (2 life) and Savannah Lions hits P2 (2 life) in the
    same combat damage (510.2). Both lose in the same state-based-action check (704.3, 704.5a),
    and the game goes on with P0 and P3."""
    scenario = Scenario(4)
    bears, lions = scenario.battlefield(P0, ["Grizzly Bears", "Savannah Lions"])
    scenario.life(P1, 2)
    scenario.life(P2, 2)
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    declare_attackers(state, {bears: P1, lions: P2})
    pass_to(state, Phase.COMBAT, Step.COMBAT_DAMAGE)
    log = [entry.record for entry in state.event_log]
    losses = [(i, r.player) for i, r in enumerate(log) if isinstance(r, PlayerLost)]
    assert [player for _, player in losses] == [P1, P2]
    assert losses[1][0] == losses[0][0] + 1, "one check, both losses together"
    assert state.result is None
    assert [state.player(p).left_game for p in (P0, P1, P2, P3)] == [False, True, True, False]


def test_903_10a_the_gap_stops_all_combat_damage() -> None:
    """Hill Giant (not a commander) is declared before P0's commander, Grizzly Bears: the gap is
    raised before any damage is dealt (510.2: all at once), so the Giant deals none either. A
    commander with 0 power assigns no combat damage (510.1a), so it raises no gap."""
    scenario = Scenario(2, config=GameConfig.commander_game())
    (giant,) = scenario.battlefield(P0, ["Hill Giant"])
    commander = scenario.commander(P0, "Grizzly Bears", zone=BATTLEFIELD)
    scenario.at(Step.COMBAT_DAMAGE, begin=True)
    scenario.attacking(P1, giant, commander)
    with pytest.raises(NotImplementedRule):
        scenario.build()
    assert scenario._state.player(P1).life == 40  # pyright: ignore[reportPrivateUsage]
    assert records(scenario._state, DamageDealt) == []  # pyright: ignore[reportPrivateUsage]

    scenario = Scenario(2, config=GameConfig.commander_game())
    myr = scenario.commander(P0, "Darksteel Myr", zone=BATTLEFIELD)
    scenario.at(Step.COMBAT_DAMAGE, begin=True)
    scenario.attacking(P1, myr)
    state = scenario.build()
    assert records(state, DamageDealt) == [] and state.player(P1).life == 40


# --- 510.1c-e: damage to and by blocking creatures (M3.3) --------------------------------------


def life(state: GameState, *players: PlayerId) -> list[int]:
    return [state.player(p).life for p in players]


def test_510_1c_one_blocker_takes_all_the_damage_without_a_question() -> None:
    """Hill Giant (3/3) is blocked by Test Wall (0/4) alone: it assigns all 3 to the Wall
    without anyone being asked (510.1c: exactly one blocker), and the Wall, with 0 power,
    assigns none (510.1a). P1 isn't dealt damage."""
    scenario = Scenario(2)
    (giant,) = scenario.battlefield(P0, ["Hill Giant"])
    (wall,) = scenario.battlefield(P1, ["Test Wall"])
    scenario.at(Step.COMBAT_DAMAGE, begin=True)
    scenario.attacking(P1, giant)
    scenario.blocking(wall, giant)
    state = scenario.build()
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION
    (dealt,) = records(state, DamageDealt)
    assert (dealt.source, dealt.to_objects, dealt.to_players) == (giant, ((wall, 3),), ())
    assert dealt.combat and "510.1c" in dealt.rules
    assert state.objects[wall].damage == 3
    assert life(state, P0, P1) == [20, 20]


def test_510_1c_two_blockers_divided_as_the_controller_chooses() -> None:
    """510.1c's example: an attacking 4/3 (Test Regrower) blocked by a 2/3 (Test Spawn) and a
    1/1 (Avacyn's Pilgrim). P0, its controller, is asked to divide its 4 damage between them, in
    the blockers' order; exactly the five divisions the example lists are legal: all 4 to the
    1/1, 1 and 3, 2 each, 3 and 1, all 4 to the 2/3. Assigning 3 and 1 kills both blockers, and
    their 2 + 1 kills the attacker (704.5g)."""
    scenario = Scenario(2)
    (attacker,) = scenario.battlefield(P0, ["Test Regrower"])
    spawn, hunter = scenario.battlefield(P1, ["Test Spawn", "Avacyn's Pilgrim"])
    scenario.at(Step.COMBAT_DAMAGE, begin=True)
    scenario.attacking(P1, attacker)
    scenario.blocking(spawn, attacker)
    scenario.blocking(hunter, attacker)
    state = scenario.build()
    request = request_of(state)
    assert (request.kind, request.player) == (DecisionKind.ASSIGN_COMBAT_DAMAGE, P0)
    assert damage_sources(state) == (attacker,)
    assert damage_recipients(state, attacker) == (ObjectOption(spawn), ObjectOption(hunter))
    (part,) = damage_space(state).parts
    legal: list[tuple[int, int]] = []
    for spawn_amount in range(-1, 6):
        for hunter_amount in range(-1, 6):
            try:
                part.validate(Amounts((spawn_amount, hunter_amount)))
            except InvalidAnswer:
                continue
            legal.append((spawn_amount, hunter_amount))
    assert sorted(legal) == [(0, 4), (1, 3), (2, 2), (3, 1), (4, 0)]
    assign_damage(state, {attacker: {ObjectOption(spawn): 3, ObjectOption(hunter): 1}})
    damage = {e.source: e.to_objects for e in records(state, DamageDealt)}
    assert damage[attacker] == ((spawn, 3), (hunter, 1))
    pass_to(state, Phase.POSTCOMBAT_MAIN)  # P1 orders the two cards entering their graveyard
    assert list(state.battlefield) == []  # 704.5g: all three are dealt lethal damage


def test_510_1c_all_the_damage_to_one_of_two_blockers_omits_the_other() -> None:
    """Assigning all 3 of Hill Giant's damage to the first of two blockers deals 0 to the
    second, which isn't dealt damage at all (120.8: 0 damage isn't dealt)."""
    scenario = Scenario(2)
    (giant,) = scenario.battlefield(P0, ["Hill Giant"])
    wall, bears = scenario.battlefield(P1, ["Test Wall", "Grizzly Bears"])
    scenario.at(Step.COMBAT_DAMAGE, begin=True)
    scenario.attacking(P1, giant)
    scenario.blocking(wall, giant)
    scenario.blocking(bears, giant)
    state = scenario.build()
    assign_damage(state, {giant: {ObjectOption(wall): 3}})
    damage = {e.source: e.to_objects for e in records(state, DamageDealt)}
    assert damage[giant] == ((wall, 3),)
    assert state.objects[wall].damage == 3
    assert state.objects[bears].damage == 0
    assert state.objects[giant].damage == 2  # the Bears' damage; the Wall has 0 power


def test_510_1d_palace_guard_divides_its_damage_between_two_attackers() -> None:
    """Palace Guard (1/4) blocks Grizzly Bears and Savannah Lions: P1, its controller, divides
    its 1 damage between them (510.1d), here to the Lions, which die (2/1). The Bears and the
    Lions each assign all their damage to the Guard (one blocker each, 510.1c): 2 + 2 = 4,
    so the Guard dies too."""
    scenario = Scenario(2)
    bears, lions = scenario.battlefield(P0, ["Grizzly Bears", "Savannah Lions"])
    (guard,) = scenario.battlefield(P1, ["Palace Guard"])
    scenario.at(Step.COMBAT_DAMAGE, begin=True)
    scenario.attacking(P1, bears, lions)
    scenario.blocking(guard, bears, lions)
    state = scenario.build()
    request = request_of(state)
    assert (request.kind, request.player) == (DecisionKind.ASSIGN_COMBAT_DAMAGE, P1)
    assert damage_sources(state) == (guard,)
    assert damage_recipients(state, guard) == (ObjectOption(bears), ObjectOption(lions))
    assign_damage(state, {guard: {ObjectOption(lions): 1}})
    damage = {e.source: e.to_objects for e in records(state, DamageDealt)}
    assert damage == {bears: ((guard, 2),), lions: ((guard, 2),), guard: ((lions, 1),)}
    assert all(obj not in state.battlefield for obj in (lions, guard))
    assert bears in state.battlefield and state.objects[bears].damage == 0


def test_510_1e_a_division_not_adding_up_is_rejected() -> None:
    """A division of Hill Giant's 3 damage that adds up to 2 or 4, gives a negative amount, or
    gives the wrong number of amounts is refused (510.1e), changing nothing: the same request
    stays pending and no damage is dealt."""
    scenario = Scenario(2)
    (giant,) = scenario.battlefield(P0, ["Hill Giant"])
    wall, bears = scenario.battlefield(P1, ["Test Wall", "Grizzly Bears"])
    scenario.at(Step.COMBAT_DAMAGE, begin=True)
    scenario.attacking(P1, giant)
    scenario.blocking(wall, giant)
    scenario.blocking(bears, giant)
    state = scenario.build()
    request = request_of(state)
    for amounts in ((1, 1), (2, 2), (4, -1), (3,), (1, 1, 1)):
        with pytest.raises(InvalidAnswer):
            submit(state, answer(state, AmountsEach((Amounts(amounts),))))
        assert request_of(state) == request
    assert records(state, DamageDealt) == []
    assert damage_answer(state, {giant: {ObjectOption(bears): 3}}).amounts == (Amounts((0, 3)),)


def test_510_2_attacker_and_blocker_deal_damage_at_once_and_both_die(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Grizzly Bears attacks and is blocked by Grizzly Bears: each deals 2 to the other in one
    set of events (510.2), so both are destroyed by the same check (704.5g), neither surviving
    to avoid the other's damage."""
    scenario = Scenario(2)
    (attacker,) = scenario.battlefield(P0, ["Grizzly Bears"])
    (blocker,) = scenario.battlefield(P1, ["Grizzly Bears"])
    scenario.at(Step.COMBAT_DAMAGE, begin=True)
    scenario.attacking(P1, attacker)
    scenario.blocking(blocker, attacker)
    batches: list[tuple[Event, ...]] = []
    real = pipeline.ApplyEvents.run

    def spy(self: pipeline.ApplyEvents, state: GameState) -> TaskResult:
        if any(isinstance(e, DamageDealt) for e in self.events):
            batches.append(self.events)
        return real(self, state)

    monkeypatch.setattr(pipeline.ApplyEvents, "run", spy)
    state = scenario.build()
    (batch,) = batches
    assert [(e.source, e.to_objects) for e in batch if isinstance(e, DamageDealt)] == [
        (attacker, ((blocker, 2),)),
        (blocker, ((attacker, 2),)),
    ]
    assert all(isinstance(e, DamageDealt) and e.combat for e in batch)  # a blocker's too
    assert attacker not in state.battlefield and blocker not in state.battlefield
    assert life(state, P0, P1) == [20, 20]


def test_510_1d_a_blocker_whose_attacker_left_deals_no_damage() -> None:
    """Grizzly Bears blocked Hill Giant, which has left combat: the Bears block nothing and
    assign no combat damage (510.1d); nobody is asked."""
    scenario = Scenario(2)
    (giant,) = scenario.battlefield(P0, ["Hill Giant"])
    (bears,) = scenario.battlefield(P1, ["Grizzly Bears"])
    scenario.at(Step.COMBAT_DAMAGE, begin=True)
    scenario.attacking(P1, giant)
    scenario.blocking(bears, giant)
    remove_from_combat(scenario._state, giant)  # pyright: ignore[reportPrivateUsage]
    state = scenario.build()
    assert records(state, DamageDealt) == []
    assert state.objects[giant].damage == 0


def test_802_5_damage_assignments_in_apnap_order() -> None:
    """Four players; P0 attacks P1 and P2. P0's Hill Giant is blocked by two of P2's creatures,
    and P1's and P2's Palace Guards each block two attackers. The assignments are asked in APNAP
    order (802.5, 510.1): P0 for the Giant, then P1 for P1's Guard, then P2 for P2's Guard; P3,
    with no creature in combat, isn't asked. All the damage is dealt at once afterwards."""
    scenario = Scenario(4)
    giant, bears, lions, bears2, lions2 = scenario.battlefield(
        P0, ["Hill Giant", "Grizzly Bears", "Savannah Lions", "Grizzly Bears", "Savannah Lions"]
    )
    (guard1,) = scenario.battlefield(P1, ["Palace Guard"])
    guard2, wall, wall2 = scenario.battlefield(P2, ["Palace Guard", "Test Wall", "Test Wall"])
    scenario.at(Step.COMBAT_DAMAGE, begin=True)
    scenario.attacking(P1, bears, lions)
    scenario.attacking(P2, giant, bears2, lions2)
    scenario.blocking(guard1, bears, lions)
    scenario.blocking(guard2, bears2, lions2)
    scenario.blocking(wall, giant)
    scenario.blocking(wall2, giant)
    state = scenario.build()
    order: list[PlayerId] = []
    request = request_of(state)
    assert request.kind is DecisionKind.ASSIGN_COMBAT_DAMAGE
    order.append(request.player)
    assert damage_sources(state) == (giant,)
    assign_damage(state, {giant: {ObjectOption(wall): 3}})
    assert records(state, DamageDealt) == []  # 510.2: nothing is dealt until all have assigned
    order.append(request_of(state).player)
    assert damage_sources(state) == (guard1,)
    assign_damage(state, {guard1: {ObjectOption(lions): 1}})
    order.append(request_of(state).player)
    assert damage_sources(state) == (guard2,)
    assign_damage(state, {guard2: {ObjectOption(bears2): 1}})
    assert order == [P0, P1, P2]
    damage = {e.source: e.to_objects for e in records(state, DamageDealt)}
    assert damage[giant] == ((wall, 3),)
    assert damage[guard1] == ((lions, 1),) and damage[guard2] == ((bears2, 1),)
    assert lions not in state.battlefield
    assert life(state, P1, P2, P3) == [20, 20, 20]


def test_800_4a_a_player_leaving_during_the_assignment_keeps_announced_ones() -> None:
    """Three players; P0 attacks P1 and P2. P0 has assigned the Giant's damage between P2's two
    Walls; P1, asked for their Palace Guard, concedes instead. P1's Guard leaves (800.4a); P0
    isn't asked again (P0's assignment was announced, 510.1), and the damage is dealt: the
    Giant's to the Walls, the Bears' and Lions' to nothing (blocked, no blocker, 510.1c)."""
    scenario = Scenario(3)
    giant, bears, lions = scenario.battlefield(
        P0, ["Hill Giant", "Grizzly Bears", "Savannah Lions"]
    )
    (guard,) = scenario.battlefield(P1, ["Palace Guard"])
    wall, wall2 = scenario.battlefield(P2, ["Test Wall", "Test Wall"])
    scenario.at(Step.COMBAT_DAMAGE, begin=True)
    scenario.attacking(P1, bears, lions)
    scenario.attacking(P2, giant)
    scenario.blocking(guard, bears, lions)
    scenario.blocking(wall, giant)
    scenario.blocking(wall2, giant)
    state = scenario.build()
    assign_damage(state, {giant: {ObjectOption(wall): 1, ObjectOption(wall2): 2}})
    assert request_of(state).player == P1
    concede(state, P1)
    damage = {e.source: e.to_objects for e in records(state, DamageDealt)}
    assert damage == {giant: ((wall, 1), (wall2, 2))}
    assert life(state, P0, P2) == [20, 20]


# --- From the test review: recipients that leave, 0 power, whole assignments, gaps -------------


def test_800_4a_an_announced_assignment_stands_when_another_player_leaves() -> None:
    """Four players; P0 attacks P2 with Hill Giant A, Grizzly Bears and Savannah Lions and P3
    with Hill Giant B. P2's two Walls block Giant A and P2's Palace Guard the Bears and the
    Lions; P3's two Walls block Giant B. P0 assigns both Giants' damage in one decision (A: 1
    and 2; B: all 3 to P3's first Wall), then P2, asked for the Guard, concedes. P0's
    assignment was announced (510.1) and leaving the game undoes no announcement (800.4a;
    510.1e's return is only for an illegal assignment): P0 isn't asked again, Giant A's damage
    to P2's departed Walls isn't dealt, and Giant B deals 3 to P3's first Wall as announced."""
    scenario = Scenario(4)
    giant_a, bears, lions, giant_b = scenario.battlefield(
        P0, ["Hill Giant", "Grizzly Bears", "Savannah Lions", "Hill Giant"]
    )
    wall_a1, wall_a2, guard = scenario.battlefield(P2, ["Test Wall", "Test Wall", "Palace Guard"])
    wall_b1, wall_b2 = scenario.battlefield(P3, ["Test Wall", "Test Wall"])
    scenario.at(Step.COMBAT_DAMAGE, begin=True)
    scenario.attacking(P2, giant_a, bears, lions)
    scenario.attacking(P3, giant_b)
    scenario.blocking(wall_a1, giant_a)
    scenario.blocking(wall_a2, giant_a)
    scenario.blocking(guard, bears, lions)
    scenario.blocking(wall_b1, giant_b)
    scenario.blocking(wall_b2, giant_b)
    state = scenario.build()
    assert damage_sources(state) == (giant_a, giant_b)
    assign_damage(
        state,
        {
            giant_a: {ObjectOption(wall_a1): 1, ObjectOption(wall_a2): 2},
            giant_b: {ObjectOption(wall_b1): 3},
        },
    )
    assert request_of(state).player == P2
    concede(state, P2)
    assert request_of(state).kind is not DecisionKind.ASSIGN_COMBAT_DAMAGE
    damage = {e.source: e.to_objects for e in records(state, DamageDealt)}
    assert damage == {giant_b: ((wall_b1, 3),)}
    assert state.objects[wall_b1].damage == 3 and state.objects[wall_b2].damage == 0


def test_510_1c_two_blockers_down_to_one_takes_all_without_a_question() -> None:
    """Hill Giant was blocked by Test Wall and Grizzly Bears; the Bears have left combat. With
    exactly one creature blocking it now, the Giant assigns all 3 to the Wall and nobody is
    asked (510.1c: the blockers it has now)."""
    scenario = Scenario(2)
    (giant,) = scenario.battlefield(P0, ["Hill Giant"])
    wall, bears = scenario.battlefield(P1, ["Test Wall", "Grizzly Bears"])
    scenario.at(Step.COMBAT_DAMAGE, begin=True)
    scenario.attacking(P1, giant)
    scenario.blocking(wall, giant)
    scenario.blocking(bears, giant)
    remove_from_combat(scenario._state, bears)  # pyright: ignore[reportPrivateUsage]
    state = scenario.build()
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION
    damage = {e.source: e.to_objects for e in records(state, DamageDealt)}
    assert damage == {giant: ((wall, 3),)}


def test_510_1d_palace_guard_blocking_two_down_to_one_deals_all_to_it() -> None:
    """Palace Guard blocked Grizzly Bears and Savannah Lions; the Lions have left combat. The
    Guard blocks only the Bears now and deals its 1 to them without a question (510.1d)."""
    scenario = Scenario(2)
    bears, lions = scenario.battlefield(P0, ["Grizzly Bears", "Savannah Lions"])
    (guard,) = scenario.battlefield(P1, ["Palace Guard"])
    scenario.at(Step.COMBAT_DAMAGE, begin=True)
    scenario.attacking(P1, bears, lions)
    scenario.blocking(guard, bears, lions)
    remove_from_combat(scenario._state, lions)  # pyright: ignore[reportPrivateUsage]
    state = scenario.build()
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION
    damage = {e.source: e.to_objects for e in records(state, DamageDealt)}
    assert damage == {bears: ((guard, 2),), guard: ((bears, 1),)}


def test_510_1a_zero_power_with_two_recipients_isnt_asked() -> None:
    """A creature with 0 power assigns no combat damage (510.1a), however many recipients:
    Darksteel Myr (0/1) blocked by two creatures and Test Wall (0/4) blocking two attackers
    aren't asked about, and deal nothing."""
    scenario = Scenario(2)
    myr, bears, lions = scenario.battlefield(
        P0, ["Darksteel Myr", "Grizzly Bears", "Savannah Lions"]
    )
    wall, giant, spawn = scenario.battlefield(P1, ["Test Wall", "Hill Giant", "Test Spawn"])
    scenario.at(Step.COMBAT_DAMAGE, begin=True)
    scenario.attacking(P1, myr, bears, lions)
    scenario.blocking(giant, myr)
    scenario.blocking(spawn, myr)
    scenario.blocking(wall, bears, lions)
    state = scenario.build()
    assert request_of(state).kind is not DecisionKind.ASSIGN_COMBAT_DAMAGE
    sources = {e.source for e in records(state, DamageDealt)}
    assert myr not in sources and wall not in sources


def test_510_1e_one_decision_checks_the_whole_assignment() -> None:
    """P0's Hill Giant and Test Regrower are each blocked by two creatures: P0 assigns both in
    one decision with two parts (510.1e: the total assignment is checked). A legal first part
    with an illegal second part is refused as a whole, nothing is dealt, and the same request
    stays pending; a legal answer for both is accepted."""
    scenario = Scenario(2)
    giant, regrower = scenario.battlefield(P0, ["Hill Giant", "Test Regrower"])
    w1, w2, w3, w4 = scenario.battlefield(P1, ["Test Wall", "Test Wall", "Test Wall", "Test Wall"])
    scenario.at(Step.COMBAT_DAMAGE, begin=True)
    scenario.attacking(P1, giant, regrower)
    scenario.blocking(w1, giant)
    scenario.blocking(w2, giant)
    scenario.blocking(w3, regrower)
    scenario.blocking(w4, regrower)
    state = scenario.build()
    request = request_of(state)
    assert damage_sources(state) == (giant, regrower)
    assert [part.total for part in damage_space(state).parts] == [3, 4]
    with pytest.raises(InvalidAnswer):
        submit(state, answer(state, AmountsEach((Amounts((3, 0)), Amounts((2, 1))))))
    assert request_of(state) == request and records(state, DamageDealt) == []
    submit(state, answer(state, AmountsEach((Amounts((3, 0)), Amounts((2, 2))))))
    damage = {e.source: e.to_objects for e in records(state, DamageDealt)}
    assert damage == {giant: ((w1, 3),), regrower: ((w3, 2), (w4, 2))}


def test_903_10a_a_blocked_commander_deals_combat_damage_to_creatures() -> None:
    """903.10a tallies only combat damage a commander deals to a player: P0's commander,
    Grizzly Bears, blocked by Test Wall, deals its 2 to the Wall without the gap; P1's commander
    Savannah Lions blocking Hill Giant deals its 2 to the Giant."""
    scenario = Scenario(2, config=GameConfig.commander_game())
    commander = scenario.commander(P0, "Grizzly Bears", zone=BATTLEFIELD)
    blocker = scenario.commander(P1, "Savannah Lions", zone=BATTLEFIELD)
    (giant,) = scenario.battlefield(P0, ["Hill Giant"])
    (wall,) = scenario.battlefield(P1, ["Test Wall"])
    scenario.at(Step.COMBAT_DAMAGE, begin=True)
    scenario.attacking(P1, commander, giant)
    scenario.blocking(wall, commander)
    scenario.blocking(blocker, giant)
    state = scenario.build()
    damage = {e.source: e.to_objects for e in records(state, DamageDealt)}
    assert damage[commander] == ((wall, 2),) and damage[blocker] == ((giant, 2),)


def test_702_16e_protection_from_the_attackers_damage_is_a_gap_until_m6() -> None:
    """Raging Goblin (red) is blocked by Repentant Blacksmith (protection from red): the
    Goblin's combat damage to it would be prevented (702.16e), which is M6's prevention stage,
    so it is a gap, raised before any damage is dealt."""
    scenario = Scenario(2)
    (goblin,) = scenario.battlefield(P0, ["Raging Goblin"])
    (smith,) = scenario.battlefield(P1, ["Repentant Blacksmith"])
    scenario.at(Step.COMBAT_DAMAGE, begin=True)
    scenario.attacking(P1, goblin)
    scenario.blocking(smith, goblin)
    with pytest.raises(NotImplementedRule) as gap:
        scenario.build()
    assert gap.value.rule == "702.16e"
    assert all(scenario._state.objects[o].damage == 0 for o in (goblin, smith))  # pyright: ignore[reportPrivateUsage]


def test_506_4b_a_tapped_blocker_still_deals_and_is_dealt_damage() -> None:
    """Tapping a blocker doesn't remove it from combat (506.4b): P1's Grizzly Bears, tapped
    after blocking Savannah Lions, still deal their 2 and are dealt 2; both die."""
    scenario = Scenario(2)
    (lions,) = scenario.battlefield(P0, ["Savannah Lions"])
    (bears,) = scenario.battlefield(P1, ["Grizzly Bears"])
    scenario.tap(bears)
    scenario.at(Step.COMBAT_DAMAGE, begin=True)
    scenario.attacking(P1, lions)
    scenario.blocking(bears, lions)
    state = scenario.build()
    damage = {e.source: e.to_objects for e in records(state, DamageDealt)}
    assert damage == {lions: ((bears, 2),), bears: ((lions, 2),)}
    assert lions not in state.battlefield and bears not in state.battlefield


def test_802_5_apnap_order_starts_with_the_active_player() -> None:
    """Four players with P2 active (APNAP order P2, P3, P0, P1, 101.4). P2's Hill Giant is
    blocked by two of P3's creatures, and P3's, P0's and P1's Palace Guards each block two of
    P2's attackers: the assignments are asked in the order P2, P3, P0, P1 (510.1, 802.5)."""
    scenario = Scenario(4)
    giant, *others = scenario.battlefield(P2, ["Hill Giant"] + ["Grizzly Bears"] * 6)
    guards = {p: scenario.battlefield(p, ["Palace Guard"])[0] for p in (P3, P0, P1)}
    walls = scenario.battlefield(P3, ["Test Wall", "Test Wall"])
    scenario.at(Step.COMBAT_DAMAGE, active=P2, begin=True)
    scenario.attacking(P3, giant, others[0], others[1])
    scenario.attacking(P0, others[2], others[3])
    scenario.attacking(P1, others[4], others[5])
    for wall in walls:
        scenario.blocking(wall, giant)
    scenario.blocking(guards[P3], others[0], others[1])
    scenario.blocking(guards[P0], others[2], others[3])
    scenario.blocking(guards[P1], others[4], others[5])
    state = scenario.build()
    order: list[PlayerId] = []
    while request_of(state).kind is DecisionKind.ASSIGN_COMBAT_DAMAGE:
        order.append(request_of(state).player)
        (source,) = damage_sources(state)
        first = damage_recipients(state, source)[0]
        amount = 3 if source == giant else 1
        assign_damage(state, {source: {first: amount}})
    assert order == [P2, P3, P0, P1]
