"""508.1c-d, 508.1f-k: restrictions, requirements and costs on declaring attackers (M3.5).

From the pinned CR:

- 508.1c: restrictions ("can't attack", "can't attack unless ...") are checked; a declaration
  disobeying one is illegal. Example: two creatures that "can't attack alone" may attack
  together.
- 508.1d: the number of requirements obeyed ("attacks if able") must be the maximum possible
  without disobeying any restriction; a player isn't required to pay a cost to attack, even to
  obey a requirement. Example: a creature that attacks if able, one with no abilities, and "No
  more than one creature can attack each turn": the only legal attack is the first creature
  alone.
- 508.1f: the chosen creatures tap; then 508.1g-h: the total cost to attack is determined and
  locked in; 508.1i: mana abilities may be activated; 508.1j: the costs are paid, no partial
  payments. 508.1: a step that can't be complied with makes the declaration illegal, and the
  game returns to before it (733.1: payments canceled; the player may reverse the mana abilities
  activated meanwhile). 508.1k: the creatures then become attacking creatures.

Cards (Oracle text, Snapshot 2026-11-02): Juggernaut ("This creature attacks each combat if able.
This creature can't be blocked by Walls."), Ghostly Prison ("Creatures can't attack you unless
their controller pays {2} for each creature they control that's attacking you."), Mogg Flunkies
("This creature can't attack or block alone."), Silent Arbiter ("No more than one creature can
attack each combat. No more than one creature can block each combat."); fixtures Test Warmonger
("Creatures you control attack each combat if able.") and Test Stomper ("This creature can't
attack or block unless you control seven or more lands.", Topiary Stomper's restriction).

Rulings: Juggernaut (2022-12-08): "If Juggernaut can't attack for any reason (such as being
tapped or having come under your control that turn), then it doesn't attack. If there's a cost
associated with having it attack, you're not forced to pay that cost, so it doesn't have to attack
in that case either." Mogg Flunkies (2018-03-16): other attacking creatures don't have to attack
the same player; "If an effect says that Mogg Flunkies attacks or blocks if able and you control
another creature able to attack or block, you must attack or block with Mogg Flunkies and that
creature."; "If you control more than one Mogg Flunkies, they can attack or block together".
Ghostly Prison (2014-02-01): a creature that can't attack you can still attack a planeswalker
you control (M4).
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import (
    ActivateAbilityOption,
    ManaActivationOption,
    NotAlone,
    ObjectOption,
)
from resolve.engine.api import submit, view_for
from resolve.errors import InvalidAnswer
from resolve.events.combat import AttackersDeclared
from resolve.events.mana import ManaSpent
from resolve.events.spells import ActionReversed
from resolve.rules import legality
from resolve.state.combat import AttackPlayer, CombatState
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.turn import Step
from tests.casting_support import activate, options, records, reverse
from tests.combat_support import attack_answer, attack_space, declare_attackers, may_attack
from tests.game_fixtures import answer, request_of
from tests.scenario import Scenario, run_script

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)


def combat_of(state: GameState) -> CombatState:
    assert state.turn is not None and state.turn.combat is not None
    return state.turn.combat


def refused(state: GameState, attacks: dict[ObjectId, PlayerId]) -> bool:
    """Whether the pending declaration refuses ``attacks``, leaving the game unchanged (733.1)."""
    before = request_of(state)
    try:
        declare_attackers(state, attacks)
    except InvalidAnswer:
        assert request_of(state) == before
        return True
    return False


def accepts(make: Callable[[], GameState], attacks: dict[ObjectId, PlayerId]) -> bool:
    """Whether a fresh state from ``make()`` accepts ``attacks``."""
    return not refused(make(), attacks)


# --- 508.1d: "attacks each combat if able" (Juggernaut) ----------------------------------------


def _juggernaut_board() -> tuple[GameState, ObjectId, ObjectId]:
    scenario = Scenario(2)
    juggernaut, bears = scenario.battlefield(P0, ["Juggernaut", "Grizzly Bears"])
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    return scenario.build(), juggernaut, bears


def test_juggernaut_must_attack() -> None:
    """Juggernaut attacks each combat if able (508.1d): a declaration without it obeys no
    requirement where one can be obeyed, so declaring nothing or Grizzly Bears alone is refused;
    Juggernaut alone, or with the Bears, is accepted."""
    state, juggernaut, bears = _juggernaut_board()
    assert refused(state, {})
    assert refused(state, {bears: P1})
    declare_attackers(state, {juggernaut: P1})
    assert juggernaut in combat_of(state).attackers
    state, juggernaut, bears = _juggernaut_board()
    declare_attackers(state, {juggernaut: P1, bears: P1})
    assert set(combat_of(state).attackers) == {juggernaut, bears}


def test_juggernaut_needn_t_attack_when_tapped_or_summoning_sick() -> None:
    """Juggernaut's ruling: a tapped Juggernaut, or one that came under P0's control this turn
    (302.6), doesn't attack, so declaring nothing is legal."""
    scenario = Scenario(2)
    juggernaut, bears = scenario.battlefield(P0, ["Juggernaut", "Grizzly Bears"])
    scenario.tap(juggernaut)
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    assert may_attack(state) == (bears,)
    declare_attackers(state, {})
    assert combat_of(state).attackers == {}
    scenario = Scenario(2)
    (bears,) = scenario.battlefield(P0, ["Grizzly Bears"])
    (juggernaut,) = scenario.battlefield(P0, ["Juggernaut"], entered_turn=3)
    scenario.at(Step.DECLARE_ATTACKERS, begin=True, number=3)
    state = scenario.build()
    assert may_attack(state) == (bears,)
    declare_attackers(state, {})
    assert combat_of(state).attackers == {}


