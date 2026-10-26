"""700.2 and 601.2b: modal spells. Choosing the modes as the spell is cast, and following them as
it resolves.

From the pinned CR:

- 700.2: a modal spell lists options (modes) preceded by an instruction to choose a number of
  them. 601.2b: if the spell is modal, the player announces the mode choice as it is cast, before
  X (601.2b) and the targets (601.2c).
- 700.2a: a mode that would be illegal (no legal targets, for example) can't be chosen.
- 700.2c, 601.2c: a spell needs the targets of a mode only if that mode is chosen; otherwise it is
  treated as though it didn't have them.
- 700.2d: the same mode can't normally be chosen twice; a spell that says "You may choose the same
  mode more than once" can, and is then treated as if that mode appeared that many times in
  sequence. Each instance of a repeated mode may choose the same target or a different one.
- 700.2f, 700.2g: modes can't change once chosen (only targets can, 115.7, M5).
- 608.2c: the spell follows its instructions in the order written: the chosen modes in printed
  order, a repeated mode's instances in sequence.
- 608.2b: the spell is targeted if any target was chosen for any instance (115.6); it doesn't
  resolve only if every one of them is illegal.

The modes are offered as a ``ChooseOne`` of ``ModesOption`` values: each choice once, as the
indices of the chosen modes from 0 in printed order, a repeated mode listed that many times
(design.md §17.8: mode combinations stay enumerated). With one possible choice nothing is asked.

Fixtures: Fiery Confluence ("Choose three. You may choose the same mode more than once. • 1 damage
to each creature. • 2 damage to each opponent. • Destroy target artifact.") and the invented
Test Command ("Choose two — • Destroy target artifact. • Destroy target enchantment. • Draw a
card.").
"""

from __future__ import annotations

import pytest

from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import CastSpellOption, ChooseOne, ModesOption, ObjectOption, Pick
from resolve.engine.api import submit
from resolve.errors import EngineError, InvalidAnswer
from resolve.events.base import AnswerRecord
from resolve.events.damage import DamageDealt
from resolve.events.permanents import PermanentDestroyed
from resolve.events.pipeline import ApplyEvents
from resolve.events.spells import (
    ActionReversed,
    BecameTargets,
    ModesChosen,
    SpellCast,
    SpellResolved,
)
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import ManaType
from resolve.state.spell import TargetObject
from resolve.state.turn import Phase
from resolve.state.zones import Zone
from tests.casting_support import cast, choose_modes, choose_targets, options, pass_, records
from tests.game_fixtures import answer, request_of
from tests.rules.test_115_targets import target_options
from tests.scenario import Scenario, names, run_script

P0, P1 = PlayerId(0), PlayerId(1)
R, U = ManaType.RED, ManaType.BLUE


def _offered(state: GameState) -> list[CastSpellOption]:
    return [o for o in options(state) if isinstance(o, CastSpellOption)]


def _modes_offered(state: GameState) -> list[ModesOption]:
    request = request_of(state)
    assert request.kind is DecisionKind.CHOOSE_MODES
    assert isinstance(request.space, ChooseOne)
    return [o for o in request.space.options if isinstance(o, ModesOption)]


def _confluence(*artifacts: str) -> tuple[Scenario, ObjectId, list[ObjectId]]:
    """P0 with Fiery Confluence in hand and {R}{R}{R}{R}; P1 with Grizzly Bears and
    ``artifacts``."""
    scenario = Scenario(2)
    (confluence,) = scenario.hand(P0, ["Fiery Confluence"])
    permanents = scenario.battlefield(P1, ["Grizzly Bears", *artifacts])
    scenario.mana(P0, R, R, R, R)
    scenario.at(Phase.PRECOMBAT_MAIN)
    return scenario, confluence, permanents


# --- Choosing the modes (601.2b, 700.2a, 700.2d) -----------------------------------------------


def test_700_2d_choose_three_with_repeats_offers_every_multiset() -> None:
    """Fiery Confluence chooses three of its three modes, repeats allowed. With an artifact on the
    battlefield every mode is legal: the 10 multisets of three modes (each once, listed in printed
    order). Without one, "destroy target artifact" can't be chosen (700.2a): the 4 multisets of
    the other two modes."""
    scenario, confluence, _ = _confluence("Sol Ring")
    state = scenario.build()
    run_script(state, cast(confluence, P0))
    offered = _modes_offered(state)
    every = {
        (0, 0, 0), (0, 0, 1), (0, 0, 2), (0, 1, 1), (0, 1, 2),
        (0, 2, 2), (1, 1, 1), (1, 1, 2), (1, 2, 2), (2, 2, 2),
    }  # fmt: skip
    assert len(offered) == 10 and {o.modes for o in offered} == every
    assert request_of(state).rules[:2] == ("601.2b", "700.2")

    scenario, confluence, _ = _confluence()
    state = scenario.build()
    run_script(state, cast(confluence, P0))
    offered = _modes_offered(state)
    assert len(offered) == 4
    assert {o.modes for o in offered} == {(0, 0, 0), (0, 0, 1), (0, 1, 1), (1, 1, 1)}


