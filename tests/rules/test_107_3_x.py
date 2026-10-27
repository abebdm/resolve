"""107.3 and 601.2b: X in a spell's mana cost, announced as the spell is cast.

From the pinned CR:

- 107.3a: if a spell's mana cost has an {X} and its text doesn't define X, its controller chooses
  and announces the value of X as part of casting it. While the spell is on the stack, any X in
  its mana cost equals that value.
- 107.1b: a player can't choose a negative number; 107.1c: "any number" is zero or more.
- 601.2b: the value of X is announced after the modes and before the targets (601.2c).
- 601.2f: the total cost is the mana cost with the announced value in place of X; that is what is
  paid (601.2g-h).
- 202.3e: an object's mana value counts X as 0 off the stack and as the chosen number on it.
- 733.1: a cast whose total cost can't be paid is reversed (an X too large to pay).

The fixture is the invented instant Test Blaze, {X}{R}: "Test Blaze deals X damage to any
target." The X decision is a ``ChooseNumber(0, None)`` (design.md §17.8): every value is offered;
whether it can be paid is found out by paying (733.1).
"""

from __future__ import annotations

import pytest

from resolve.data.mana_cost import parse_mana_cost
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import ChooseNumber, Number, PlayerOption
from resolve.effects.characteristics import characteristics
from resolve.engine.api import submit
from resolve.engine.view import view_for
from resolve.errors import InvalidAnswer
from resolve.events.base import AnswerRecord
from resolve.events.damage import DamageDealt
from resolve.events.spells import (
    ActionReversed,
    BecameTargets,
    SpellCast,
    SpellResolved,
    XAnnounced,
)
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import ManaType
from resolve.state.spell import TargetPlayer
from resolve.state.turn import Phase
from resolve.state.turn import Step as TurnStep
from resolve.state.zones import Zone
from tests.casting_support import activate, cast, choose_targets, choose_x, pass_, records
from tests.game_fixtures import answer, request_of
from tests.scenario import Scenario, run_script

P0, P1 = PlayerId(0), PlayerId(1)
R = ManaType.RED
OPPONENT = PlayerOption(P1)


def _blaze(*mana: ManaType) -> tuple[Scenario, ObjectId]:
    """P0 with Test Blaze in hand and ``mana`` in their pool, in their main phase."""
    scenario = Scenario(2)
    (blaze,) = scenario.hand(P0, ["Test Blaze"])
    scenario.mana(P0, *mana)
    scenario.at(Phase.PRECOMBAT_MAIN)
    return scenario, blaze


def test_107_3a_x_is_announced_and_added_to_the_cost() -> None:
    """Test Blaze with four red mana: X is asked (any number from 0), 3 is announced and joins
    the spell's record; the total cost is {3}{R} (601.2f), all four mana are spent, and Test
    Blaze deals 3 damage as it resolves (107.3a)."""
    scenario, blaze = _blaze(R, R, R, R)
    state = scenario.build()
    life = state.player(P1).life
    run_script(state, cast(blaze, P0))
    request = request_of(state)
    assert request.kind is DecisionKind.CHOOSE_X
    assert request.space == ChooseNumber(0, None)
    assert "107.3a" in request.rules and "601.2b" in request.rules
    run_script(state, choose_x(3), choose_targets(OPPONENT))
    (spell,) = state.stack
    record = state.objects[spell].spell
    assert record is not None and record.x == 3
    (announced,) = records(state, XAnnounced)
    assert (announced.spell, announced.x) == (spell, 3)
    (cast_event,) = records(state, SpellCast)
    assert cast_event.total_cost == parse_mana_cost("{3}{R}")
    assert len(cast_event.mana_spent) == 4 and state.player(P0).mana_pool == []
    run_script(state, pass_(P0), pass_(P1))
    (damage,) = records(state, DamageDealt)
    assert damage.to_players == ((P1, 3),)
    assert state.player(P1).life == life - 3


def test_107_3a_x_may_be_zero() -> None:
    """X = 0 (107.1c): the total cost is {R}; Test Blaze deals 0 damage, which isn't dealt at all
    (120.8), and still resolves."""
    scenario, blaze = _blaze(R)
    state = scenario.build()
    run_script(state, cast(blaze, P0), choose_x(0), choose_targets(OPPONENT))
    (cast_event,) = records(state, SpellCast)
    assert cast_event.total_cost == parse_mana_cost("{R}")
    run_script(state, pass_(P0), pass_(P1))
    assert records(state, DamageDealt) == []
    assert len(records(state, SpellResolved)) == 1


def test_107_1b_x_cant_be_negative() -> None:
    scenario, blaze = _blaze(R)
    state = scenario.build()
    run_script(state, cast(blaze, P0))
    with pytest.raises(InvalidAnswer):
        submit(state, answer(state, Number(-1)))
    assert request_of(state).kind is DecisionKind.CHOOSE_X


def test_202_3e_mana_value_on_the_stack_includes_x() -> None:
    """Test Blaze's mana value is 1 in hand (X is 0 off the stack), 4 on the stack with X = 3, and
    1 again in the graveyard after it resolves (202.3e)."""
    scenario, blaze = _blaze(R, R, R, R)
    state = scenario.build()
    assert characteristics(state, blaze).mana_value == 1
    run_script(state, cast(blaze, P0), choose_x(3), choose_targets(OPPONENT))
    (spell,) = state.stack
    assert characteristics(state, spell).mana_value == 4
    run_script(state, pass_(P0), pass_(P1))
    (card,) = state.player(P0).graveyard
    assert state.objects[card].zone == Zone.graveyard(P0)
    assert characteristics(state, card).mana_value == 1