def test_two_requirements_on_one_creature_count_twice() -> None:
    """Juggernaut under Test Warmonger has two requirements (each instance counts, 508.1d); the
    Warmonger itself and Grizzly Bears one each. Every creature must attack: leaving out any one
    disobeys a requirement that could be obeyed."""
    scenario = Scenario(2)
    juggernaut, warmonger, bears = scenario.battlefield(
        P0, ["Juggernaut", "Test Warmonger", "Grizzly Bears"]
    )
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    assert len(attack_space(state).requirements) == 4
    assert refused(state, {juggernaut: P1, warmonger: P1})
    assert refused(state, {warmonger: P1, bears: P1})
    declare_attackers(state, {juggernaut: P1, warmonger: P1, bears: P1})
    assert len(combat_of(state).attackers) == 3


def test_warmonger_affects_only_its_controllers_creatures() -> None:
    """Test Warmonger controlled by P1 puts no requirement on P0's creatures: P0 may attack with
    nothing."""
    scenario = Scenario(2)
    scenario.battlefield(P0, ["Grizzly Bears"])
    scenario.battlefield(P1, ["Test Warmonger"])
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    assert attack_space(state).requirements == ()
    declare_attackers(state, {})


# --- 508.1d's example: Silent Arbiter ---------------------------------------------------------


def test_508_1d_example_silent_arbiter() -> None:
    """508.1d's example, with Silent Arbiter (controlled by P1: its restriction applies to every
    player's creatures): Juggernaut attacks if able, Grizzly Bears has no abilities, at most one
    creature attacks. Only Juggernaut alone is legal."""

    def make() -> GameState:
        scenario = Scenario(2)
        scenario.battlefield(P0, ["Juggernaut", "Grizzly Bears"])
        scenario.battlefield(P1, ["Silent Arbiter"])
        scenario.at(Step.DECLARE_ATTACKERS, begin=True)
        return scenario.build()

    juggernaut, bears = may_attack(make())
    assert accepts(make, {juggernaut: P1})
    assert not accepts(make, {bears: P1})
    assert not accepts(make, {juggernaut: P1, bears: P1})
    assert not accepts(make, {})


def test_two_silent_arbiters_still_allow_one_attacker() -> None:
    """Two Silent Arbiters: still at most one creature attacks (redundant restrictions); one
    attacker is accepted."""
    scenario = Scenario(2)
    bears, lions = scenario.battlefield(P0, ["Grizzly Bears", "Savannah Lions"])
    scenario.battlefield(P1, ["Silent Arbiter", "Silent Arbiter"])
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    assert refused(state, {bears: P1, lions: P1})
    declare_attackers(state, {lions: P1})
    assert list(combat_of(state).attackers) == [lions]


def test_silent_arbiter_counts_attackers_of_every_defending_player() -> None:
    """Three players: "no more than one creature can attack each combat" counts every attacker,
    whichever player it attacks."""
    scenario = Scenario(3)
    bears, lions = scenario.battlefield(P0, ["Grizzly Bears", "Savannah Lions"])
    scenario.battlefield(P2, ["Silent Arbiter"])
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    assert refused(state, {bears: P1, lions: P2})
    declare_attackers(state, {bears: P2})