def test_700_2d_without_repeats_each_mode_is_chosen_at_most_once() -> None:
    """Test Command chooses two of three modes, no repeats (700.2d): with an artifact and an
    enchantment, the three pairs of different modes."""
    scenario = Scenario(2)
    (command,) = scenario.hand(P0, ["Test Command"])
    scenario.battlefield(P1, ["Sol Ring", "Test Totem"])
    scenario.mana(P0, U, U)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(command, P0))
    assert {o.modes for o in _modes_offered(state)} == {(0, 1), (0, 2), (1, 2)}
    assert len(_modes_offered(state)) == 3


def test_700_2a_a_spell_without_enough_legal_modes_isnt_offered() -> None:
    """Test Command with neither an artifact nor an enchantment on the battlefield: only "draw a
    card" is legal, and two different modes must be chosen, so it can't be cast (700.2a, 601.2b)
    and priority doesn't offer it. Fiery Confluence, whose damage modes are always legal, is."""
    scenario = Scenario(2)
    command, confluence = scenario.hand(P0, ["Test Command", "Fiery Confluence"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    offered = {o.object for o in _offered(scenario.build())}
    assert command not in offered and confluence in offered


def test_700_2a_a_single_possible_choice_isnt_asked() -> None:
    """Test Command with an artifact but no enchantment: the only legal pair is "destroy target
    artifact" and "draw a card". Nothing is asked; the choice is still announced (ModesChosen,
    601.2b) and recorded."""
    scenario = Scenario(2)
    (command,) = scenario.hand(P0, ["Test Command"])
    (ring,) = scenario.battlefield(P1, ["Sol Ring"])
    scenario.mana(P0, U, U)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(command, P0))
    kinds = [r.kind for r in records(state, AnswerRecord)]
    assert DecisionKind.CHOOSE_MODES not in kinds
    (spell,) = state.stack
    record = state.objects[spell].spell
    assert record is not None and record.modes == (0, 2)
    (chosen,) = records(state, ModesChosen)
    assert (chosen.spell, chosen.modes) == (spell, (0, 2))
    assert record.targets == ((TargetObject(ring),),)


def test_700_2_an_answer_outside_the_choices_is_rejected() -> None:
    scenario, confluence, _ = _confluence("Sol Ring")
    state = scenario.build()
    run_script(state, cast(confluence, P0))
    with pytest.raises(InvalidAnswer):
        submit(state, answer(state, Pick(10)))
    assert request_of(state).kind is DecisionKind.CHOOSE_MODES


def test_601_2b_modes_are_chosen_before_targets() -> None:
    """The modes are announced (601.2b) before the targets are chosen (601.2c)."""
    scenario, confluence, (_, ring, signet) = _confluence("Sol Ring", "Selesnya Signet")
    state = scenario.build()
    run_script(state, cast(confluence, P0), choose_modes(0, 1, 2))
    assert target_options(state) == (ObjectOption(ring), ObjectOption(signet))
    run_script(state, choose_targets(ring))
    logged = [e.record for e in state.event_log]
    chosen = next(i for i, r in enumerate(logged) if isinstance(r, ModesChosen))
    became = next(i for i, r in enumerate(logged) if isinstance(r, BecameTargets))
    assert chosen < became


# --- Targets of the chosen modes (601.2c, 700.2c, 700.2d) --------------------------------------


def test_700_2c_only_the_chosen_modes_targets_are_chosen() -> None:
    """Test Command choosing "destroy target enchantment" and "draw a card": only the
    enchantment is a target (one instance), although an artifact is on the battlefield."""
    scenario = Scenario(2)
    (command,) = scenario.hand(P0, ["Test Command"])
    _, totem = scenario.battlefield(P1, ["Sol Ring", "Test Totem"])
    scenario.mana(P0, U, U)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(command, P0), choose_modes(1, 2))
    (spell,) = state.stack
    record = state.objects[spell].spell
    assert record is not None and record.targets == ((TargetObject(totem),),)


