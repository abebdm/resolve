"""The torture test "Lure + a creature that attacks each combat if able + Ghostly Prison"
(docs/torture-tests.md; the M3 plan's section 4.2, question Q4).

Lure is an Aura (enchant, M4; a granted ability, M5), so M3 uses Prized Unicorn, which has Lure's
ability itself ("All creatures able to block this creature do so."), with Test Warmonger
("Creatures you control attack each combat if able.") for the attack requirement.

The rules (pinned CR):

- 508.1d: attack requirements are obeyed as far as possible without disobeying restrictions,
  but a cost to attack (Ghostly Prison) is never required: the Unicorn needn't attack.
- 508.1g-j: if P0 attacks anyway, the {2} is locked in and paid.
- 509.1c: then every creature able to block the Unicorn must, unless a restriction stops it
  (509.1b; the plan names "a flyer-only restriction": no card of M3 has one, so Test Stomper's
  "can't block unless you control seven or more lands" stands in for it) or blocking it needs a
  cost, which the defending player isn't required to pay (Test Tollkeeper; Prized Unicorn's
  ruling).
"""

from __future__ import annotations

from resolve.decisions.kinds import DecisionKind
from resolve.errors import InvalidAnswer
from resolve.state.combat import CombatState
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.turn import Phase, Step
from tests.casting_support import activate, pay
from tests.combat_support import declare_attackers, declare_blockers, may_attack, pass_to
from tests.game_fixtures import request_of
from tests.scenario import Scenario, run_script

P0, P1 = PlayerId(0), PlayerId(1)


def combat_of(state: GameState) -> CombatState:
    assert state.turn is not None and state.turn.combat is not None
    return state.turn.combat


def board(*, tollkeeper: bool = False) -> tuple[GameState, dict[str, ObjectId]]:
    """P0: Prized Unicorn, Test Warmonger (summoning sick, so it can't attack), two Plains. P1:
    Ghostly Prison, Grizzly Bears, Hill Giant, Test Stomper (one land: it can't block), a
    tapped Savannah Lions, a Forest (and Test Tollkeeper with ``tollkeeper``)."""
    scenario = Scenario(2)
    (unicorn,) = scenario.battlefield(P0, ["Prized Unicorn"])
    scenario.battlefield(P0, ["Test Warmonger"], entered_turn=2)
    plains = scenario.battlefield(P0, ["Plains", "Plains"])
    scenario.battlefield(P1, ["Ghostly Prison"])
    bears, giant, stomper, lions, forest = scenario.battlefield(
        P1, ["Grizzly Bears", "Hill Giant", "Test Stomper", "Savannah Lions", "Forest"]
    )
    scenario.tap(lions)
    if tollkeeper:
        scenario.battlefield(P1, ["Test Tollkeeper"])
    scenario.at(Step.DECLARE_ATTACKERS, begin=True, number=2)
    names = {"unicorn": unicorn, "bears": bears, "giant": giant, "stomper": stomper}
    names |= {"lions": lions, "forest": forest, "plains0": plains[0], "plains1": plains[1]}
    return scenario.build(), names


def attack_paying(state: GameState, c: dict[str, ObjectId]) -> None:
    declare_attackers(state, {c["unicorn"]: P1})
    run_script(state, activate(c["plains0"]), activate(c["plains1"]), pay())
    pass_to(state, Phase.COMBAT, Step.DECLARE_BLOCKERS)
    assert request_of(state).kind is DecisionKind.DECLARE_BLOCKERS


def test_attacking_isnt_required_when_it_costs() -> None:
    """The Unicorn must attack each combat if able (Test Warmonger), but attacking P1 costs {2}
    (Ghostly Prison), which P0 isn't required to pay (508.1d): declaring no attacker is legal."""
    state, c = board()
    assert may_attack(state) == (c["unicorn"],)
    declare_attackers(state, {})
    assert combat_of(state).attackers == {}


def test_paid_every_creature_able_to_block_it_must() -> None:
    """P0 pays the {2} and the Unicorn attacks. P1's Grizzly Bears and Hill Giant must both block
    it (509.1c); Test Stomper (a restriction, 509.1b) and the tapped Savannah Lions can't, so they
    don't. Fewer blockers are refused."""
    state, c = board()
    attack_paying(state, c)
    assert c["unicorn"] in combat_of(state).attackers
    for partial in ({}, {c["bears"]: (c["unicorn"],)}, {c["giant"]: (c["unicorn"],)}):
        try:
            declare_blockers(state, partial)
        except InvalidAnswer:
            continue
        raise AssertionError(f"{partial} was accepted")
    declare_blockers(state, {c["bears"]: (c["unicorn"],), c["giant"]: (c["unicorn"],)})
    assert set(combat_of(state).blockers) == {c["bears"], c["giant"]}


def test_paid_an_unpaid_block_cost_isnt_required() -> None:
    """With Test Tollkeeper too, blocking the Unicorn costs {1} per blocker, which P1 isn't
    required to pay (509.1c, Prized Unicorn's ruling): no block is legal; and P1 may still block,
    paying."""
    state, c = board(tollkeeper=True)
    attack_paying(state, c)
    declare_blockers(state, {})
    assert combat_of(state).blockers == {}
    state, c = board(tollkeeper=True)
    attack_paying(state, c)
    declare_blockers(state, {c["bears"]: (c["unicorn"],)})
    run_script(state, activate(c["forest"]), pay())
    assert set(combat_of(state).blockers) == {c["bears"]}