# --- 508.1c: "can't attack alone" (Mogg Flunkies) ----------------------------------------------


def test_508_1c_example_two_mogg_flunkies_may_attack_together() -> None:
    """508.1c's example (and Mogg Flunkies' ruling): two Mogg Flunkies may attack together
    without other attackers; one alone is refused."""
    scenario = Scenario(2)
    first, second = scenario.battlefield(P0, ["Mogg Flunkies", "Mogg Flunkies"])
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    assert NotAlone(ObjectOption(first)) in attack_space(state).constraints
    assert refused(state, {first: P1})
    assert refused(state, {second: P1})
    declare_attackers(state, {first: P1, second: P1})
    assert set(combat_of(state).attackers) == {first, second}


def test_mogg_flunkies_may_attack_with_a_creature_attacking_another_player() -> None:
    """Mogg Flunkies' ruling: the other attacker needn't attack the same player. Three players:
    the Flunkies attack P1 and Grizzly Bears P2: accepted. The Bears alone are accepted too (only
    the Flunkies can't attack alone)."""

    def make() -> GameState:
        scenario = Scenario(3)
        scenario.battlefield(P0, ["Mogg Flunkies", "Grizzly Bears"])
        scenario.at(Step.DECLARE_ATTACKERS, begin=True)
        return scenario.build()

    flunkies, bears = may_attack(make())
    assert not accepts(make, {flunkies: P2})
    assert accepts(make, {flunkies: P1, bears: P2})
    assert accepts(make, {bears: P2})


def test_mogg_flunkies_under_warmonger_must_attack_with_another_creature() -> None:
    """Mogg Flunkies' ruling: if it attacks if able (Test Warmonger) and another creature is able
    to attack, both must attack. Warmonger came under P0's control this turn (it can't attack);
    the Flunkies and Grizzly Bears must both attack: either alone, or neither, is refused."""

    def make() -> GameState:
        scenario = Scenario(2)
        scenario.battlefield(P0, ["Mogg Flunkies", "Grizzly Bears"])
        scenario.battlefield(P0, ["Test Warmonger"], entered_turn=2)
        scenario.at(Step.DECLARE_ATTACKERS, begin=True, number=2)
        return scenario.build()

    flunkies, bears = may_attack(make())
    assert accepts(make, {flunkies: P1, bears: P1})
    assert not accepts(make, {bears: P1})
    assert not accepts(make, {flunkies: P1})
    assert not accepts(make, {})


def test_mogg_flunkies_alone_under_warmonger_doesn_t_attack() -> None:
    """Under Test Warmonger (summoning sick) with no other creature able to attack, the Flunkies'
    requirement can't be obeyed without breaking its restriction: no attack is legal, and
    attacking alone is refused."""
    scenario = Scenario(2)
    (flunkies,) = scenario.battlefield(P0, ["Mogg Flunkies"])
    scenario.battlefield(P0, ["Test Warmonger"], entered_turn=2)
    scenario.at(Step.DECLARE_ATTACKERS, begin=True, number=2)
    state = scenario.build()
    assert refused(state, {flunkies: P1})
    declare_attackers(state, {})
    assert combat_of(state).attackers == {}


# --- 508.1c: "can't attack unless" (Test Stomper) -----------------------------------------------


def _stomper_board(lands: int) -> tuple[GameState, ObjectId]:
    scenario = Scenario(2)
    (stomper,) = scenario.battlefield(P0, ["Test Stomper"])
    scenario.battlefield(P0, ["Forest"] * lands)
    scenario.battlefield(P0, ["Grizzly Bears"])
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    return scenario.build(), stomper


def test_topiary_style_restriction() -> None:
    """Test Stomper can't attack unless its controller controls seven or more lands (508.1c):
    with six Forests it isn't offered (the prohibition cites 508.1c); with seven it may attack.
    Its blocking half is in test_509_1c_blocking_requirements.py."""
    state, stomper = _stomper_board(6)
    assert stomper not in may_attack(state)
    verdict = legality.allowed(state, legality.AttackAction(P0, stomper, AttackPlayer(P1)))
    assert not verdict.allowed and "508.1c" in verdict.rules
    state, stomper = _stomper_board(7)
    assert stomper in may_attack(state)
    declare_attackers(state, {stomper: P1})
    assert stomper in combat_of(state).attackers


