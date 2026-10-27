"""701.6 (counter), 113.6g (can't be countered) and 101.2 (the "can't" wins), with Cancel.

From the pinned CR:

- 701.6a: to counter a spell means to cancel it, removing it from the stack. It doesn't resolve
  and none of its effects occur. A countered spell is put into its owner's graveyard.
- 701.6b: its caster gets no refund of the costs paid.
- 113.6g: an object's ability that states it can't be countered functions on the stack.
- 101.2: when an effect directs something to happen and another says it can't, the "can't"
  wins: Cancel still targets the spell, and resolves, but doesn't counter it.
- 115.2: "target spell" targets a spell on the stack, not a permanent or a player; 115.5: a spell
  can't target itself.
- 608.2b: a spell whose only target has left the stack doesn't resolve.

Where a countered spell goes (approved by the user, 2026-10-27, docs/decisions.md): its owner's
graveyard, always, as an ordinary zone change through the event pipeline (a new object, 400.7),
so M6's replacement effects can change it. It is *not* ``resolved_spell_destination``, which
decides only where a spell goes as it resolves (608.2n: an Adventure is exiled, 715.3d; an Omen
shuffled, 720.3d; buyback returns it, 702.27a).
"""

from __future__ import annotations

import pytest

from resolve.decisions.spaces import CastSpellOption, ObjectOption, PlayerOption
from resolve.events.damage import DamageDealt
from resolve.events.spells import (
    PermanentSpellResolved,
    SpellCountered,
    SpellDidNotResolve,
    SpellResolved,
)
from resolve.rules import legality
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import ManaType
from resolve.state.spell import Alternative, AlternativeKind, TargetObject, TargetPlayer
from resolve.state.turn import Phase
from resolve.state.zones import EXILE, Zone
from tests.casting_support import cast, choose_targets, options, pass_, records, target_choices
from tests.scenario import Scenario, names, run_script
from tests.seams import patch_object

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)
U, R = ManaType.BLUE, ManaType.RED


def castable(state: GameState) -> list[ObjectId]:
    return [o.object for o in options(state) if isinstance(o, CastSpellOption)]


def countered_by_cancel(
    spell: str, *, players: int = 2, owner: PlayerId | None = None
) -> tuple[GameState, ObjectId, ObjectId]:
    """P0's ``spell`` (owned by ``owner``) on the stack, below P1's Cancel targeting it; both
    resolve. Returns the state, the spell and the Cancel."""
    scenario = Scenario(players)
    (target,) = scenario.stack(P0, [spell], owner=owner)
    (cancel,) = scenario.stack(P1, ["Cancel"])
    scenario.targets(cancel, [TargetObject(target)])
    if spell == "Test Shock":
        scenario.targets(target, [TargetPlayer(P1)])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    assert state.stack == [target, cancel]
    for _ in range(2):
        if state.stack:
            run_script(state, *(pass_(PlayerId(p)) for p in range(players)))
    return state, target, cancel


def test_701_6a_a_countered_spell_goes_to_its_owners_graveyard() -> None:
    """P0's Grizzly Bears (a permanent spell) countered by P1's Cancel: it leaves the stack for
    P0's graveyard as a new object (400.7) and never reaches the battlefield; Cancel resolves and
    goes to P1's graveyard (608.2n)."""
    state, bears, cancel = countered_by_cancel("Grizzly Bears")
    (countered,) = records(state, SpellCountered)
    assert countered.spell == bears and countered.moved is not None
    assert countered.moved != bears and bears not in state.objects
    assert state.player(P0).graveyard == [countered.moved]
    assert names(state, Zone.graveyard(P0)) == ["Grizzly Bears"]
    assert records(state, PermanentSpellResolved) == [] and state.battlefield == []
    (resolved,) = records(state, SpellResolved)
    assert resolved.spell == cancel
    assert names(state, Zone.graveyard(P1)) == ["Cancel"] and state.stack == []