def test_700_2d_each_instance_may_target_the_same_artifact() -> None:
    """Fiery Confluence choosing "2 damage to each opponent" and "destroy target artifact" twice,
    both instances targeting Sol Ring (700.2d). As it resolves, Sol Ring is destroyed once; the
    second instance does nothing (its target is gone, 608.2b), and Selesnya Signet stays."""
    scenario, confluence, (_, ring, signet) = _confluence("Sol Ring", "Selesnya Signet")
    state = scenario.build()
    life = state.player(P1).life
    run_script(
        state,
        cast(confluence, P0),
        choose_modes(1, 2, 2),
        choose_targets(ring),
        choose_targets(ring),
    )
    (spell,) = state.stack
    record = state.objects[spell].spell
    assert record is not None
    assert record.targets == ((TargetObject(ring),), (TargetObject(ring),))
    run_script(state, pass_(P0), pass_(P1))
    assert [r.obj for r in records(state, PermanentDestroyed)] == [ring]
    assert signet in state.battlefield
    assert state.player(P1).life == life - 2
    assert len(records(state, SpellResolved)) == 1


def test_700_2d_each_instance_may_target_a_different_artifact() -> None:
    scenario, confluence, (_, ring, signet) = _confluence("Sol Ring", "Selesnya Signet")
    state = scenario.build()
    run_script(
        state,
        cast(confluence, P0),
        choose_modes(1, 2, 2),
        choose_targets(signet),
        choose_targets(ring),
        pass_(P0),
        pass_(P1),
    )
    assert [r.obj for r in records(state, PermanentDestroyed)] == [signet, ring]
    assert names(state, Zone.graveyard(P1)) == ["Selesnya Signet", "Sol Ring"]


# --- Modes are fixed (700.2f-g) and resolve in order (608.2c) ----------------------------------


def test_700_2_modes_cant_change_after_casting() -> None:
    """Fiery Confluence cast with "1 damage to each creature" three times while an artifact is on
    the battlefield. The modes are asked once, as it is cast, and recorded; they can't be chosen
    again (a second ModesChosen is refused), and the spell resolves with exactly those modes:
    three damage events of 1, nothing destroyed."""
    scenario, confluence, (bears, ring) = _confluence("Sol Ring")
    state = scenario.build()
    run_script(state, cast(confluence, P0), choose_modes(0, 0, 0))
    (spell,) = state.stack
    record = state.objects[spell].spell
    assert record is not None and record.modes == (0, 0, 0)
    with pytest.raises(EngineError, match="already has its modes"):
        ApplyEvents((ModesChosen(spell=spell, modes=(2, 2, 2), rules=("601.2b",)),)).run(state)
    run_script(state, pass_(P0), pass_(P1))
    assert sum(r.kind is DecisionKind.CHOOSE_MODES for r in records(state, AnswerRecord)) == 1
    damage = records(state, DamageDealt)
    assert [d.to_objects for d in damage] == [((bears, 1),)] * 3
    assert records(state, PermanentDestroyed)[0].obj == bears  # 704.5g, after the spell
    assert ring in state.battlefield


def test_608_2c_modes_follow_the_printed_order() -> None:
    """Modes (0, 1, 2): the damage to each creature, then the damage to each opponent, then the
    artifact is destroyed (608.2c)."""
    scenario, confluence, (bears, ring) = _confluence("Sol Ring")
    state = scenario.build()
    run_script(
        state,
        cast(confluence, P0),
        choose_modes(0, 1, 2),
        pass_(P0),
        pass_(P1),
    )
    logged = [
        e.record for e in state.event_log if isinstance(e.record, DamageDealt | PermanentDestroyed)
    ]
    assert isinstance(logged[0], DamageDealt) and logged[0].to_objects == ((bears, 1),)
    assert isinstance(logged[1], DamageDealt) and logged[1].to_players == ((P1, 2),)
    assert isinstance(logged[2], PermanentDestroyed) and logged[2].obj == ring


def test_733_1_a_modal_spell_that_cant_be_paid_is_reversed() -> None:
    """Fiery Confluence with modes chosen but only {R}{R} in the pool: the cast is reversed
    (733.1). The card is back in hand, nothing is recorded on a spell, and no SpellCast."""
    scenario = Scenario(2)
    (confluence,) = scenario.hand(P0, ["Fiery Confluence"])
    scenario.mana(P0, R, R)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(confluence, P0), choose_modes(0, 1, 1))
    assert state.stack == []
    assert confluence in state.player(P0).hand
    assert len(records(state, ActionReversed)) == 1 and not records(state, SpellCast)