# --- 508.1d, 508.1g-j: costs (Ghostly Prison) -----------------------------------------------------


def _prison_board(
    players: int = 2,
    plains: int = 2,
    prisons: int = 1,
    creatures: tuple[str, ...] = ("Grizzly Bears",),
) -> tuple[GameState, list[ObjectId], list[ObjectId]]:
    scenario = Scenario(players)
    attackers = scenario.battlefield(P0, list(creatures))
    lands = scenario.battlefield(P0, ["Plains"] * plains)
    scenario.battlefield(P1, ["Ghostly Prison"] * prisons)
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    return scenario.build(), attackers, lands


def test_508_1d_a_cost_isnt_required() -> None:
    """Juggernaut must attack if able, but attacking P1 (Ghostly Prison's controller, the only
    opponent) needs a cost, which P0 isn't required to pay (508.1d, Juggernaut's ruling): no
    attack is legal. In a three-player game P2 can be attacked for free, so Juggernaut must
    attack: declaring nothing is refused, and attacking P2 is accepted."""
    state, (juggernaut,), _ = _prison_board(creatures=("Juggernaut",))
    declare_attackers(state, {})
    assert combat_of(state).attackers == {}
    state, (juggernaut,), _ = _prison_board(players=3, creatures=("Juggernaut",))
    assert refused(state, {})
    declare_attackers(state, {juggernaut: P2})
    assert combat_of(state).attackers[juggernaut].target == AttackPlayer(P2)


def test_ghostly_prison_costs_2_per_creature_attacking_its_controller() -> None:
    """Two creatures attack P1, who controls Ghostly Prison: after they tap (508.1f), the total
    cost {4} ({2} for each) is locked in (508.1h) and P0 pays it with four Plains, activating
    their mana abilities (508.1i-j). Then they attack (508.1k), and the declaration's event
    records the cost."""
    state, (bears, lions), plains = _prison_board(
        plains=4, creatures=("Grizzly Bears", "Savannah Lions")
    )
    declare_attackers(state, {bears: P1, lions: P1})
    request = request_of(state)
    assert request.kind is DecisionKind.ACTIVATE_MANA_ABILITIES and request.player == P0
    (payment,) = view_for(state, P0).payments
    assert payment.cost.text == "{4}"
    assert state.objects[bears].tapped and state.objects[lions].tapped  # 508.1f came first
    assert combat_of(state).attackers == {}
    # With every mana ability activated nothing is left to ask: the cost is paid.
    run_script(state, *(activate(p) for p in plains))
    assert set(combat_of(state).attackers) == {bears, lions}
    (declared,) = records(state, AttackersDeclared)
    assert declared.cost is not None and declared.cost.text == "{4}"
    assert records(state, ManaSpent)
    assert all(state.objects[p].tapped for p in plains)


def test_two_ghostly_prisons_cost_4_per_creature() -> None:
    """Two Ghostly Prisons controlled by P1: each adds {2} per creature, {4} for one attacker."""
    state, (bears,), _ = _prison_board(plains=4, prisons=2)
    declare_attackers(state, {bears: P1})
    (payment,) = view_for(state, P0).payments
    assert payment.cost.text == "{4}"


def test_attacking_another_player_costs_nothing() -> None:
    """Three players, Ghostly Prison controlled by P1: Grizzly Bears attacking P2 needs no cost,
    so nothing is asked and it attacks; attacking P1 too costs {2} for the one creature attacking
    P1 only."""
    state, (bears,), _ = _prison_board(players=3)
    declare_attackers(state, {bears: P2})
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION
    assert bears in combat_of(state).attackers
    assert records(state, AttackersDeclared)[0].cost is None
    state, (bears, lions), _ = _prison_board(
        players=3, creatures=("Grizzly Bears", "Savannah Lions")
    )
    declare_attackers(state, {bears: P1, lions: P2})
    (payment,) = view_for(state, P0).payments
    assert payment.cost.text == "{2}"


def test_ghostly_prison_doesnt_tax_its_controllers_own_attacks() -> None:
    """Ghostly Prison controlled by P0, the attacking player: "attack you" is P0, who isn't
    attacked, so attacking P1 costs nothing."""
    scenario = Scenario(2)
    (bears,) = scenario.battlefield(P0, ["Grizzly Bears", "Ghostly Prison"])[:1]
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    assert attack_space(state).costly == ()
    declare_attackers(state, {bears: P1})
    assert bears in combat_of(state).attackers


