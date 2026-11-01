"""702.111 menace (M3.4).

From the pinned CR:

- 702.111b: "A creature with menace can't be blocked except by two or more creatures."
- 702.111c: multiple instances are redundant.
- 509.1b: restrictions are checked on the whole declaration; one that disobeys a restriction is
  illegal. Menace concerns how many creatures block, not one blocker, so it is a constraint of
  the declaration's space (``NoneOrAtLeast``, design.md §17.18), not a prohibition of one block.
- 802.4b: each defending player's blocks are judged ignoring other players' attackers and
  blockers, so two players can't share the blocking of a creature attacking one of them (802.4a:
  they block only creatures attacking them anyway).
- 733.1: an illegal declaration is refused and nothing changes.

Deranged Whelp (menace, 2/1); Palace Guard (can block any number of creatures).
"""

from __future__ import annotations

import pytest

from resolve.agents.random_agent import RandomAgent
from resolve.cards.keywords import Menace
from resolve.cards.registry import CardDefinition
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import NoneOrAtLeast, ObjectOption
from resolve.engine.api import submit, view_for
from resolve.errors import InvalidAnswer
from resolve.events.combat import BlockersDeclared
from resolve.rules import defaults
from resolve.state.combat import CombatState
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.turn import Step
from tests import scryfall_fixtures as fx
from tests.casting_support import records
from tests.combat_support import block_answer, block_space, blockable, declare_blockers, may_block
from tests.game_fixtures import answer, request_of
from tests.scenario import Scenario, with_cards

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)


def combat_of(state: GameState) -> CombatState:
    assert state.turn is not None and state.turn.combat is not None
    return state.turn.combat