def test_701_6a_a_countered_instant_goes_to_its_owners_graveyard() -> None:
    """P0's Test Shock countered: to P0's graveyard, as a new object, through the pipeline (its
    ``SpellCountered`` event is logged and visible to everyone)."""
    state, shock, _ = countered_by_cancel("Test Shock")
    (countered,) = records(state, SpellCountered)
    assert countered.spell == shock and state.player(P0).graveyard == [countered.moved]
    entry = next(e for e in state.event_log if isinstance(e.record, SpellCountered))
    assert entry.visible_to is None  # public: every player sees it


def test_701_6a_the_owners_graveyard_not_the_controllers() -> None:
    """In three players, P0 controls a Grizzly Bears spell P2 owns; countered, it goes to P2's
    graveyard (701.6a: its owner's)."""
    state, _, _ = countered_by_cancel("Grizzly Bears", players=3, owner=P2)
    assert names(state, Zone.graveyard(P2)) == ["Grizzly Bears"]
    assert state.player(P0).graveyard == []


def test_701_6a_a_countered_adventure_goes_to_the_graveyard_not_exile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0's Test Quest, cast as an Adventure (715.3), countered by P1's Cancel: it goes to P0's
    graveyard (701.6a), not to exile. Exile is where an Adventure goes only as it *resolves*
    (715.3d); ``resolved_spell_destination`` is replaced by exile here, as 715.3d will make it
    (M4), and countering doesn't consult it."""
    patch_object(monkeypatch, "resolved_spell_destination", lambda state, spell: EXILE)
    scenario = Scenario(2)
    adventure = Alternative(AlternativeKind.ADVENTURE)
    (quest,) = scenario.stack(P0, ["Test Adventurer // Test Quest"], variant=adventure)
    (cancel,) = scenario.stack(P1, ["Cancel"])
    scenario.targets(cancel, [TargetObject(quest)])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1))
    (countered,) = records(state, SpellCountered)
    assert countered.spell == quest
    assert names(state, Zone.graveyard(P0)) == ["Test Adventurer // Test Quest"]
    assert names(state, EXILE) == ["Cancel"]  # Cancel resolved: the patched destination


def test_115_2_cancel_targets_only_spells() -> None:
    """With permanents on both sides and P0's Grizzly Bears and Test Shock on the stack, P1's
    Cancel offers the two spells, top first, and no permanent or player (115.2). With nothing
    else on the stack it isn't offered at all (601.2c)."""
    scenario = Scenario(2)
    scenario.battlefield(P0, ["Savannah Lions", "Sol Ring"])
    scenario.battlefield(P1, ["Hill Giant"])
    bears, shock = scenario.stack(P0, ["Grizzly Bears", "Test Shock"])  # top first
    scenario.targets(shock, [TargetPlayer(P1)])
    (cancel,) = scenario.hand(P1, ["Cancel"])
    scenario.mana(P1, U, U, U)
    scenario.at(Phase.PRECOMBAT_MAIN, priority=P1, passed=[P0])
    state = scenario.build()
    run_script(state, cast(cancel, P1))
    assert target_choices(state) == (ObjectOption(bears), ObjectOption(shock))

    scenario = Scenario(2)
    scenario.battlefield(P0, ["Savannah Lions"])
    scenario.hand(P1, ["Cancel"])
    scenario.at(Phase.PRECOMBAT_MAIN, active=P1)
    state = scenario.build()
    assert castable(state) == []


def test_115_5_cancel_cant_target_itself() -> None:
    """As Cancel's targets are chosen it is already on the stack (601.2a), but it can't target
    itself (115.5): the only option is P0's Grizzly Bears."""
    scenario = Scenario(2)
    (bears,) = scenario.stack(P0, ["Grizzly Bears"])
    (cancel,) = scenario.hand(P1, ["Cancel"])
    scenario.mana(P1, U, U, U)
    scenario.at(Phase.PRECOMBAT_MAIN, priority=P1, passed=[P0])
    state = scenario.build()
    run_script(state, cast(cancel, P1))
    assert target_choices(state) == (ObjectOption(bears),)  # the one choice, so not asked
    assert len(state.stack) == 2


