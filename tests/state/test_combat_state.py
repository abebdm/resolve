"""The combat state (506-511; design.md §17.18): its invariants, purity and view.

From the pinned CR:

- 506.1, 511.3: combat exists during the combat phase only (as it ends, every creature and
  planeswalker is removed from combat).
- 506.2, 802.2: the active player is the attacking player; in a multiplayer game every one of
  their opponents is a defending player. Only creatures the attacking player controls attack
  (508.1a); only creatures a defending player controls block (509.1a), and each blocks a creature
  attacking that player (509.1a, 802.4a).
- 506.3: only a creature can attack or block; a player can be attacked.
- 508.8: whether attackers were declared is what skips the later steps.
- 509.1h: an attacking creature with blockers declared for it is blocked.
"""

from __future__ import annotations

import copy
import pickle
from collections.abc import Callable
from dataclasses import replace

import pytest

from resolve.engine.concede import concede
from resolve.engine.view import CombatView, view_for
from resolve.rules.combat import defending_players
from resolve.state.combat import AttackPlayer, AttackRecord, BlockRecord, CombatState
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.invariants import check_pure_data, invariant_violations
from resolve.state.turn import Phase, Step
from tests.scenario import Scenario

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)


def combat_board() -> tuple[GameState, dict[str, ObjectId]]:
    """Three players, P0's turn 3, the declare blockers step (blockers declared): Grizzly Bears
    attacks P1 and is blocked by P1's Test Wall; Hill Giant attacks P2, unblocked. P0 also has an
    untapped Forest and Llanowar Elves (not attacking); P2 has Savannah Lions (not blocking)."""
    scenario = Scenario(3)
    bears, giant, forest, elves = scenario.battlefield(
        P0, ["Grizzly Bears", "Hill Giant", "Forest", "Llanowar Elves"]
    )
    (wall,) = scenario.battlefield(P1, ["Test Wall"])
    (lions,) = scenario.battlefield(P2, ["Savannah Lions"])
    scenario.at(Step.DECLARE_BLOCKERS, number=3)
    scenario.attacking(P1, bears)
    scenario.attacking(P2, giant)
    scenario.blocking(wall, bears)
    ids = {"bears": bears, "giant": giant, "forest": forest, "elves": elves}
    ids |= {"wall": wall, "lions": lions}
    return scenario.build(), ids


def test_506_2_802_2_every_opponent_still_in_the_game_defends() -> None:
    """Two players: the nonactive one (506.2). Four players, P2's turn: the other three, in
    APNAP order (802.2, 101.4); one who has left the game isn't an opponent in it (800.4a)."""
    two = Scenario(2)
    two.at(Step.BEGINNING_OF_COMBAT, active=P1, number=2)
    assert defending_players(two.build()) == (P0,)
    four = Scenario(4)
    four.at(Step.BEGINNING_OF_COMBAT, active=P2, number=3)
    state = four.build()
    assert defending_players(state) == (PlayerId(3), P0, P1)
    concede(state, P0)
    assert defending_players(state) == (PlayerId(3), P1)


def combat_of(state: GameState) -> CombatState:
    assert state.turn is not None and state.turn.combat is not None
    return state.turn.combat


def test_the_scenario_builds_the_combat_state() -> None:
    state, ids = combat_board()
    bears, giant, wall = ids["bears"], ids["giant"], ids["wall"]
    assert combat_of(state) == CombatState(
        defending_players=(P1, P2),
        attackers={
            bears: AttackRecord(bears, AttackPlayer(P1), declared=True, blocked=True),
            giant: AttackRecord(giant, AttackPlayer(P2), declared=True, blocked=False),
        },
        blockers={wall: BlockRecord(wall, (bears,), declared=True)},
        attacks_happened=True,
    )
    assert combat_of(state).blockers_of(bears) == (wall,)
    assert combat_of(state).blockers_of(giant) == ()
    assert invariant_violations(state) == []


def test_no_combat_state_outside_combat() -> None:
    scenario = Scenario(2)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    assert state.turn is not None and state.turn.combat is None


def _attack(record: AttackRecord) -> Callable[[GameState, dict[str, ObjectId]], None]:
    def change(state: GameState, ids: dict[str, ObjectId]) -> None:
        combat_of(state).attackers[record.attacker] = record

    return change


def _forest_attacks(state: GameState, ids: dict[str, ObjectId]) -> None:
    _attack(AttackRecord(ids["forest"], AttackPlayer(P1)))(state, ids)


def _missing_object_attacks(state: GameState, ids: dict[str, ObjectId]) -> None:
    _attack(AttackRecord(ObjectId(999), AttackPlayer(P1)))(state, ids)


def _attacks_the_active_player(state: GameState, ids: dict[str, ObjectId]) -> None:
    _attack(AttackRecord(ids["giant"], AttackPlayer(P0)))(state, ids)


def _outside_combat(state: GameState, ids: dict[str, ObjectId]) -> None:
    assert state.turn is not None
    state.turn.phase, state.turn.step = Phase.POSTCOMBAT_MAIN, None
    state.turn.segments = state.turn.segments[3:]


def _opponent_attacks(state: GameState, ids: dict[str, ObjectId]) -> None:
    wall = ids["wall"]
    combat = combat_of(state)
    combat.attackers[wall] = AttackRecord(wall, AttackPlayer(P2), blocked=False)