def test_601_2b_x_comes_before_targets() -> None:
    """X is announced (601.2b) before the targets are chosen (601.2c): the CHOOSE_X answer comes
    first, and XAnnounced is logged before BecameTargets."""
    scenario, blaze = _blaze(R, R)
    scenario.battlefield(P1, ["Grizzly Bears"])
    state = scenario.build()
    run_script(state, cast(blaze, P0), choose_x(1))
    assert request_of(state).kind is DecisionKind.CHOOSE_TARGETS
    run_script(state, choose_targets(OPPONENT))
    kinds = [r.kind for r in records(state, AnswerRecord)]
    assert kinds == [
        DecisionKind.PRIORITY_ACTION,
        DecisionKind.CHOOSE_X,
        DecisionKind.CHOOSE_TARGETS,
    ]
    logged = [e.record for e in state.event_log]
    announced = next(i for i, r in enumerate(logged) if isinstance(r, XAnnounced))
    became = next(i for i, r in enumerate(logged) if isinstance(r, BecameTargets))
    assert announced < became
    (spell,) = state.stack
    record = state.objects[spell].spell
    assert record is not None and record.targets == ((TargetPlayer(P1),),)


def test_733_1_an_x_too_large_to_pay_is_reversed() -> None:
    """X = 5 with two red mana: the total cost {5}{R} can't be paid, so the cast is reversed
    (733.1): Test Blaze is back in hand, the mana still in the pool, and P0 has priority."""
    scenario, blaze = _blaze(R, R)
    state = scenario.build()
    run_script(state, cast(blaze, P0), choose_x(5), choose_targets(OPPONENT))
    assert state.stack == [] and blaze in state.player(P0).hand
    assert len(state.player(P0).mana_pool) == 2
    assert len(records(state, ActionReversed)) == 1 and not records(state, SpellCast)
    request = request_of(state)
    assert request.kind is DecisionKind.PRIORITY_ACTION and request.player == P0


def test_601_2g_the_payment_under_way_is_the_total_with_x() -> None:
    """While Test Blaze with X = 2 is being paid from three Mountains, the payment every player
    sees is the total cost {2}{R} (601.2f-g), not the printed {X}{R}."""
    scenario = Scenario(2)
    (blaze,) = scenario.hand(P0, ["Test Blaze"])
    mountains = scenario.battlefield(P0, ["Mountain", "Mountain", "Mountain"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(blaze, P0), choose_x(2), choose_targets(OPPONENT))
    assert request_of(state).kind is DecisionKind.ACTIVATE_MANA_ABILITIES
    for player in (P0, P1):
        (payment,) = view_for(state, player).payments
        assert payment.cost == parse_mana_cost("{2}{R}")
    run_script(state, *(activate(m) for m in mountains))  # then "pay" is the only answer
    (cast_event,) = records(state, SpellCast)
    assert cast_event.total_cost == parse_mana_cost("{2}{R}")


def test_107_3a_the_caster_announces_x_even_out_of_turn() -> None:
    """Three players, P0's upkeep: P1 casts Test Blaze after P0 passes; the value of X is chosen
    by the spell's controller (107.3a), so P1 is asked."""
    scenario = Scenario(3)
    (blaze,) = scenario.hand(P1, ["Test Blaze"])
    scenario.mana(P1, R, R)
    scenario.at(TurnStep.UPKEEP)
    state = scenario.build()
    run_script(state, pass_(P0), cast(blaze, P1))
    request = request_of(state)
    assert request.kind is DecisionKind.CHOOSE_X
    assert (request.player, request.for_player) == (P1, P1)


def test_733_1_a_reversed_cast_forgets_its_x() -> None:
    """After an X too large to pay is reversed, casting Test Blaze again asks X again (the
    reversal restores the game, 733.1), and the new value is the one used."""
    scenario, blaze = _blaze(R, R)
    state = scenario.build()
    run_script(state, cast(blaze, P0), choose_x(5), choose_targets(OPPONENT))
    assert blaze in state.player(P0).hand
    run_script(state, cast(blaze, P0))
    assert request_of(state).kind is DecisionKind.CHOOSE_X
    run_script(state, choose_x(1), choose_targets(OPPONENT))
    (cast_event,) = records(state, SpellCast)
    assert cast_event.total_cost == parse_mana_cost("{1}{R}")
    (spell,) = state.stack
    record = state.objects[spell].spell
    assert record is not None and record.x == 1


def test_202_3e_mana_value_with_x_zero_and_two_xs() -> None:
    """On the stack, Test Blaze with X = 0 has mana value 1; Test Twin Blaze ({X}{X}{R}) with
    X = 3 has 7, each {X} counting the value (107.3a, 202.3e)."""
    scenario = Scenario(2)
    blaze, twin = scenario.stack(P0, ["Test Blaze", "Test Twin Blaze"])
    scenario.x(blaze, 0).x(twin, 3)
    state = scenario.build()
    assert characteristics(state, blaze).mana_value == 1
    assert characteristics(state, twin).mana_value == 7
    record = state.objects[twin].spell
    assert record is not None and record.total_cost == parse_mana_cost("{6}{R}")


def test_601_2b_x_is_public() -> None:
    """The value of X is announced (601.2b): every player's view of the spell shows it."""
    scenario, blaze = _blaze(R, R, R)
    state = scenario.build()
    run_script(state, cast(blaze, P0), choose_x(2))
    (spell,) = state.stack
    for player in (P0, P1):
        (seen,) = [o for o in view_for(state, player).stack if o.id == spell]
        assert seen.spell is not None and seen.spell.x == 2
