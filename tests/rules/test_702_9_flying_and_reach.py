"""702.9 flying and 702.17 reach (M3.4).

From the pinned CR:

- 702.9b: "A creature with flying can't be blocked except by creatures with flying and/or reach.
  A creature with flying can block a creature with or without flying."
- 702.17b: the same sentence: reach lets a creature block a creature with flying.
- 702.9c, 702.17c: multiple instances are redundant.
- 509.1b: evasion abilities are restrictions; a declaration that disobeys one is illegal.

Giant Spider's ruling (2008-04-01): it blocks flyers with reach, "because a creature with flying
can only be blocked by creatures with flying or reach".

Wind Drake (flying), Giant Spider (reach), Grizzly Bears and Hill Giant (vanilla).
"""

from __future__ import annotations

from resolve.decisions.kinds import DecisionKind
from resolve.rules import legality
from resolve.state.combat import CombatState
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.turn import Step
from tests.combat_support import blockable, declare_blockers, may_block
from tests.game_fixtures import request_of
from tests.scenario import Scenario

P0, P1 = PlayerId(0), PlayerId(1)


def combat_of(state: GameState) -> CombatState:
    assert state.turn is not None and state.turn.combat is not None
    return state.turn.combat


def verdict(state: GameState, blocker: ObjectId, attacker: ObjectId) -> legality.Verdict:
    return legality.allowed(state, legality.BlockAction(P1, blocker, attacker))


def test_702_9b_a_flyer_cant_be_blocked_by_a_creature_without_flying_or_reach() -> None:
    """Wind Drake attacks P1, whose only creature is Grizzly Bears: the Bears can't block it
    (702.9b; the verdict cites the rule), so P1 has nothing to declare and isn't asked, and the
    Drake is unblocked (509.1h)."""
    scenario = Scenario(2)
    (drake,) = scenario.battlefield(P0, ["Wind Drake"])
    (bears,) = scenario.battlefield(P1, ["Grizzly Bears"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, drake)
    state = scenario.build()
    refused = verdict(state, bears, drake)
    assert not refused.allowed
    assert "702.9b" in refused.rules
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION
    assert combat_of(state).attackers[drake].blocked is False


def test_702_9b_a_flyer_can_be_blocked_by_giant_spider_and_by_another_flyer() -> None:
    """Wind Drake attacks P1, who controls Giant Spider (reach), a Wind Drake of their own
    (flying) and Grizzly Bears: the Spider and the Drake may block it (702.9b, 702.17b; Giant
    Spider's ruling), the Bears may not. The Spider's block is declared and stands."""
    scenario = Scenario(2)
    (drake,) = scenario.battlefield(P0, ["Wind Drake"])
    spider, own_drake, bears = scenario.battlefield(
        P1, ["Giant Spider", "Wind Drake", "Grizzly Bears"]
    )
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, drake)
    state = scenario.build()
    assert may_block(state) == (spider, own_drake)
    assert verdict(state, spider, drake).allowed
    assert verdict(state, own_drake, drake).allowed
    assert not verdict(state, bears, drake).allowed
    declare_blockers(state, {spider: (drake,)})
    assert combat_of(state).blockers_of(drake) == (spider,)
    assert combat_of(state).attackers[drake].blocked is True


def test_702_9b_a_flyer_can_block_a_ground_creature() -> None:
    """P1's Wind Drake may block Grizzly Bears, which has no flying (702.9b, second sentence),
    and Giant Spider attacking is blocked like any creature: reach is no evasion (702.17b)."""
    scenario = Scenario(2)
    bears, spider = scenario.battlefield(P0, ["Grizzly Bears", "Giant Spider"])
    drake, giant = scenario.battlefield(P1, ["Wind Drake", "Hill Giant"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, bears, spider)
    state = scenario.build()
    assert blockable(state, drake) == (bears, spider)
    assert blockable(state, giant) == (bears, spider)
    declare_blockers(state, {drake: (bears,), giant: (spider,)})
    assert combat_of(state).blockers_of(bears) == (drake,)
    assert combat_of(state).blockers_of(spider) == (giant,)


def test_702_9b_flying_and_reach_on_the_blocker_dont_stop_flying_attackers_choosing() -> None:
    """With two flyers and a ground creature attacking, P1's Giant Spider may block any of them
    and P1's Grizzly Bears only the ground creature (702.9b is judged per attacker)."""
    scenario = Scenario(2)
    drake, other, giant = scenario.battlefield(P0, ["Wind Drake", "Wind Drake", "Hill Giant"])
    spider, bears = scenario.battlefield(P1, ["Giant Spider", "Grizzly Bears"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, drake, other, giant)
    state = scenario.build()
    assert blockable(state, spider) == (drake, other, giant)
    assert blockable(state, bears) == (giant,)
