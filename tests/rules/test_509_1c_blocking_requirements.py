"""509.1b-f: restrictions, requirements and costs on declaring blockers (M3.5).

From the pinned CR:

- 509.1b: restrictions ("can't block", "can't block unless ...") must be obeyed.
- 509.1c: the number of requirements obeyed ("blocks if able", "must block") must be the maximum
  possible without disobeying any restriction; a player isn't required to pay a cost to block,
  even to obey a requirement. Example: a creature that blocks if able and one with no abilities,
  attacked by a creature with menace: the player must block with both.
- 509.1d-f: the total cost to block is determined and locked in, mana abilities may be activated,
  then the costs are paid (no partial payments); 509.1: if a step can't be complied with, the
  declaration is illegal and the game returns to before it (733.1).
- 802.4b: when judging a defending player's blocks, creatures attacking other players and other
  players' blockers are ignored.

Cards (Snapshot 2026-11-02): Prized Unicorn ("All creatures able to block this creature do so."),
Mogg Flunkies ("This creature can't attack or block alone."), Silent Arbiter ("No more than one
creature can block each combat."), Deranged Whelp (menace); fixtures Test Sentry ("This creature
blocks each combat if able.", 509.1c's example), Test Stomper ("can't attack or block unless you
control seven or more lands") and Test Tollkeeper ("Creatures can't block unless their controller
pays {1} for each creature they control that's blocking.").

Prized Unicorn's rulings (2019-07-12): "If a creature the defending player controls can't block
Prized Unicorn for any reason (such as being tapped), then it doesn't block Prized Unicorn. If
there's a cost associated with having a creature block Prized Unicorn, the defending player isn't
forced to pay that cost, so it doesn't have to block." and "If more than one Prized Unicorn is
attacking, creatures that could block must block one Prized Unicorn, but they don't all have to
block the same Prized Unicorn."

**Interpretation (802.4b):** Mogg Flunkies "blocks alone" and Silent Arbiter's "no more than one
creature can block each combat" are judged within one defending player's declaration, ignoring
other players' blockers (802.4b), so in multiplayer each defending player may block with one
creature under Silent Arbiter, and a Flunkies needs a blocker of its own controller.
"""

from __future__ import annotations

from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import ManaActivationOption
from resolve.engine.api import view_for
from resolve.engine.concede import concede
from resolve.errors import InvalidAnswer
from resolve.events.combat import BlockersDeclared
from resolve.events.spells import ActionReversed
from resolve.rules import legality
from resolve.state.combat import CombatState
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.turn import Step
from tests.casting_support import activate, records, reverse
from tests.combat_support import block_space, declare_blockers, may_block
from tests.game_fixtures import request_of
from tests.scenario import Scenario, run_script

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)
Blocks = dict[ObjectId, tuple[ObjectId, ...]]


def combat_of(state: GameState) -> CombatState:
    assert state.turn is not None and state.turn.combat is not None
    return state.turn.combat


def refused(state: GameState, blocks: Blocks) -> bool:
    """Whether the pending declaration refuses ``blocks``, leaving the game unchanged (733.1)."""
    before = request_of(state)
    try:
        declare_blockers(state, blocks)
    except InvalidAnswer:
        assert request_of(state) == before
        return True
    return False


def blocked_by(state: GameState) -> dict[ObjectId, tuple[ObjectId, ...]]:
    return {b: record.blocking for b, record in combat_of(state).blockers.items()}


# --- 509.1c's example: Test Sentry and menace ---------------------------------------------------