def test_702_111b_one_blocker_is_rejected_two_are_accepted() -> None:
    """Deranged Whelp attacks P1, who controls Grizzly Bears and Savannah Lions. The space says
    the Whelp is blocked by none or by at least two creatures; the Bears alone is refused and
    nothing changes (733.1); the Bears and the Lions together are accepted and both block it."""
    scenario = Scenario(2)
    (whelp,) = scenario.battlefield(P0, ["Deranged Whelp"])
    bears, lions = scenario.battlefield(P1, ["Grizzly Bears", "Savannah Lions"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, whelp)
    state = scenario.build()
    assert block_space(state).constraints == (NoneOrAtLeast(ObjectOption(whelp), 2),)
    request = request_of(state)
    with pytest.raises(InvalidAnswer):
        submit(state, answer(state, block_answer(state, {bears: (whelp,)})))
    assert request_of(state) == request
    assert combat_of(state).blockers == {}
    assert records(state, BlockersDeclared) == []
    declare_blockers(state, {bears: (whelp,), lions: (whelp,)})
    assert combat_of(state).blockers_of(whelp) == (bears, lions)
    assert combat_of(state).attackers[whelp].blocked is True


def test_702_111b_no_blockers_is_legal() -> None:
    """Menace forbids one blocker, not none: declaring no blockers is accepted and the Whelp is
    unblocked (509.1h)."""
    scenario = Scenario(2)
    (whelp,) = scenario.battlefield(P0, ["Deranged Whelp"])
    scenario.battlefield(P1, ["Grizzly Bears", "Savannah Lions"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, whelp)
    state = scenario.build()
    declare_blockers(state, {})
    assert combat_of(state).attackers[whelp].blocked is False


def test_702_111b_three_blockers_are_accepted() -> None:
    """ "Two or more": three blockers are accepted too."""
    scenario = Scenario(2)
    (whelp,) = scenario.battlefield(P0, ["Deranged Whelp"])
    blockers = scenario.battlefield(P1, ["Grizzly Bears", "Savannah Lions", "Hill Giant"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, whelp)
    state = scenario.build()
    declare_blockers(state, {b: (whelp,) for b in blockers})
    assert combat_of(state).blockers_of(whelp) == tuple(blockers)


def test_702_111b_palace_guard_alone_cant_block_it() -> None:
    """Palace Guard can block any number of creatures, but it is one creature: alone it can't
    block the Whelp (702.111b). P1, whose only creature it is, has no legal block of the Whelp,
    so the Whelp isn't offered to it; with Grizzly Bears also attacking, the Guard may block
    the Bears only. With Savannah Lions beside it, the Guard and the Lions may block the Whelp
    together, the Guard blocking the Bears as well."""
    scenario = Scenario(2)
    (whelp,) = scenario.battlefield(P0, ["Deranged Whelp"])
    scenario.battlefield(P1, ["Palace Guard"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, whelp)
    state = scenario.build()
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION
    assert combat_of(state).attackers[whelp].blocked is False

    scenario = Scenario(2)
    whelp, bears = scenario.battlefield(P0, ["Deranged Whelp", "Grizzly Bears"])
    (guard,) = scenario.battlefield(P1, ["Palace Guard"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, whelp, bears)
    state = scenario.build()
    assert blockable(state, guard) == (bears,)

    scenario = Scenario(2)
    whelp, bears = scenario.battlefield(P0, ["Deranged Whelp", "Grizzly Bears"])
    guard, lions = scenario.battlefield(P1, ["Palace Guard", "Savannah Lions"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, whelp, bears)
    state = scenario.build()
    assert blockable(state, guard) == (whelp, bears)
    with pytest.raises(InvalidAnswer):
        submit(state, answer(state, block_answer(state, {guard: (whelp, bears)})))
    declare_blockers(state, {guard: (whelp, bears), lions: (whelp,)})
    assert combat_of(state).blockers_of(whelp) == (guard, lions)
    assert combat_of(state).blockers_of(bears) == (guard,)


def test_702_111b_judged_per_defending_player() -> None:
    """Three players: P0's two Whelps attack P1 and P2. P1 controls two creatures and may block
    their Whelp with both; P2 controls one, which can't block P2's Whelp alone (and can't help
    block P1's: 802.4a), so P2 isn't asked."""
    scenario = Scenario(3)
    whelp_1, whelp_2 = scenario.battlefield(P0, ["Deranged Whelp", "Deranged Whelp"])
    bears, lions = scenario.battlefield(P1, ["Grizzly Bears", "Savannah Lions"])
    scenario.battlefield(P2, ["Hill Giant"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, whelp_1)
    scenario.attacking(P2, whelp_2)
    state = scenario.build()
    assert request_of(state).player == P1
    assert may_block(state) == (bears, lions)
    assert blockable(state, bears) == (whelp_1,)
    declare_blockers(state, {bears: (whelp_1,), lions: (whelp_1,)})
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION
    combat = combat_of(state)
    assert combat.attackers[whelp_1].blocked is True
    assert combat.attackers[whelp_2].blocked is False


def test_702_111b_each_menace_attacker_is_its_own_constraint() -> None:
    """Two Whelps attack P1, who controls Grizzly Bears and Savannah Lions (each may block one
    creature, 509.1a). The space has one constraint per Whelp. One blocker on each Whelp is
    refused; both on the same Whelp is accepted, the other Whelp unblocked."""
    scenario = Scenario(2)
    whelp_1, whelp_2 = scenario.battlefield(P0, ["Deranged Whelp", "Deranged Whelp"])
    bears, lions = scenario.battlefield(P1, ["Grizzly Bears", "Savannah Lions"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, whelp_1, whelp_2)
    state = scenario.build()
    assert block_space(state).constraints == (
        NoneOrAtLeast(ObjectOption(whelp_1), 2),
        NoneOrAtLeast(ObjectOption(whelp_2), 2),
    )
    with pytest.raises(InvalidAnswer):
        submit(state, answer(state, block_answer(state, {bears: (whelp_1,), lions: (whelp_2,)})))
    declare_blockers(state, {bears: (whelp_2,), lions: (whelp_2,)})
    combat = combat_of(state)
    assert combat.attackers[whelp_1].blocked is False
    assert combat.blockers_of(whelp_2) == (bears, lions)


TWICE_MENACING = fx.keyword_creature(
    "Test Twice Menacing", "{1}{R}", 2.0, "Wolf", ("2", "1"), "R", "Menace\nMenace"
)


def test_702_111c_two_instances_of_menace_still_need_two_blockers() -> None:
    """Multiple instances are redundant (702.111c): a creature with menace twice has one
    constraint of minimum 2 (not 4, and not two constraints); one blocker is refused, two are
    accepted."""
    definition = CardDefinition("Test Twice Menacing", abilities=(Menace(), Menace()))
    scenario = with_cards(2, [TWICE_MENACING], [definition])
    (wolf,) = scenario.battlefield(P0, ["Test Twice Menacing"])
    bears, lions = scenario.battlefield(P1, ["Grizzly Bears", "Savannah Lions"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, wolf)
    state = scenario.build()
    assert block_space(state).constraints == (NoneOrAtLeast(ObjectOption(wolf), 2),)
    with pytest.raises(InvalidAnswer):
        submit(state, answer(state, block_answer(state, {lions: (wolf,)})))
    declare_blockers(state, {bears: (wolf,), lions: (wolf,)})
    assert combat_of(state).blockers_of(wolf) == (bears, lions)


def test_702_111b_a_creature_that_may_block_nothing_doesnt_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Seam of ``defaults.blocks_allowed``: with Grizzly Bears allowed to block no creature (0),
    P1's Bears and Savannah Lions are one possible blocker of the Whelp, which can't be blocked
    by one (702.111b): no legal declaration blocks anything, so P1 isn't asked (design.md §6)."""
    scenario = Scenario(2)
    (whelp,) = scenario.battlefield(P0, ["Deranged Whelp"])
    bears, _lions = scenario.battlefield(P1, ["Grizzly Bears", "Savannah Lions"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, whelp)
    original = defaults.blocks_allowed

    def blocks_allowed(state: GameState, obj: ObjectId) -> int | None:
        return 0 if obj == bears else original(state, obj)

    monkeypatch.setattr(defaults, "blocks_allowed", blocks_allowed)
    state = scenario.build()
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION
    assert combat_of(state).attackers[whelp].blocked is False


def test_702_111b_the_random_agent_declares_only_legal_blocks() -> None:
    """Deranged Whelp and Grizzly Bears attack P1, who controls three creatures: over 60 seeds,
    every declaration ``RandomAgent`` makes is accepted by the engine (``submit``), never one
    blocker on the Whelp, and some block the Whelp with two or more."""
    blocked = 0
    for seed in range(60):
        scenario = Scenario(2)
        whelp, bears = scenario.battlefield(P0, ["Deranged Whelp", "Grizzly Bears"])
        scenario.battlefield(P1, ["Grizzly Bears", "Savannah Lions", "Hill Giant"])
        scenario.at(Step.DECLARE_BLOCKERS, begin=True)
        scenario.attacking(P1, whelp, bears)
        state = scenario.build()
        request = request_of(state)
        submit(state, RandomAgent(seed).decide(view_for(state, request.player), request))
        on_whelp = combat_of(state).blockers_of(whelp)
        assert len(on_whelp) != 1
        blocked += len(on_whelp) >= 2
    assert blocked > 0