def test_608_2b_cancel_whose_target_resolved_doesnt_resolve() -> None:
    """P1's Cancel targets P0's Grizzly Bears, which is above it on the stack (a scenario state:
    the Bears resolves first). As Cancel then tries to resolve its only target has left the stack
    (a new object on the battlefield, 400.7), so Cancel doesn't resolve (608.2b): nothing is
    countered and the Bears stays."""
    scenario = Scenario(2)
    bears, cancel = scenario.stack(P0, ["Grizzly Bears", "Cancel"])  # the Bears on top
    scenario.targets(cancel, [TargetObject(bears)])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1), pass_(P0), pass_(P1))
    assert len(state.battlefield) == 1
    (failed,) = records(state, SpellDidNotResolve)
    assert failed.spell == cancel
    assert records(state, SpellCountered) == []


def test_701_6a_a_countered_spells_effects_dont_happen() -> None:
    """P0 casts Test Shock at P1 (paying {R} from the pool); P1 casts Cancel in response. Shock
    is countered: no damage is dealt, P1's life is unchanged, and P0's {R} isn't refunded
    (701.6b)."""
    scenario = Scenario(2)
    (shock,) = scenario.hand(P0, ["Test Shock"])
    (cancel,) = scenario.hand(P1, ["Cancel"])
    scenario.mana(P0, R)
    scenario.mana(P1, U, U, U)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    life = state.player(P1).life
    run_script(state, cast(shock, P0), choose_targets(PlayerOption(P1)), pass_(P0))
    (on_stack,) = state.stack
    run_script(state, cast(cancel, P1))  # its one legal target: Test Shock
    assert target_choices(state) == (ObjectOption(on_stack),)
    run_script(state, pass_(P1), pass_(P0))
    assert records(state, DamageDealt) == [] and state.player(P1).life == life
    assert names(state, Zone.graveyard(P0)) == ["Test Shock"]
    assert state.player(P0).mana_pool == []


def test_113_6g_a_spell_that_cant_be_countered_can_still_be_targeted_but_isnt_countered() -> None:
    """P0's Test Stubborn Spell ("This spell can't be countered.") targets P1. P1's Cancel may
    target it (113.6g makes it uncounterable, not untargetable); Cancel resolves (its target is
    legal) but doesn't counter it (101.2). Stubborn Spell then resolves and deals 1 damage."""
    scenario = Scenario(2)
    (stubborn,) = scenario.stack(P0, ["Test Stubborn Spell"])
    scenario.targets(stubborn, [TargetPlayer(P1)])
    (cancel,) = scenario.hand(P1, ["Cancel"])
    scenario.mana(P1, U, U, U)
    scenario.at(Phase.PRECOMBAT_MAIN, priority=P1, passed=[P0])
    state = scenario.build()
    life = state.player(P1).life
    run_script(state, cast(cancel, P1))
    assert target_choices(state) == (ObjectOption(stubborn),)
    run_script(state, pass_(P1), pass_(P0))
    assert records(state, SpellCountered) == []
    (resolved,) = records(state, SpellResolved)
    assert names(state, Zone.graveyard(P1)) == ["Cancel"] and resolved.destination is not None
    assert state.stack == [stubborn]
    run_script(state, pass_(P0), pass_(P1))
    assert state.player(P1).life == life - 1
    assert names(state, Zone.graveyard(P0)) == ["Test Stubborn Spell"]


def test_101_2_cant_be_countered_beats_counter() -> None:
    """``allowed(CounterAction)``: countering Test Shock is allowed (701.6a); countering Test
    Stubborn Spell isn't: its "can't" (113.6g) wins over the counter (101.2)."""
    scenario = Scenario(2)
    shock, stubborn = scenario.stack(P0, ["Test Shock", "Test Stubborn Spell"])
    state = scenario.build()
    allowed = legality.allowed(state, legality.CounterAction(P1, shock))
    assert allowed.allowed and allowed.rules == ("701.6a",)
    forbidden = legality.allowed(state, legality.CounterAction(P1, stubborn))
    assert not forbidden.allowed and forbidden.rules == ("101.2", "113.6g")
