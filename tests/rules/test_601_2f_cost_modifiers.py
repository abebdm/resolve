"""601.2f: the total cost, with cost increases and reductions (118.7, 113.6, 601.8).

From the pinned CR:

- 601.2f: the total cost is the mana cost or alternative cost, plus additional costs and cost
  increases, minus cost reductions; reduced to nothing, its mana component is {0}, never less.
  Then effects that directly affect the total are applied, and the total is locked in: effects
  that would change it after that have no effect.
- 118.7a: a reduction by an amount of generic mana affects only the generic component, never the
  colored or colorless components.
- 113.6: a permanent's static abilities function only while it is on the battlefield.
- 601.8: casting a spell that alters costs won't affect spells already on the stack.
- 202.3: the mana value comes from the mana cost, which a reduction doesn't change (Emerald
  Medallion's ruling: "it changes only the total cost you pay").
- 601.2b, 107.3a: X is announced before the total cost is determined (Medallion's ruling: "you
  choose the value of X before calculating the spell's total cost").

Test Thorn ("Spells cost {1} more to cast.") is a test-only increase (the first real one is the
commander tax, M7). Emerald Medallion: "Green spells you cast cost {1} less to cast."
"""

from __future__ import annotations

from resolve.data.mana_cost import ManaCost, parse_mana_cost
from resolve.decisions.kinds import DecisionKind
from resolve.effects.characteristics import characteristics
from resolve.engine.api import view_for
from resolve.events.spells import SpellCast
from resolve.state.game import move_object
from resolve.state.ids import PlayerId
from resolve.state.mana import Mana, ManaType
from resolve.state.turn import Phase, Step
from resolve.state.zones import BATTLEFIELD, Zone
from tests.casting_support import activate, cast, choose_x, pass_, pay, records
from tests.game_fixtures import request_of
from tests.scenario import Scenario, run_script

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)
G = ManaType.GREEN


def cost(text: str) -> ManaCost:
    return parse_mana_cost(text)


