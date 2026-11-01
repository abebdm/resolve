"""509.1b: restrictions on blocking (M3.4).

From the pinned CR:

- 509.1b: the defending player checks each creature they control for restrictions ("can't
  block", "can't block unless ..."); if any is disobeyed, the declaration is illegal. Evasion
  abilities are restrictions; "if an attacking creature gains or loses an evasion ability after a
  legal block has been declared, it doesn't affect that block. Different evasion abilities are
  cumulative." (Example: flying and shadow can't be blocked by a creature with flying but
  without shadow.)
- 733.1: an illegal declaration is refused, and nothing changes.

Cards: Phantom Warrior ("This creature can't be blocked."); Test Lambholt Warden, a 3/3 with
Champion of Lambholt's first ability alone ("Creatures with power less than this creature's power
can't block creatures you control."); Test Flying Brute (flying and menace).

Champion of Lambholt's rulings (2020-08-07): "The comparison of power is done only when blockers
are declared. Decreasing the power of a blocking creature (or increasing the power of Champion of
Lambholt) after this point won't cause any creature to stop blocking or become unblocked." and
"Champion of Lambholt's first ability applies even if it isn't attacking."
"""

from __future__ import annotations

import pytest

from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import Assignment, NoneOrAtLeast, ObjectOption
from resolve.engine.api import submit
from resolve.errors import InvalidAnswer
from resolve.events.combat import BlockersDeclared
from resolve.events.damage import DamageDealt
from resolve.rules import legality
from resolve.state.combat import CombatState
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.turn import Phase, Step
from tests.casting_support import records
from tests.combat_support import (
    block_answer,
    block_space,
    blockable,
    declare_blockers,
    may_block,
    pass_to,
)
from tests.game_fixtures import answer, request_of
from tests.scenario import Scenario

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)


def combat_of(state: GameState) -> CombatState:
    assert state.turn is not None and state.turn.combat is not None
    return state.turn.combat


def verdict(
    state: GameState, blocker: ObjectId, attacker: ObjectId, player: PlayerId = P1
) -> legality.Verdict:
    return legality.allowed(state, legality.BlockAction(player, blocker, attacker))


# --- "This creature can't be blocked." -----------------------------------------------------------