def test_an_unpaid_cost_reverses_the_declaration_and_asks_again() -> None:
    """P0 has one Plains for a {2} cost: after activating it and choosing to pay, the cost can't
    be paid (508.1j: no partial payments), so the declaration is illegal (508.1, 733.1): P0 is
    asked which mana abilities to reverse (reversing the Plains), the game returns to before the
    declaration (the Bears untapped, no attackers, the Plains untapped, no mana), and P0 declares
    again."""
    state, (bears,), (plains,) = _prison_board(plains=1)
    declare_attackers(state, {bears: P1})
    run_script(state, activate(plains))  # no ability left to activate: it tries to pay
    request = request_of(state)
    assert request.kind is DecisionKind.REVERSE_MANA_ABILITIES and request.player == P0
    run_script(state, reverse(ManaActivationOption(0, plains, 0)))
    assert request_of(state).kind is DecisionKind.DECLARE_ATTACKERS
    assert not state.objects[bears].tapped and not state.objects[plains].tapped
    assert state.player(P0).mana_pool == []
    assert combat_of(state).attackers == {}
    (reversed_,) = records(state, ActionReversed)
    assert reversed_.player == P0 and reversed_.declaration
    assert records(state, AttackersDeclared) == []
    declare_attackers(state, {})
    assert combat_of(state).attackers == {}


def test_a_kept_mana_ability_stays_after_the_reversal() -> None:
    """733.1: P0 keeps the Plains' activation when the declaration is reversed: the Plains stays
    tapped and its {W} stays in P0's pool; the Bears untap."""
    state, (bears,), (plains,) = _prison_board(plains=1)
    declare_attackers(state, {bears: P1})
    run_script(state, activate(plains), reverse())
    assert request_of(state).kind is DecisionKind.DECLARE_ATTACKERS
    assert state.objects[plains].tapped and len(state.player(P0).mana_pool) == 1
    assert not state.objects[bears].tapped


def test_508_1f_attackers_tap_before_costs() -> None:
    """An attacking Llanowar Elves taps as it is declared (508.1f), before the cost is paid
    (508.1h-j), so its mana ability isn't offered to pay Ghostly Prison's {2}: only the Forest's
    is. One mana isn't enough, so the declaration is reversed."""
    scenario = Scenario(2)
    elves, forest = scenario.battlefield(P0, ["Llanowar Elves", "Forest"])
    scenario.battlefield(P1, ["Ghostly Prison"])
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    declare_attackers(state, {elves: P1})
    offered = {o.object for o in options(state) if isinstance(o, ActivateAbilityOption)}
    assert offered == {forest}
    run_script(state, activate(forest), reverse(ManaActivationOption(0, forest, 0)))
    assert request_of(state).kind is DecisionKind.DECLARE_ATTACKERS
    assert not state.objects[elves].tapped


def test_an_unpayable_cost_with_no_mana_ability_reverses_at_once() -> None:
    """With no mana ability to activate, a {2} cost can't be paid: nothing is asked about mana,
    the declaration is reversed (no mana ability to reverse, so no question) and asked again."""
    state, (bears,), _ = _prison_board(plains=0)
    declare_attackers(state, {bears: P1})
    assert request_of(state).kind is DecisionKind.DECLARE_ATTACKERS
    assert not state.objects[bears].tapped
    assert len(records(state, ActionReversed)) == 1


def test_costly_picks_are_marked_in_the_space() -> None:
    """The space marks each pick that needs a cost (508.1h): Grizzly Bears attacking P1 (Ghostly
    Prison) but not attacking P2."""
    state, (bears,), _ = _prison_board(players=3)
    space = attack_space(state)
    ((pick),) = space.costly
    assert pick.item == ObjectOption(bears) and pick.choice == space.choices[0][0]


def test_an_illegal_answer_to_a_costly_declaration_is_refused_first() -> None:
    """A malformed answer is refused before anything taps or is paid (733.1)."""
    state, (bears,), _ = _prison_board()
    with pytest.raises(InvalidAnswer):
        submit(state, answer(state, attack_answer(state, {bears: P1}).__class__(((0, 0),))))
    assert not state.objects[bears].tapped