def test_601_2f_medallion_reduces_a_green_spells_generic_mana() -> None:
    """With Emerald Medallion, Grizzly Bears ({1}{G}) costs {G}: one Forest pays it, and the
    total cost the cast records is {G}."""
    scenario = Scenario(2)
    (bears,) = scenario.hand(P0, ["Grizzly Bears"])
    _, forest = scenario.battlefield(P0, ["Emerald Medallion", "Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(bears, P0))
    assert request_of(state).kind is DecisionKind.ACTIVATE_MANA_ABILITIES
    (payment,) = view_for(state, P0).payments
    assert payment.cost == cost("{G}")
    run_script(state, activate(forest))
    (cast_event,) = records(state, SpellCast)
    assert cast_event.total_cost == cost("{G}")
    assert cast_event.mana_spent == (Mana(G, forest),)


def test_118_7a_it_cant_reduce_colored_mana() -> None:
    """Llanowar Elves ({G}) has no generic mana to reduce: with Emerald Medallion its total cost
    is still {G}, so a Plains alone can't pay it and the cast is reversed (733.1). Grizzly Bears
    in the same hand shows the Medallion works: {G}."""
    scenario = Scenario(2)
    elves, _ = scenario.hand(P0, ["Llanowar Elves", "Grizzly Bears"])
    _, plains = scenario.battlefield(P0, ["Emerald Medallion", "Plains"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(elves, P0))
    (payment,) = view_for(state, P0).payments
    assert payment.cost == cost("{G}")
    run_script(state, activate(plains))
    assert request_of(state).kind is DecisionKind.REVERSE_MANA_ABILITIES
    assert records(state, SpellCast) == []

    scenario = Scenario(2)
    _, bears = scenario.hand(P0, ["Llanowar Elves", "Grizzly Bears"])
    _, forest = scenario.battlefield(P0, ["Emerald Medallion", "Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(bears, P0), activate(forest))
    (cast_event,) = records(state, SpellCast)
    assert cast_event.total_cost == cost("{G}")


def test_601_2f_two_medallions_stop_at_zero_generic() -> None:
    """Two Emerald Medallions reduce Grizzly Bears ({1}{G}) by {2}: the generic part can't go
    below nothing (601.2f), and the {G} stays (118.7a): {G}. Hill Giant ({3}{R}) isn't green,
    so neither Medallion changes it."""
    scenario = Scenario(2)
    bears, _ = scenario.hand(P0, ["Grizzly Bears", "Hill Giant"])
    scenario.battlefield(P0, ["Emerald Medallion", "Emerald Medallion"])
    scenario.mana(P0, G)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(bears, P0))
    (cast_event,) = records(state, SpellCast)
    assert cast_event.total_cost == cost("{G}")

    scenario = Scenario(2)
    (giant,) = scenario.hand(P0, ["Hill Giant"])
    scenario.battlefield(P0, ["Emerald Medallion", "Emerald Medallion", "Mountain"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(giant, P0))
    (payment,) = view_for(state, P0).payments
    assert payment.cost == cost("{3}{R}")


def test_601_2f_two_copies_of_a_reducer_both_apply() -> None:
    """601.2f subtracts all cost reductions: two Emerald Medallions take {2} off Test Growth
    ({X}{G}) with X = 3 ({3}{G}): {1}{G}; with X = 2: {G}."""
    for x, total in ((3, "{1}{G}"), (2, "{G}")):
        scenario = Scenario(2)
        (growth,) = scenario.hand(P0, ["Test Growth"])
        scenario.battlefield(P0, ["Emerald Medallion", "Emerald Medallion", "Forest"])
        scenario.at(Phase.PRECOMBAT_MAIN)
        state = scenario.build()
        run_script(state, cast(growth, P0), choose_x(x))
        (payment,) = view_for(state, P0).payments
        assert payment.cost == cost(total), x


def test_601_2f_a_tapped_medallion_still_reduces() -> None:
    """Being tapped doesn't stop a permanent's static abilities (110.5b, 113.6): Grizzly Bears
    still costs {G}."""
    scenario = Scenario(2)
    (bears,) = scenario.hand(P0, ["Grizzly Bears"])
    medallion, _ = scenario.battlefield(P0, ["Emerald Medallion", "Forest"])
    scenario.tap(medallion)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(bears, P0))
    (payment,) = view_for(state, P0).payments
    assert payment.cost == cost("{G}")


def test_601_2f_two_reductions_together_reduce_more() -> None:
    """Test Raptor ({1}{G}) is a green Dinosaur, so Emerald Medallion and Kinjalli's Caller both
    apply. With Test Thorn as well: {1}{G} plus {1} is {2}{G}, minus {2} is {G} (601.2f). One
    reduction missing, or the reductions before the increase, would give {1}{G}."""
    scenario = Scenario(2)
    (raptor,) = scenario.hand(P0, ["Test Raptor"])
    scenario.battlefield(P0, ["Emerald Medallion", "Kinjalli's Caller", "Test Thorn"])
    scenario.mana(P0, G)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(raptor, P0))
    (cast_event,) = records(state, SpellCast)
    assert cast_event.total_cost == cost("{G}")


def test_601_2f_only_spells_you_cast() -> None:
    """Three players. P1 and P2 control Emerald Medallions; P0's Grizzly Bears still costs
    {1}{G} ("spells you cast" are the Medallion's controller's). P1's Test Growth with X = 2
    ({2}{G}) costs {1}{G}: only P1's Medallion applies to it, not P2's."""
    scenario = Scenario(3)
    (bears,) = scenario.hand(P0, ["Grizzly Bears"])
    scenario.battlefield(P0, ["Forest"])
    scenario.battlefield(P1, ["Emerald Medallion"])
    scenario.battlefield(P2, ["Emerald Medallion"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(bears, P0))
    (payment,) = view_for(state, P0).payments
    assert payment.cost == cost("{1}{G}")

    scenario = Scenario(3)
    (growth,) = scenario.hand(P1, ["Test Growth"])
    scenario.battlefield(P1, ["Emerald Medallion", "Forest"])
    scenario.battlefield(P2, ["Emerald Medallion"])
    scenario.at(Phase.PRECOMBAT_MAIN, active=P1)
    state = scenario.build()
    run_script(state, cast(growth, P1), choose_x(2, P1))
    (payment,) = view_for(state, P1).payments
    assert payment.cost == cost("{1}{G}")


def test_601_2f_you_is_the_controller_not_the_owner() -> None:
    """ "You" is the Medallion's controller (109.5). P0 controls an Emerald Medallion P1 owns:
    P0's Grizzly Bears costs {G}, P1's costs {1}{G}."""
    for caster, total in ((P0, "{G}"), (P1, "{1}{G}")):
        scenario = Scenario(2)
        (bears,) = scenario.hand(caster, ["Grizzly Bears"])
        scenario.battlefield(P0, ["Emerald Medallion"], owner=P1)
        scenario.battlefield(caster, ["Forest"])
        scenario.at(Phase.PRECOMBAT_MAIN, active=caster)
        state = scenario.build()
        run_script(state, cast(bears, caster))
        (payment,) = view_for(state, caster).payments
        assert payment.cost == cost(total), caster


def test_202_3_mana_value_isnt_changed() -> None:
    """Grizzly Bears cast for {G} with Emerald Medallion is still a spell with mana cost {1}{G}
    and mana value 2 (202.3, 118.7: paying the reduced cost counts as paying the mana cost), and
    so is the permanent it becomes."""
    scenario = Scenario(2)
    (bears,) = scenario.hand(P0, ["Grizzly Bears"])
    scenario.battlefield(P0, ["Emerald Medallion"])
    scenario.mana(P0, G)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(bears, P0))
    (cast_event,) = records(state, SpellCast)
    assert cast_event.total_cost == cost("{G}")
    chars = characteristics(state, cast_event.spell)
    assert chars.mana_cost == cost("{1}{G}")
    assert chars.mana_value == 2
    run_script(state, pass_(P0), pass_(P1))
    permanent = state.battlefield[-1]
    assert characteristics(state, permanent).name == "Grizzly Bears"
    assert characteristics(state, permanent).mana_value == 2


def test_601_2f_x_is_chosen_before_the_reduction() -> None:
    """Test Growth ({X}{G}) with Emerald Medallion: X is announced first (601.2b), then the total
    {X}{G} with that value is reduced. X = 2 costs {1}{G}; X = 1 costs {G}; X = 0 costs {G}
    (there is no generic mana to reduce, 118.7a)."""
    for x, total in ((2, "{1}{G}"), (1, "{G}"), (0, "{G}")):
        scenario = Scenario(2)
        (growth,) = scenario.hand(P0, ["Test Growth"])
        scenario.battlefield(P0, ["Emerald Medallion", "Forest"])
        scenario.at(Phase.PRECOMBAT_MAIN)
        state = scenario.build()
        run_script(state, cast(growth, P0), choose_x(x))
        (payment,) = view_for(state, P0).payments
        assert payment.cost == cost(total), x


def test_107_3a_x_keeps_its_announced_value_after_the_reduction() -> None:
    """The reduction changes the generic mana paid, not X (107.3a, 202.3e): Test Growth with
    X = 2 and Emerald Medallion is paid {1}{G}, and on the stack its X is still 2 and its mana
    value 3."""
    scenario = Scenario(2)
    (growth,) = scenario.hand(P0, ["Test Growth"])
    _, first, second = scenario.battlefield(P0, ["Emerald Medallion", "Forest", "Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(growth, P0), choose_x(2), activate(first), activate(second))
    (cast_event,) = records(state, SpellCast)
    assert cast_event.total_cost == cost("{1}{G}")
    record = state.object(cast_event.spell).spell
    assert record is not None and record.x == 2
    assert characteristics(state, cast_event.spell).mana_value == 3


def test_601_2f_the_total_is_locked_in() -> None:
    """Once the total is determined it is locked in (601.2f): if Emerald Medallion leaves the
    battlefield while Grizzly Bears is being paid, the total stays {G}; if one arrives then, the
    total stays {1}{G}. (No M2 card can move a permanent during 601.2g, so the test moves the
    Medallion directly, as an effect would.)"""
    scenario = Scenario(2)
    (bears,) = scenario.hand(P0, ["Grizzly Bears"])
    medallion, forest = scenario.battlefield(P0, ["Emerald Medallion", "Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(bears, P0))
    assert request_of(state).kind is DecisionKind.ACTIVATE_MANA_ABILITIES
    move_object(state, medallion, Zone.graveyard(P0))
    (payment,) = view_for(state, P0).payments
    assert payment.cost == cost("{G}")
    run_script(state, activate(forest))
    (cast_event,) = records(state, SpellCast)
    assert cast_event.total_cost == cost("{G}")

    scenario = Scenario(2)
    (bears,) = scenario.hand(P0, ["Grizzly Bears"])
    (medallion,) = scenario.graveyard(P0, ["Emerald Medallion"])
    first, second = scenario.battlefield(P0, ["Forest", "Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(bears, P0))
    move_object(state, medallion, BATTLEFIELD, controller=P0)
    (payment,) = view_for(state, P0).payments
    assert payment.cost == cost("{1}{G}")
    run_script(state, activate(first), activate(second))
    (cast_event,) = records(state, SpellCast)
    assert cast_event.total_cost == cost("{1}{G}")


def test_113_6_a_flash_spell_cast_over_a_medallion_spell_pays_in_full() -> None:
    """113.6: P0 casts Ashcoat Bear (flash, {1}{G}) in response to their own Emerald Medallion
    spell: the Medallion isn't on the battlefield, so the Bear costs {1}{G}. The Bear resolves,
    then the Medallion; the next green spell, Grizzly Bears, costs {G}."""
    scenario = Scenario(2)
    ashcoat, bears = scenario.hand(P0, ["Ashcoat Bear", "Grizzly Bears"])
    scenario.stack(P0, ["Emerald Medallion"])
    first, second, third = scenario.battlefield(P0, ["Forest", "Forest", "Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(ashcoat, P0), activate(first), activate(second), pay())
    (ashcoat_cast,) = records(state, SpellCast)
    assert ashcoat_cast.total_cost == cost("{1}{G}")
    run_script(state, pass_(P0), pass_(P1))  # the Ashcoat Bear resolves
    run_script(state, pass_(P0), pass_(P1))  # the Medallion resolves
    assert [characteristics(state, o).name for o in state.battlefield[-2:]] == [
        "Ashcoat Bear",
        "Emerald Medallion",
    ]
    run_script(state, cast(bears, P0), activate(third))
    _, bears_cast = records(state, SpellCast)
    assert bears_cast.total_cost == cost("{G}")


def test_601_8_a_reducer_arriving_doesnt_change_a_spell_already_cast() -> None:
    """601.8: Grizzly Bears is cast for {1}{G}; then, with the Bears on the stack, an Emerald
    Medallion comes onto the battlefield (the test moves it, as an effect would). The Bears'
    total and the mana spent are unchanged, and it resolves with no further payment."""
    scenario = Scenario(2)
    (bears,) = scenario.hand(P0, ["Grizzly Bears"])
    (medallion,) = scenario.graveyard(P0, ["Emerald Medallion"])
    first, second = scenario.battlefield(P0, ["Forest", "Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(bears, P0), activate(first), activate(second))
    (cast_event,) = records(state, SpellCast)
    assert cast_event.total_cost == cost("{1}{G}")
    move_object(state, medallion, BATTLEFIELD, controller=P0)
    record = state.object(cast_event.spell).spell
    assert record is not None and record.total_cost == cost("{1}{G}")
    assert record.mana_spent == cast_event.mana_spent
    run_script(state, pass_(P0), pass_(P1))
    assert characteristics(state, state.battlefield[-1]).name == "Grizzly Bears"
    assert len(records(state, SpellCast)) == 1 and view_for(state, P0).payments == ()


def test_601_8_spells_already_on_the_stack_keep_their_total() -> None:
    """601.8: Grizzly Bears is on the stack with its total {1}{G} below P0's Emerald Medallion
    spell; once the Medallion resolves, the Bears' record still has {1}{G}."""
    scenario = Scenario(2)
    _, bears = scenario.stack(P0, ["Emerald Medallion", "Grizzly Bears"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1))
    assert characteristics(state, state.battlefield[-1]).name == "Emerald Medallion"
    record = state.object(bears).spell
    assert record is not None and record.total_cost == cost("{1}{G}")


def test_113_6_a_medallion_on_the_stack_reduces_nothing() -> None:
    """113.6: Emerald Medallion's ability functions only on the battlefield. With the Medallion
    spell on the stack, Ashcoat Bear (flash, {1}{G}) costs {1}{G}; one in P0's hand or graveyard
    reduces nothing either. Once a Medallion is on the battlefield, the Bear costs {G}."""
    scenario = Scenario(2)
    ashcoat, _ = scenario.hand(P0, ["Ashcoat Bear", "Emerald Medallion"])
    scenario.graveyard(P0, ["Emerald Medallion"])
    scenario.stack(P0, ["Emerald Medallion"])
    scenario.battlefield(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(ashcoat, P0))
    (payment,) = view_for(state, P0).payments
    assert payment.cost == cost("{1}{G}")

    scenario = Scenario(2)
    (ashcoat,) = scenario.hand(P0, ["Ashcoat Bear"])
    scenario.battlefield(P0, ["Emerald Medallion", "Forest"])
    scenario.at(Step.UPKEEP, active=P1, priority=P0, passed=[P1])
    state = scenario.build()
    run_script(state, cast(ashcoat, P0))
    (payment,) = view_for(state, P0).payments
    assert payment.cost == cost("{G}")


def test_601_2f_modifiers_apply_in_the_rules_order() -> None:
    """Increases come before reductions (601.2f; Emerald Medallion's ruling): with Test Thorn
    (+{1}) and Emerald Medallion (-{1}), Llanowar Elves ({G}) costs {1}{G} then {G}. Applied the
    other way round, the reduction would find no generic mana and the total would be {1}{G}. The
    Medallion is put onto the battlefield first, so battlefield order isn't what decides. With
    only Test Thorn, the Elves cost {1}{G}."""
    scenario = Scenario(2)
    (elves,) = scenario.hand(P0, ["Llanowar Elves"])
    scenario.battlefield(P0, ["Emerald Medallion", "Test Thorn", "Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(elves, P0))
    (payment,) = view_for(state, P0).payments
    assert payment.cost == cost("{G}")

    scenario = Scenario(2)
    (elves,) = scenario.hand(P0, ["Llanowar Elves"])
    scenario.battlefield(P0, ["Forest"])
    scenario.battlefield(P1, ["Test Thorn"])  # an increase applies whoever controls it
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(elves, P0))
    (payment,) = view_for(state, P0).payments
    assert payment.cost == cost("{1}{G}")