def test_phantom_warrior_cant_be_blocked() -> None:
    """Phantom Warrior attacks P1, who controls Grizzly Bears, Wind Drake (flying) and Palace
    Guard: none may block it (509.1b, cited), so P1 isn't asked and it is unblocked."""
    scenario = Scenario(2)
    (warrior,) = scenario.battlefield(P0, ["Phantom Warrior"])
    blockers = scenario.battlefield(P1, ["Grizzly Bears", "Wind Drake", "Palace Guard"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, warrior)
    state = scenario.build()
    for blocker in blockers:
        refused = verdict(state, blocker, warrior)
        assert not refused.allowed and "509.1b" in refused.rules
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION
    assert combat_of(state).attackers[warrior].blocked is False


def test_phantom_warrior_blocks_as_usual() -> None:
    """The restriction is on blocking Phantom Warrior, not on Phantom Warrior blocking: it may
    block an attacking Grizzly Bears, and another attacker beside it may be blocked."""
    scenario = Scenario(2)
    warrior_attacking, bears = scenario.battlefield(P0, ["Phantom Warrior", "Grizzly Bears"])
    (warrior,) = scenario.battlefield(P1, ["Phantom Warrior"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, warrior_attacking, bears)
    state = scenario.build()
    assert blockable(state, warrior) == (bears,)


# --- Champion of Lambholt's restriction -------------------------------------------------------


def _warden_board(
    blockers: list[str], *, warden_attacks: bool
) -> tuple[GameState, ObjectId, ObjectId, list[ObjectId]]:
    """P0 controls Test Lambholt Warden (3/3) and Grizzly Bears; the Bears attack P1 (and the
    Warden too, if ``warden_attacks``); P1 controls ``blockers``."""
    scenario = Scenario(2)
    warden, bears = scenario.battlefield(P0, ["Test Lambholt Warden", "Grizzly Bears"])
    ids = scenario.battlefield(P1, blockers)
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, *((warden, bears) if warden_attacks else (bears,)))
    return scenario.build(), warden, bears, ids


def test_champions_restriction_smaller_blockers_are_refused() -> None:
    """The Warden's power is 3: Grizzly Bears and Savannah Lions (power 2 and 1) can't block the
    Warden or the attacking Bears (509.1b, cited); Wall of Stone's 0 power can't either."""
    state, warden, bears, blockers = _warden_board(
        ["Grizzly Bears", "Savannah Lions", "Wall of Stone"], warden_attacks=True
    )
    for blocker in blockers:
        for attacker in (warden, bears):
            refused = verdict(state, blocker, attacker)
            assert not refused.allowed and "509.1b" in refused.rules
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION


def test_champions_restriction_equal_power_is_allowed() -> None:
    """ "Less than": Hill Giant's power equals the Warden's 3, so it may block either attacker;
    Test Regrower (power 4) too."""
    state, warden, bears, (giant, regrower) = _warden_board(
        ["Hill Giant", "Test Regrower"], warden_attacks=True
    )
    assert blockable(state, giant) == (warden, bears)
    assert blockable(state, regrower) == (warden, bears)


def test_champions_restriction_protects_any_creature_of_its_controller() -> None:
    """The Warden doesn't attack (its ruling: the ability applies even if it isn't attacking):
    the attacking Grizzly Bears still can't be blocked by P1's Savannah Lions (power 1), but can by
    P1's Hill Giant (power 3)."""
    state, _warden, bears, (lions, giant) = _warden_board(
        ["Savannah Lions", "Hill Giant"], warden_attacks=False
    )
    assert may_block(state) == (giant,)
    assert blockable(state, giant) == (bears,)
    assert not verdict(state, lions, bears).allowed


def test_champions_restriction_doesnt_protect_other_players_creatures() -> None:
    """A Warden controlled by the defending player restricts blocks of creatures *they*
    control: P0's attacking Grizzly Bears may be blocked by P1's Savannah Lions (power 1) though
    P1 controls a Warden; three players, P2's Warden doesn't affect P1's blocks either."""
    scenario = Scenario(3)
    (bears,) = scenario.battlefield(P0, ["Grizzly Bears"])
    _warden, lions = scenario.battlefield(P1, ["Test Lambholt Warden", "Savannah Lions"])
    scenario.battlefield(P2, ["Test Lambholt Warden"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, bears)
    state = scenario.build()
    assert blockable(state, lions) == (bears,)


def test_champions_restriction_is_checked_only_as_blocks_are_declared() -> None:
    """Its ruling: the comparison is made only as blockers are declared. P1's Grizzly Bears
    (power 2) were declared blocking P0's Hill Giant before P0's Test Lambholt Warden (power 3)
    was on the battlefield (the scenario puts it there after the declaration, as if it had entered
    since): the block stands through combat damage, the Bears and the Giant dealing damage to
    each other (510.1c-d)."""
    scenario = Scenario(2)
    giant, _warden = scenario.battlefield(P0, ["Hill Giant", "Test Lambholt Warden"])
    (bears,) = scenario.battlefield(P1, ["Grizzly Bears"])
    scenario.at(Step.DECLARE_BLOCKERS)
    scenario.attacking(P1, giant)
    scenario.blocking(bears, giant)
    state = scenario.build()
    assert not verdict(state, bears, giant).allowed  # it couldn't be declared now
    pass_to(state, Phase.POSTCOMBAT_MAIN)
    damage = {event.source: event for event in records(state, DamageDealt)}
    assert damage[giant].to_objects == ((bears, 3),)
    assert damage[bears].to_objects == ((giant, 2),)


# --- Cumulative evasion; illegal declarations -------------------------------------------------


def test_509_1b_evasion_is_cumulative() -> None:
    """Test Flying Brute has flying and menace: it can be blocked only by two or more creatures
    each with flying or reach. P1 controls Wind Drake, Giant Spider and Grizzly Bears: the Bears
    can't block it (flying), the Drake alone is refused (menace), the Drake and the Spider
    together are accepted."""
    scenario = Scenario(2)
    (brute,) = scenario.battlefield(P0, ["Test Flying Brute"])
    drake, spider, bears = scenario.battlefield(P1, ["Wind Drake", "Giant Spider", "Grizzly Bears"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, brute)
    state = scenario.build()
    assert may_block(state) == (drake, spider)
    assert not verdict(state, bears, brute).allowed
    assert block_space(state).constraints == (NoneOrAtLeast(ObjectOption(brute), 2),)
    with pytest.raises(InvalidAnswer):
        submit(state, answer(state, block_answer(state, {drake: (brute,)})))
    declare_blockers(state, {drake: (brute,), spider: (brute,)})
    assert combat_of(state).blockers_of(brute) == (drake, spider)


def test_509_1b_flying_and_menace_with_one_able_blocker_isnt_blockable() -> None:
    """Cumulative: P1's Wind Drake and Grizzly Bears are two creatures, but only the Drake may
    block the Brute (flying), and it can't alone (menace): P1 isn't asked."""
    scenario = Scenario(2)
    (brute,) = scenario.battlefield(P0, ["Test Flying Brute"])
    scenario.battlefield(P1, ["Wind Drake", "Grizzly Bears"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, brute)
    state = scenario.build()
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION
    assert combat_of(state).attackers[brute].blocked is False


def test_509_1b_an_illegal_block_is_rejected_and_nothing_changes() -> None:
    """Hill Giant and Wind Drake attack P1, who controls Grizzly Bears: the Bears may block only
    the Giant, so the space offers it one choice, and an answer picking a second (the Drake's
    place, index 1) is refused. The pending request, the combat state and the log are unchanged
    (733.1), and a legal declaration is then accepted."""
    scenario = Scenario(2)
    giant, drake = scenario.battlefield(P0, ["Hill Giant", "Wind Drake"])
    (bears,) = scenario.battlefield(P1, ["Grizzly Bears"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, giant, drake)
    state = scenario.build()
    assert blockable(state, bears) == (giant,)
    request = request_of(state)
    with pytest.raises(InvalidAnswer):
        submit(state, answer(state, Assignment(((1,),))))
    assert request_of(state) == request
    assert combat_of(state).blockers == {}
    assert records(state, BlockersDeclared) == []
    declare_blockers(state, {bears: (giant,)})
    combat = combat_of(state)
    assert combat.attackers[giant].blocked is True
    assert combat.attackers[drake].blocked is False
