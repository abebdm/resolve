"""The combat events (``resolve.events.combat``) and ``remove_from_combat`` (506.4), applied
directly to scenario states.

- ``CombatBegan`` (506.2): only in a combat phase, once per combat phase.
- ``AttackersDeclared`` (508.1k): attackers in order, not yet blocked or unblocked; 508.8's
  ``attacks_happened``.
- ``BlockersDeclared`` (509.1g-h): blockers block their attackers in order; named attackers
  become blocked, every other undecided attacker unblocked, and decided ones stay as they are.
- ``CombatEnded`` (511.3): the combat state is gone.
- 506.4: an attacker leaving combat stops being blocked by its blockers; a blocker leaving
  leaves its attackers blocked (509.1h); nothing happens outside a combat.
"""

from __future__ import annotations

import pytest

from resolve.errors import EngineError
from resolve.events.combat import AttackersDeclared, BlockersDeclared, CombatBegan, CombatEnded
from resolve.state.combat import (
    AttackPlayer,
    AttackRecord,
    BlockRecord,
    CombatState,
    remove_from_combat,
)
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.turn import Phase, Step
from tests.scenario import Scenario

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)


def combat_of(state: GameState) -> CombatState:
    assert state.turn is not None and state.turn.combat is not None
    return state.turn.combat


def declare_step(players: int = 2) -> tuple[GameState, list[ObjectId], list[ObjectId]]:
    scenario = Scenario(players)
    attackers = scenario.battlefield(P0, ["Grizzly Bears", "Hill Giant", "Savannah Lions"])
    blockers = scenario.battlefield(P1, ["Test Wall", "Darksteel Myr"])
    scenario.at(Step.DECLARE_ATTACKERS)
    return scenario.build(), attackers, blockers


def test_506_2_combat_began_creates_the_combat_state_once_in_a_combat_phase() -> None:
    scenario = Scenario(3)
    scenario.at(Step.BEGINNING_OF_COMBAT, begin=True)
    state = scenario.build()
    assert combat_of(state).defending_players == (P1, P2)
    with pytest.raises(EngineError, match="already"):
        CombatBegan(defending_players=(P1,), rules=("506.2",)).apply(state)

    scenario = Scenario(2)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    with pytest.raises(EngineError, match="combat phase"):
        CombatBegan(defending_players=(P1,), rules=("506.2",)).apply(state)


def test_508_1k_attackers_declared_in_order_and_undecided() -> None:
    state, (bears, giant, _), _ = declare_step()
    AttackersDeclared(
        attacks=((giant, AttackPlayer(P1)), (bears, AttackPlayer(P1))), rules=("508.1k",)
    ).apply(state)
    combat = combat_of(state)
    assert list(combat.attackers) == [giant, bears]
    assert combat.attackers[giant] == AttackRecord(giant, AttackPlayer(P1), True, None)
    assert combat.attacks_happened
    with pytest.raises(EngineError, match="already attacking"):
        AttackersDeclared(attacks=((bears, AttackPlayer(P1)),), rules=("508.1k",)).apply(state)
    with pytest.raises(EngineError, match="empty"):
        AttackersDeclared(attacks=(), rules=("508.1k",)).apply(state)


def test_509_1h_blockers_declared_fixes_blocked_status() -> None:
    """The Wall blocks the Giant: the Giant is blocked, the Bears unblocked. An attacker whose
    status is already decided keeps it (509.1h)."""
    state, (bears, giant, lions), (wall, _) = declare_step()
    combat = combat_of(state)
    AttackersDeclared(
        attacks=((bears, AttackPlayer(P1)), (giant, AttackPlayer(P1))), rules=("508.1k",)
    ).apply(state)
    combat.attackers[lions] = AttackRecord(lions, AttackPlayer(P1), False, True)
    BlockersDeclared(blocks=((wall, (giant,)),), rules=("509.1g",)).apply(state)
    assert combat.blockers == {wall: BlockRecord(wall, (giant,))}
    assert [combat.attackers[a].blocked for a in (bears, giant, lions)] == [False, True, True]


def test_509_1g_blockers_declared_refuses_impossible_blocks() -> None:
    state, (bears, giant, _), (wall, _) = declare_step()
    AttackersDeclared(attacks=((bears, AttackPlayer(P1)),), rules=("508.1k",)).apply(state)
    with pytest.raises(EngineError, match="isn't attacking"):
        BlockersDeclared(blocks=((wall, (giant,)),), rules=("509.1g",)).apply(state)
    BlockersDeclared(blocks=((wall, (bears,)),), rules=("509.1g",)).apply(state)
    with pytest.raises(EngineError, match="already blocking"):
        BlockersDeclared(blocks=((wall, (bears,)),), rules=("509.1g",)).apply(state)


def test_511_3_combat_ended_removes_the_combat_state() -> None:
    state, (bears, _, _), _ = declare_step()
    AttackersDeclared(attacks=((bears, AttackPlayer(P1)),), rules=("508.1k",)).apply(state)
    CombatEnded(rules=("511.3",)).apply(state)
    assert state.turn is not None and state.turn.combat is None
    with pytest.raises(EngineError, match="no combat"):
        CombatEnded(rules=("511.3",)).apply(state)


def test_506_4_removing_an_attacker_and_a_blocker() -> None:
    """The Wall blocks the Bears and the Giant (as if it could block two), the Myr the Giant.
    Removing the Giant leaves the Wall blocking the Bears and the Myr blocking nothing; removing
    the Wall leaves the Bears blocked (509.1h); 508.8's record stays."""
    state, (bears, giant, _), (wall, myr) = declare_step()
    combat = combat_of(state)
    AttackersDeclared(
        attacks=((bears, AttackPlayer(P1)), (giant, AttackPlayer(P1))), rules=("508.1k",)
    ).apply(state)
    BlockersDeclared(blocks=((wall, (bears, giant)), (myr, (giant,))), rules=("509.1g",)).apply(
        state
    )
    remove_from_combat(state, giant)
    assert list(combat.attackers) == [bears]
    assert combat.blockers == {wall: BlockRecord(wall, (bears,)), myr: BlockRecord(myr, ())}
    remove_from_combat(state, wall)
    assert list(combat.blockers) == [myr]
    assert combat.attackers[bears].blocked is True
    remove_from_combat(state, bears)
    assert combat.attackers == {} and combat.attacks_happened
    remove_from_combat(state, bears)  # not in combat: nothing happens


def test_506_4_outside_combat_nothing_happens() -> None:
    scenario = Scenario(2)
    (bears,) = scenario.battlefield(P0, ["Grizzly Bears"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    remove_from_combat(state, bears)
    assert state.turn is not None and state.turn.combat is None