def _attacker_blocks(state: GameState, ids: dict[str, ObjectId]) -> None:
    combat_of(state).blockers[ids["elves"]] = BlockRecord(ids["elves"], (ids["giant"],))


def _blocks_a_non_attacker(state: GameState, ids: dict[str, ObjectId]) -> None:
    combat_of(state).blockers[ids["lions"]] = BlockRecord(ids["lions"], (ids["elves"],))


def _blocks_another_players_attacker(state: GameState, ids: dict[str, ObjectId]) -> None:
    combat = combat_of(state)
    combat.blockers[ids["lions"]] = BlockRecord(ids["lions"], (ids["bears"],))


def _blocked_says_unblocked(state: GameState, ids: dict[str, ObjectId]) -> None:
    combat = combat_of(state)
    combat.attackers[ids["bears"]] = replace(combat.attackers[ids["bears"]], blocked=False)


def _wrong_key(state: GameState, ids: dict[str, ObjectId]) -> None:
    combat = combat_of(state)
    combat.attackers[ids["elves"]] = combat.attackers.pop(ids["giant"])


def _no_attacks_happened(state: GameState, ids: dict[str, ObjectId]) -> None:
    combat_of(state).attacks_happened = False


def _active_player_defends(state: GameState, ids: dict[str, ObjectId]) -> None:
    combat_of(state).defending_players = (P0, P1, P2)


def _unknown_defender(state: GameState, ids: dict[str, ObjectId]) -> None:
    combat_of(state).defending_players = (P1, P2, PlayerId(7))


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        (_outside_combat, "a combat state outside the combat phase (506.1, 511.3)"),
        (_opponent_attacks, "isn't controlled by the active player (506.2, 508.1a)"),
        (_attacker_blocks, "isn't controlled by a defending player (509.1a)"),
        (_forest_attacks, "isn't a creature on the battlefield (506.3)"),
        (_missing_object_attacks, "isn't a creature on the battlefield (506.3)"),
        (_attacks_the_active_player, "attacks player 0, who isn't a defending player (506.2)"),
        (_blocks_a_non_attacker, "which isn't attacking (509.1a)"),
        (_blocks_another_players_attacker, "attacking another player (509.1a, 802.4a)"),
        (_blocked_says_unblocked, "has blockers but isn't recorded as blocked (509.1h)"),
        (_wrong_key, "is stored under the wrong key"),
        (_no_attacks_happened, "attacks_happened is False (508.8)"),
        (_active_player_defends, "the active player can't be a defending player (506.2)"),
        (_unknown_defender, "defending player 7 isn't a player"),
    ],
)
def test_combat_state_invariants(
    change: Callable[[GameState, dict[str, ObjectId]], None], problem: str
) -> None:
    state, ids = combat_board()
    change(state, ids)
    assert any(problem in found for found in invariant_violations(state)), invariant_violations(
        state
    )


def test_a_creature_put_onto_the_battlefield_attacking_didnt_make_attacks_happen() -> None:
    """508.8 counts creatures declared as attackers and creatures put onto the battlefield
    attacking (508.4), so an attacker of either kind requires ``attacks_happened``. With no
    attackers left it may be either: attackers removed from combat after attacking keep it
    True (508.8 asks whether any were declared, not whether any remain)."""
    state, ids = combat_board()
    combat = combat_of(state)
    combat.attackers.clear()
    combat.blockers.clear()
    assert invariant_violations(state) == []  # attackers removed after attacking (508.8)
    combat.attacks_happened = False
    assert invariant_violations(state) == []
    combat.attackers[ids["giant"]] = AttackRecord(ids["giant"], AttackPlayer(P2), declared=False)
    assert any("attacks_happened is False" in p for p in invariant_violations(state))


def test_combat_state_survives_deepcopy_and_pickle() -> None:
    """Pure data (CLAUDE.md rule 5): the whole state, combat included, round-trips."""
    state, _ = combat_board()
    check_pure_data(state)
    for copied in (copy.deepcopy(state), pickle.loads(pickle.dumps(state))):
        assert copied.turn is not None
        assert copied.turn.combat == combat_of(state)
        assert copied.turn.combat is not combat_of(state)


def test_view_shows_combat_to_every_player() -> None:
    """Combat is public (400.2, 506): every player, attacked or not, sees the same attackers,
    targets, blockers and blocked status."""
    state, ids = combat_board()
    bears, giant, wall = ids["bears"], ids["giant"], ids["wall"]
    expected = CombatView(
        defending_players=(P1, P2),
        attackers=(
            AttackRecord(bears, AttackPlayer(P1), declared=True, blocked=True),
            AttackRecord(giant, AttackPlayer(P2), declared=True, blocked=False),
        ),
        blockers=(BlockRecord(wall, (bears,), declared=True),),
        attacks_happened=True,
    )
    assert [view_for(state, p).combat for p in (P0, P1, P2)] == [expected] * 3


def test_view_has_no_combat_outside_combat() -> None:
    scenario = Scenario(2)
    scenario.at(Phase.PRECOMBAT_MAIN)
    assert view_for(scenario.build(), P1).combat is None
