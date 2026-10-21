"""733: handling illegal actions, by reversing them (design.md §17.4).

From the pinned CR:

- 733.1: if a player starts to take an action but can't legally complete it, the entire action is
  reversed and any payments already made are canceled; no abilities trigger and no effects apply
  as a result. A spell returns to the zone it came from. The player may also reverse any legal
  mana abilities they activated while making the illegal play (unless their mana was spent on a
  mana ability that wasn't reversed). Actions that moved cards to or from a library, shuffled a
  library or revealed cards from one can't be reversed.
- 733.2: the player who had priority retains it. Nothing in 117.4 makes the reversed action an
  action taken "in between passing", so the passes before it still count (design.md §17.4).
- 601.2h, 118.3: a cost that can't be paid fully can't be paid, so such a cast is illegal.
- 400.2: every player saw the card on the stack, so they know it once it is back in the hand.
- What a reversal doesn't rewind (design.md §17.4): object IDs, request IDs and the RNG, so no
  ID is reused and randomness can't be peeked at.
"""

from __future__ import annotations

import pytest

from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import ChooseSubset, ManaActivationOption
from resolve.engine.concede import concede
from resolve.errors import EngineError
from resolve.events.spells import ActionReversed, SpellCast
from resolve.state.checkpoint import (
    NOT_RESTORED,
    restorable_fields,
    restore_checkpoint,
    take_checkpoint,
)
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import Mana, ManaType
from resolve.state.turn import Phase, Step
from resolve.state.zones import Zone
from tests.casting_support import activate, answered, cast, pass_, records, reverse
from tests.engine_support import ReversesAfterDrawing
from tests.game_fixtures import request_of
from tests.scenario import Scenario, run_script

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)
G = ManaType.GREEN


