"""The retired evergreen evasion abilities: 702.13 intimidate, 702.14 landwalk, 702.36 fear
(M3.4).

From the pinned CR:

- 702.13b: "A creature with intimidate can't be blocked except by artifact creatures and/or
  creatures that share a color with it."
- 702.36b: "A creature with fear can't be blocked except by artifact creatures and/or black
  creatures."
- 702.14c: "A creature with landwalk can't be blocked as long as the defending player controls at
  least one land with the specified land type". 702.14d: landwalk abilities don't "cancel" one
  another (the defending player's own landwalk creature still can't block it).
- 802.2a: in a multiplayer game, "the defending player" of an attacking creature is the player
  it attacks ("Whether the creature with mountainwalk can be blocked depends only on whether
  Carissa controls a Mountain").
- 509.1b: these are restrictions on the declaration; each is checked as blockers are declared.

Highborn Ghoul (intimidate, black), Severed Legion (fear, black), Bog Raiders (swampwalk, black);
Darksteel Myr (a colorless artifact creature), Test Spawn (black), Grizzly Bears (green),
Raging Goblin (red).
"""

from __future__ import annotations

from resolve.decisions.kinds import DecisionKind
from resolve.rules import legality
from resolve.state.combat import CombatState
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.turn import Step
from tests.combat_support import blockable, may_block
from tests.game_fixtures import request_of
from tests.scenario import Scenario

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)


def combat_of(state: GameState) -> CombatState:
    assert state.turn is not None and state.turn.combat is not None
    return state.turn.combat


def verdict(
    state: GameState, blocker: ObjectId, attacker: ObjectId, player: PlayerId = P1
) -> legality.Verdict:
    return legality.allowed(state, legality.BlockAction(player, blocker, attacker))


def _against(attacker: str, blockers: list[str]) -> tuple[GameState, ObjectId, list[ObjectId]]:
    scenario = Scenario(2)
    (creature,) = scenario.battlefield(P0, [attacker])
    ids = scenario.battlefield(P1, blockers)
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, creature)
    return scenario.build(), creature, ids


def test_702_13b_intimidate() -> None:
    """Darksteel Myr (an artifact creature) and Test Spawn (black, sharing Highborn Ghoul's
    color) may block Highborn Ghoul; Grizzly Bears (green, not an artifact) can't, and the
    refusal cites 702.13b."""
    state, ghoul, (myr, spawn, bears) = _against(
        "Highborn Ghoul", ["Darksteel Myr", "Test Spawn", "Grizzly Bears"]
    )
    assert may_block(state) == (myr, spawn)
    refused = verdict(state, bears, ghoul)
    assert not refused.allowed and "702.13b" in refused.rules


def test_702_13b_intimidate_doesnt_restrict_a_creature_without_it() -> None:
    """Intimidate is the attacker's: Highborn Ghoul blocking isn't restricted, and a Grizzly
    Bears attacking is blocked by the Ghoul and by Test Spawn alike."""
    state, bears, (ghoul, spawn) = _against("Grizzly Bears", ["Highborn Ghoul", "Test Spawn"])
    assert may_block(state) == (ghoul, spawn)
    assert blockable(state, ghoul) == (bears,)


def test_702_36b_fear() -> None:
    """Darksteel Myr (artifact) and Test Spawn (black) may block Severed Legion; Grizzly Bears
    (green) and Raging Goblin (red) can't, and the refusal cites 702.36b."""
    state, legion, (myr, spawn, bears, goblin) = _against(
        "Severed Legion", ["Darksteel Myr", "Test Spawn", "Grizzly Bears", "Raging Goblin"]
    )
    assert may_block(state) == (myr, spawn)
    for blocker in (bears, goblin):
        refused = verdict(state, blocker, legion)
        assert not refused.allowed and "702.36b" in refused.rules


def test_702_14c_swampwalk_unblockable_while_the_defending_player_controls_a_swamp() -> None:
    """P1 controls a Swamp and Grizzly Bears: Bog Raiders can't be blocked (702.14c), so P1 isn't
    asked and the Raiders are unblocked. A Bog Raiders of P1's own can't block it either: landwalk
    doesn't cancel (702.14d)."""
    scenario = Scenario(2)
    (raiders,) = scenario.battlefield(P0, ["Bog Raiders"])
    bears, own_raiders, _swamp = scenario.battlefield(P1, ["Grizzly Bears", "Bog Raiders", "Swamp"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, raiders)
    state = scenario.build()
    for blocker in (bears, own_raiders):
        refused = verdict(state, blocker, raiders)
        assert not refused.allowed and "702.14c" in refused.rules
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION
    assert combat_of(state).attackers[raiders].blocked is False


def test_702_14c_swampwalk_is_blockable_otherwise() -> None:
    """P1 controls no Swamp (a Forest only), P0 controls one: Grizzly Bears may block Bog Raiders,
    since only the defending player's lands count (702.14c)."""
    scenario = Scenario(2)
    raiders, _swamp = scenario.battlefield(P0, ["Bog Raiders", "Swamp"])
    bears, _forest = scenario.battlefield(P1, ["Grizzly Bears", "Forest"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, raiders)
    state = scenario.build()
    assert blockable(state, bears) == (raiders,)


def test_702_14c_judged_per_defending_player_in_multiplayer() -> None:
    """Three players: one Bog Raiders attacks P1, who controls a Swamp, the other attacks P2, who
    doesn't (802.2a: each attacker's defending player is the player it attacks). P1's Bears can't
    block theirs; P2's Bears may block theirs."""
    scenario = Scenario(3)
    raiders_1, raiders_2 = scenario.battlefield(P0, ["Bog Raiders", "Bog Raiders"])
    bears_1, _swamp = scenario.battlefield(P1, ["Grizzly Bears", "Swamp"])
    (bears_2,) = scenario.battlefield(P2, ["Grizzly Bears"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, raiders_1)
    scenario.attacking(P2, raiders_2)
    state = scenario.build()
    assert not verdict(state, bears_1, raiders_1).allowed
    request = request_of(state)
    assert (request.kind, request.player) == (DecisionKind.DECLARE_BLOCKERS, P2)
    assert may_block(state) == (bears_2,)
    assert blockable(state, bears_2) == (raiders_2,)