def test_509_1c_example_menace_and_a_creature_that_blocks_if_able() -> None:
    """509.1c's example: Test Sentry (blocks if able) and Grizzly Bears, attacked by Deranged
    Whelp (menace). Only both blocking is legal: the Sentry alone breaks menace, the Bears alone
    break menace and the requirement, neither disobeys the requirement."""
    scenario = Scenario(2)
    (whelp,) = scenario.battlefield(P0, ["Deranged Whelp"])
    sentry, bears = scenario.battlefield(P1, ["Test Sentry", "Grizzly Bears"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, whelp)
    state = scenario.build()
    assert refused(state, {sentry: (whelp,)})
    assert refused(state, {bears: (whelp,)})
    assert refused(state, {})
    declare_blockers(state, {sentry: (whelp,), bears: (whelp,)})
    assert blocked_by(state) == {sentry: (whelp,), bears: (whelp,)}


def test_sentry_blocks_any_attacker() -> None:
    """Test Sentry's requirement is obeyed by blocking any attacker: with two attackers it must
    block one of them, either."""
    scenario = Scenario(2)
    bears, lions = scenario.battlefield(P0, ["Grizzly Bears", "Savannah Lions"])
    (sentry,) = scenario.battlefield(P1, ["Test Sentry"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, bears, lions)
    state = scenario.build()
    assert refused(state, {})
    declare_blockers(state, {sentry: (lions,)})
    assert blocked_by(state) == {sentry: (lions,)}


# --- Prized Unicorn ---------------------------------------------------------------------------


def _unicorn_board(
    unicorns: int = 1, *, tollkeeper: bool = False
) -> tuple[GameState, list[ObjectId], dict[str, ObjectId]]:
    scenario = Scenario(2)
    attackers = scenario.battlefield(P0, ["Prized Unicorn"] * unicorns + ["Hill Giant"])
    bears, lions, tapped, stomper = scenario.battlefield(
        P1, ["Grizzly Bears", "Savannah Lions", "Grizzly Bears", "Test Stomper"]
    )
    (forest,) = scenario.battlefield(P1, ["Forest"])
    scenario.tap(tapped)
    if tollkeeper:
        scenario.battlefield(P0, ["Test Tollkeeper"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, *attackers)
    names = {"bears": bears, "lions": lions, "tapped": tapped, "stomper": stomper}
    names["forest"] = forest
    return scenario.build(), attackers, names


def test_prized_unicorn_every_able_creature_blocks_it() -> None:
    """Prized Unicorn and Hill Giant attack P1, who controls Grizzly Bears, Savannah Lions, a
    tapped Grizzly Bears and Test Stomper with one land. Every creature able to block the Unicorn
    must (509.1c): the Bears and Lions. Leaving one out, or blocking the Giant instead, is
    refused."""
    state, (unicorn, giant), c = _unicorn_board()
    assert refused(state, {})
    assert refused(state, {c["bears"]: (unicorn,)})
    assert refused(state, {c["bears"]: (unicorn,), c["lions"]: (giant,)})
    declare_blockers(state, {c["bears"]: (unicorn,), c["lions"]: (unicorn,)})
    assert blocked_by(state) == {c["bears"]: (unicorn,), c["lions"]: (unicorn,)}


def test_prized_unicorn_tapped_and_restricted_creatures_dont_block() -> None:
    """The Unicorn's ruling: a tapped creature can't block it, and Test Stomper's restriction
    (one land, not seven) forbids it to block: neither is offered (509.1a-b), so they aren't
    required to."""
    state, (unicorn, _), c = _unicorn_board()
    assert may_block(state) == (c["bears"], c["lions"])
    verdict = legality.allowed(state, legality.BlockAction(P1, c["stomper"], unicorn))
    assert not verdict.allowed and "509.1b" in verdict.rules


def test_prized_unicorn_a_block_cost_isnt_required() -> None:
    """The Unicorn's ruling: with Test Tollkeeper on the battlefield every block needs {1}, which
    P1 isn't forced to pay (509.1c), so not blocking is legal."""
    state, _, _ = _unicorn_board(tollkeeper=True)
    declare_blockers(state, {})
    assert combat_of(state).blockers == {}


def test_two_prized_unicorns_each_blocker_blocks_one() -> None:
    """The Unicorn's ruling: with two Unicorns attacking, each able creature must block one of
    them, not necessarily the same: both on the first, or one on each, are accepted; one of them
    blocking the Giant is refused."""
    state, (first, second, giant), c = _unicorn_board(unicorns=2)
    assert refused(state, {c["bears"]: (first,), c["lions"]: (giant,)})
    assert refused(state, {c["bears"]: (first,)})
    declare_blockers(state, {c["bears"]: (first,), c["lions"]: (second,)})
    assert blocked_by(state) == {c["bears"]: (first,), c["lions"]: (second,)}
    state, (first, _, _), c = _unicorn_board(unicorns=2)
    declare_blockers(state, {c["bears"]: (first,), c["lions"]: (first,)})


def test_prized_unicorn_with_palace_guard_blocks_it_and_others() -> None:
    """Palace Guard can block any number of creatures: it obeys the Unicorn's requirement by
    blocking it, alone or with the Giant; blocking only the Giant is refused."""
    scenario = Scenario(2)
    unicorn, giant = scenario.battlefield(P0, ["Prized Unicorn", "Hill Giant"])
    (guard,) = scenario.battlefield(P1, ["Palace Guard"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, unicorn, giant)
    state = scenario.build()
    assert refused(state, {guard: (giant,)})
    declare_blockers(state, {guard: (unicorn, giant)})
    assert blocked_by(state) == {guard: (unicorn, giant)}


def test_prized_unicorn_attacking_another_player_puts_no_requirement() -> None:
    """802.4b: the Unicorn attacks P2, so P1's creatures can't block it and have no requirement;
    P1 may leave Grizzly Bears home."""
    scenario = Scenario(3)
    unicorn, giant = scenario.battlefield(P0, ["Prized Unicorn", "Hill Giant"])
    scenario.battlefield(P1, ["Grizzly Bears"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P2, unicorn)
    scenario.attacking(P1, giant)
    state = scenario.build()
    assert block_space(state).requirements == ()
    declare_blockers(state, {})


# --- 509.1b: Test Stomper, Mogg Flunkies, Silent Arbiter ----------------------------------------


def test_topiary_style_restriction_for_blocks() -> None:
    """Test Stomper can't block unless its controller controls seven or more lands: with six
    Forests it may not block; with seven it may."""
    for lands, expected in ((6, False), (7, True)):
        scenario = Scenario(2)
        (bears,) = scenario.battlefield(P0, ["Grizzly Bears"])
        (stomper,) = scenario.battlefield(P1, ["Test Stomper"])
        scenario.battlefield(P1, ["Forest"] * lands)
        scenario.at(Step.DECLARE_BLOCKERS, begin=True)
        scenario.attacking(P1, bears)
        state = scenario.build()
        verdict = legality.allowed(state, legality.BlockAction(P1, stomper, bears))
        assert verdict.allowed is expected


def test_mogg_flunkies_cant_block_alone() -> None:
    """Mogg Flunkies can't block alone: alone is refused; with Grizzly Bears blocking another
    attacker (its ruling: not the same one) accepted."""
    scenario = Scenario(2)
    bears, lions = scenario.battlefield(P0, ["Grizzly Bears", "Savannah Lions"])
    flunkies, own = scenario.battlefield(P1, ["Mogg Flunkies", "Grizzly Bears"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, bears, lions)
    state = scenario.build()
    assert refused(state, {flunkies: (bears,)})
    declare_blockers(state, {flunkies: (bears,), own: (lions,)})
    assert blocked_by(state) == {flunkies: (bears,), own: (lions,)}


def test_802_4b_another_players_blocker_doesnt_keep_flunkies_company() -> None:
    """802.4b: P1 blocks first (APNAP) with Grizzly Bears; P2's Mogg Flunkies alone is still
    refused, since P1's blockers are ignored when judging P2's blocks."""
    scenario = Scenario(3)
    bears, lions = scenario.battlefield(P0, ["Grizzly Bears", "Savannah Lions"])
    (blocker,) = scenario.battlefield(P1, ["Grizzly Bears"])
    (flunkies,) = scenario.battlefield(P2, ["Mogg Flunkies"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, bears)
    scenario.attacking(P2, lions)
    state = scenario.build()
    declare_blockers(state, {blocker: (bears,)})
    assert request_of(state).player == P2
    assert refused(state, {flunkies: (lions,)})
    declare_blockers(state, {})


def test_silent_arbiter_at_most_one_blocker() -> None:
    """Silent Arbiter (controlled by the attacker): no more than one creature can block. Two
    blockers are refused, one is accepted."""
    scenario = Scenario(2)
    bears, _ = scenario.battlefield(P0, ["Grizzly Bears", "Silent Arbiter"])
    first, second = scenario.battlefield(P1, ["Grizzly Bears", "Savannah Lions"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, bears)
    state = scenario.build()
    assert refused(state, {first: (bears,), second: (bears,)})
    declare_blockers(state, {second: (bears,)})


def test_802_4b_silent_arbiter_counts_one_defending_players_blockers() -> None:
    """802.4b (the interpretation in the module docstring): P1 blocks with one creature, then P2
    may still block with one of theirs; two of P2's are refused."""
    scenario = Scenario(3)
    bears, lions, _ = scenario.battlefield(
        P0, ["Grizzly Bears", "Savannah Lions", "Silent Arbiter"]
    )
    (one,) = scenario.battlefield(P1, ["Grizzly Bears"])
    two, three = scenario.battlefield(P2, ["Grizzly Bears", "Hill Giant"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, bears)
    scenario.attacking(P2, lions)
    state = scenario.build()
    declare_blockers(state, {one: (bears,)})
    assert refused(state, {two: (lions,), three: (lions,)})
    declare_blockers(state, {three: (lions,)})
    assert blocked_by(state) == {one: (bears,), three: (lions,)}


# --- 509.1d-f: costs to block (Test Tollkeeper) ---------------------------------------------------


def _toll_board(forests: int) -> tuple[GameState, ObjectId, list[ObjectId], list[ObjectId]]:
    scenario = Scenario(2)
    bears, lions = scenario.battlefield(P0, ["Grizzly Bears", "Savannah Lions"])
    scenario.battlefield(P0, ["Test Tollkeeper"])
    blockers = scenario.battlefield(P1, ["Palace Guard", "Hill Giant"])
    lands = scenario.battlefield(P1, ["Forest"] * forests)
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, bears, lions)
    return scenario.build(), bears, blockers, lands


def test_block_tax_is_paid_once_per_blocking_creature() -> None:
    """Test Tollkeeper: {1} for each blocking creature (509.1d), whatever it blocks: Palace Guard
    blocking both attackers and Hill Giant blocking one cost {2}, paid with two Forests
    (509.1e-f); then the blocks are made (509.1g) and the event records the cost."""
    state, bears, (guard, giant), lands = _toll_board(2)
    declare_blockers(state, {guard: (bears, combat_order(state)[1]), giant: (bears,)})
    request = request_of(state)
    assert request.kind is DecisionKind.ACTIVATE_MANA_ABILITIES and request.player == P1
    (payment,) = view_for(state, P1).payments
    assert payment.cost.text == "{2}"
    assert combat_of(state).blockers == {}
    run_script(state, *(activate(land) for land in lands))  # then nothing is left to ask
    assert set(combat_of(state).blockers) == {guard, giant}
    declared = [r for r in records(state, BlockersDeclared) if r.blocks]
    assert declared[0].cost is not None and declared[0].cost.text == "{2}"


def combat_order(state: GameState) -> list[ObjectId]:
    return list(combat_of(state).attackers)


def test_an_unpaid_block_cost_reverses_the_declaration() -> None:
    """One Forest for a {2} total: the cost can't be paid, so the declaration is reversed
    (509.1, 733.1): P1 reverses the Forest, nothing blocks, and P1 declares again."""
    state, bears, (guard, giant), (forest,) = _toll_board(1)
    declare_blockers(state, {guard: (bears,), giant: (bears,)})
    run_script(state, activate(forest), reverse(ManaActivationOption(0, forest, 0)))
    assert request_of(state).kind is DecisionKind.DECLARE_BLOCKERS
    assert request_of(state).player == P1
    assert combat_of(state).blockers == {}
    assert not state.objects[forest].tapped
    (reversed_,) = records(state, ActionReversed)
    assert reversed_.player == P1 and reversed_.declaration
    declare_blockers(state, {guard: (bears,)})
    assert request_of(state).kind is DecisionKind.ACTIVATE_MANA_ABILITIES
    run_script(state, activate(forest))
    assert blocked_by(state) == {guard: (bears,)}


def test_a_defending_player_conceding_while_paying_for_blocks() -> None:
    """Three players, Test Tollkeeper (P0's): P1 declares a block and, while paying its {1},
    concedes (104.3a). Their declaration leaves with them (800.4a): no blocker is made, and P2
    declares next."""
    scenario = Scenario(3)
    bears, lions, _ = scenario.battlefield(
        P0, ["Grizzly Bears", "Savannah Lions", "Test Tollkeeper"]
    )
    (one,) = scenario.battlefield(P1, ["Grizzly Bears"])
    scenario.battlefield(P1, ["Forest"])
    scenario.battlefield(P2, ["Hill Giant"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, bears)
    scenario.attacking(P2, lions)
    state = scenario.build()
    declare_blockers(state, {one: (bears,)})
    assert request_of(state).kind is DecisionKind.ACTIVATE_MANA_ABILITIES
    concede(state, P1)
    request = request_of(state)
    assert request.kind is DecisionKind.DECLARE_BLOCKERS and request.player == P2
    assert combat_of(state).blockers == {}
    assert [r for r in records(state, BlockersDeclared) if r.blocks] == []