def one_forest_and_bears() -> tuple[GameState, ObjectId, ObjectId]:
    """P0's main phase: Grizzly Bears ({1}{G}) in hand and one Forest, which can't pay it."""
    scenario = Scenario(2)
    (bears,) = scenario.hand(P0, ["Grizzly Bears"])
    (forest,) = scenario.battlefield(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    return scenario.build(), bears, forest


def test_733_1_an_unpayable_cast_is_reversed() -> None:
    """Tap the Forest, then "pay" is the only option left (not asked): {G} can't pay {1}{G}. The
    player reverses the Forest's ability: the game is as before the cast."""
    state, bears, forest = one_forest_and_bears()
    run_script(state, cast(bears, P0), activate(forest))
    request = request_of(state)
    assert request.kind is DecisionKind.REVERSE_MANA_ABILITIES and request.player == P0
    assert "733.1" in request.rules
    assert request.space == ChooseSubset((ManaActivationOption(0, forest, 0),), 0, 1)
    run_script(state, reverse(ManaActivationOption(0, forest, 0)))
    assert not state.objects[forest].tapped
    assert state.player(P0).mana_pool == []
    assert state.player(P0).hand == [bears]  # its old ID
    assert state.objects[bears].known_to == (P1,)  # 400.2: P1 saw it on the stack
    assert state.stack == []
    (reversed_,) = records(state, ActionReversed)
    assert reversed_.player == P0 and reversed_.card == bears and "733.1" in reversed_.rules
    assert records(state, SpellCast) == []
    request = request_of(state)
    assert request.kind is DecisionKind.PRIORITY_ACTION and request.player == P0  # 733.2


def test_733_1_a_player_may_keep_a_mana_ability_unreversed() -> None:
    state, bears, forest = one_forest_and_bears()
    run_script(state, cast(bears, P0), activate(forest), reverse())
    assert state.objects[forest].tapped
    assert state.player(P0).mana_pool == [Mana(G, forest)]
    assert state.player(P0).hand == [bears] and state.stack == []
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION


def test_733_1_nothing_activated_asks_nothing() -> None:
    """No mana and no mana ability: nothing can pay, and nothing was activated to reverse."""
    scenario = Scenario(2)
    (bears,) = scenario.hand(P0, ["Grizzly Bears"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(bears, P0))
    assert answered(state, DecisionKind.REVERSE_MANA_ABILITIES) == 0
    assert answered(state, DecisionKind.ACTIVATE_MANA_ABILITIES) == 0
    assert state.player(P0).hand == [bears] and len(records(state, ActionReversed)) == 1
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION


def test_733_1_reversal_doesnt_rewind_counters_or_randomness() -> None:
    state, bears, forest = one_forest_and_bears()
    objects_before, requests_before = state.next_object_id, state.next_request_id
    timestamps_before = state.next_timestamp
    run_script(state, cast(bears, P0), activate(forest))
    advanced = (state.next_object_id, state.next_timestamp)
    run_script(state, reverse(ManaActivationOption(0, forest, 0)))
    assert state.next_object_id >= advanced[0] > objects_before  # the stack object's ID is used
    assert state.next_timestamp >= advanced[1] > timestamps_before
    assert request_of(state).id > requests_before
    assert state.objects[bears].id == bears


def test_733_1_a_checkpoint_leaves_out_the_log_counters_and_rng() -> None:
    """Restoring doesn't rewind the RNG: numbers drawn since the checkpoint stay drawn."""
    state = Scenario(2).build()
    assert set(NOT_RESTORED) == {
        "event_log",
        "tasks",
        "pending",
        "next_object_id",
        "next_timestamp",
        "next_request_id",
        "rng",
    }
    assert "objects" in restorable_fields() and "players" in restorable_fields()
    checkpoint = take_checkpoint(state)
    state.rng.randbelow(1000)
    drawn = state.rng.state
    state.player(P0).life = 3
    restore_checkpoint(state, checkpoint)
    assert state.rng.state == drawn
    assert state.player(P0).life == 20


def test_733_1_reversal_after_a_library_action_is_an_engine_error() -> None:
    scenario = Scenario(2)
    scenario.library(P0, ["Forest"])
    with pytest.raises(EngineError, match=r"733\.1"):
        scenario.build(ReversesAfterDrawing(P0))


def test_733_2_passes_before_a_reversed_cast_still_count() -> None:
    """P0 passes in their upkeep; P1 tries to cast Test Shock with no mana, and it's reversed;
    P1 still has priority, and when they pass the upkeep ends (117.4: P0's pass counts)."""
    scenario = Scenario(2)
    scenario.library(P0, ["Forest"])
    (shock,) = scenario.hand(P1, ["Test Shock"])
    scenario.at(Step.UPKEEP, number=3)
    state = scenario.build()
    run_script(state, pass_(P0), cast(shock, P1))
    request = request_of(state)
    assert request.player == P1 and request.kind is DecisionKind.PRIORITY_ACTION
    turn = state.turn
    assert turn is not None and turn.passed == [P0]
    run_script(state, pass_(P1))
    turn = state.turn
    assert turn is not None and turn.step is Step.DRAW


def test_733_1_a_player_who_concedes_during_a_reversed_cast_stays_gone() -> None:
    """104.3a, 800.4a: P2 concedes while P0 decides how to pay; P0's cast is then reversed. The
    reversal restores the game as before the cast, but P2's leaving isn't part of the action."""
    scenario = Scenario(3)
    (bears,) = scenario.hand(P0, ["Grizzly Bears"])
    (forest,) = scenario.battlefield(P0, ["Forest"])
    (theirs,) = scenario.battlefield(P2, ["Forest"])
    (in_hand,) = scenario.hand(P2, ["Forest"])
    (in_library,) = scenario.library(P2, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(bears, P0), activate(forest))
    concede(state, P2)
    assert request_of(state).kind is DecisionKind.REVERSE_MANA_ABILITIES
    run_script(state, reverse(ManaActivationOption(0, forest, 0)))
    assert state.player(P2).left_game
    assert all(obj not in state.objects for obj in (theirs, in_hand, in_library))
    assert state.player(P2).hand == [] and state.player(P2).library == []
    assert state.player(P0).hand == [bears]
    assert state.objects[bears].zone == Zone.hand(P0)
