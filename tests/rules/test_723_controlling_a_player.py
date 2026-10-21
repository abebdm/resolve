"""723: controlling another player, through ``deciding_player`` and ``knows_identity``.

No effect gives control of a player until Mindslaver and Word of Command (M9). These tests
replace ``deciding_player`` (design.md §17.1) with ``monkeypatch`` to check the engine obeys it
everywhere; M9 replaces them with real effects.

From the pinned CR:

- 723.5: the controller makes all choices and decisions the controlled player is allowed to
  make, including what to play. The decision is still the controlled player's: it is their
  priority, their land play, their discard.
- 723.4: information visible to the controlled player is visible to both that player and the
  controller; the controller can see that player's hand.
- 723.6: the controller can't make that player concede; a player may concede at any time, even
  if controlled (104.3a).
"""

from __future__ import annotations

import pytest

from resolve.decisions.kinds import DecisionKind
from resolve.decisions.request import DecisionAnswer
from resolve.decisions.spaces import ChooseOne, PassOption, Pick, PickMany
from resolve.engine import concede
from resolve.engine.api import submit, view_for
from resolve.errors import InvalidAnswer
from resolve.events.cards import CardDrawn
from resolve.events.turn import PriorityPassed
from resolve.rules import defaults
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.invariants import invariant_violations
from resolve.state.turn import Phase, Step
from tests.game_fixtures import request_of
from tests.scenario import Scenario

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)


def p1_controls_p0(monkeypatch: pytest.MonkeyPatch) -> None:
    def deciding(state: object, player: PlayerId) -> PlayerId:
        return P1 if player == P0 else player

    monkeypatch.setattr(defaults, "deciding_player", deciding)


def pass_index(request_space: ChooseOne) -> Pick:
    return Pick(request_space.options.index(PassOption()))


def test_723_5_the_deciding_player_receives_the_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """Player 0 would have priority; player 1 controls them, so player 1 is asked. The request
    is still for player 0 (it's their priority); an answer from player 0 is rejected."""
    p1_controls_p0(monkeypatch)
    scenario = Scenario(2)
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    request = request_of(state)
    assert (request.player, request.for_player) == (P1, P0)
    assert request.kind is DecisionKind.PRIORITY_ACTION
    assert isinstance(request.space, ChooseOne)
    with pytest.raises(InvalidAnswer, match="answered"):
        submit(state, DecisionAnswer(request.id, P0, pass_index(request.space)))
    assert state.pending is request  # nothing changed
    assert state.turn is not None and state.turn.priority == P0
    assert invariant_violations(state) == []


def test_723_5_the_controllers_answer_is_the_controlled_players_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Player 1 passes for player 0: the pass is player 0's (117.3d), then player 1 receives
    priority and decides for themselves."""
    p1_controls_p0(monkeypatch)
    scenario = Scenario(2)
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    request = request_of(state)
    assert isinstance(request.space, ChooseOne)
    submit(state, DecisionAnswer(request.id, P1, pass_index(request.space)))
    passes = [e.record for e in state.event_log if isinstance(e.record, PriorityPassed)]
    assert [p.player for p in passes] == [P0]
    assert state.turn is not None and state.turn.passed == [P0]
    follow_up = request_of(state)
    assert (follow_up.player, follow_up.for_player) == (P1, P1)


def test_723_5_the_views_say_who_decides_and_for_whom(monkeypatch: pytest.MonkeyPatch) -> None:
    p1_controls_p0(monkeypatch)
    scenario = Scenario(3)
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    request = request_of(state)
    assert view_for(state, P1).request == request
    assert view_for(state, P0).request is None  # the controlled player isn't asked
    assert view_for(state, P2).request is None
    for viewer in (P0, P1, P2):
        waiting = view_for(state, viewer).waiting_for
        assert waiting is not None
        assert (waiting.player, waiting.for_player) == (P1, P0)


def test_723_5_a_decision_the_controlled_player_asks_the_controller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cleanup discard (514.1) is player 0's decision; the controller makes it."""
    p1_controls_p0(monkeypatch)
    scenario = Scenario(2)
    scenario.hand(P0, ["Forest"] * 9)
    for player in scenario.players:
        scenario.library(player, ["Forest"] * 2)
    scenario.at(Step.CLEANUP)
    state = scenario.build()
    request = request_of(state)
    assert request.kind is DecisionKind.DISCARD
    assert (request.player, request.for_player) == (P1, P0)
    submit(state, DecisionAnswer(request.id, P1, PickMany((0, 1))))
    assert len(state.player(P0).hand) == 7


def test_723_4_the_controller_sees_what_the_controlled_player_sees(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Player 0's hand is visible to player 0 (402.3) and, while player 1 controls them, to
    player 1; player 2 and the controlled player's library stay hidden. Player 1's hand is not
    shown to player 0: control gives the controller the controlled player's information, not the
    other way round."""
    p1_controls_p0(monkeypatch)
    scenario = Scenario(3)
    (shock,) = scenario.hand(P0, ["Test Shock"])
    (forest,) = scenario.hand(P1, ["Forest"])
    (top,) = scenario.library(P0, ["Forest"])
    scenario.at(Step.UPKEEP)
    state = scenario.build()

    def names_in_hand(viewer: PlayerId, owner: PlayerId) -> list[str | None]:
        return [o.name for o in view_for(state, viewer).players[owner].hand]

    assert names_in_hand(P0, P0) == ["Test Shock"]
    assert names_in_hand(P1, P0) == ["Test Shock"]
    assert names_in_hand(P2, P0) == [None]
    assert names_in_hand(P0, P1) == [None]
    assert names_in_hand(P1, P1) == ["Forest"]
    assert view_for(state, P1).players[P0].library_size == 1  # a count only (401.3)
    assert shock in state.objects and forest in state.objects and top in state.objects


def test_723_4_without_control_the_hand_stays_private() -> None:
    scenario = Scenario(2)
    scenario.hand(P0, ["Test Shock"])
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    assert [o.name for o in view_for(state, P1).players[P0].hand] == [None]


def test_723_4_the_controller_sees_the_controlled_players_private_log_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Drawing a card shows the drawn card to its player only (400.2); the controller sees it
    too (723.4), another opponent doesn't."""
    p1_controls_p0(monkeypatch)
    scenario = Scenario(3)
    top, _ = scenario.library(P0, ["Test Shock", "Forest"])
    scenario.at(Step.DRAW, begin=True)
    state = scenario.build()

    def drawn_from(viewer: PlayerId) -> list[ObjectId | None]:
        return [
            entry.record.drawn_from
            for entry in view_for(state, viewer).log
            if isinstance(entry.record, CardDrawn) and entry.record.player == P0
        ]

    assert drawn_from(P0) == drawn_from(P1) == [top]  # the library object is known to both
    assert drawn_from(P2) == [None]  # redacted: they only see the new hand object


def test_723_6_the_controller_cant_concede_for_the_controlled_player(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p1_controls_p0(monkeypatch)
    scenario = Scenario(3)
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    with pytest.raises(InvalidAnswer, match="723.6"):
        concede(state, P0, by=P1)
    assert not state.player(P0).left_game and state.pending is not None
    assert invariant_violations(state) == []


def test_723_6_a_controlled_player_may_concede_at_any_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """104.3a: player 0 concedes while player 1 controls them. They lose and leave; the request
    meant for player 0 is withdrawn, and the game goes on with whoever the rules ask now."""
    p1_controls_p0(monkeypatch)
    scenario = Scenario(3)
    scenario.at(Phase.PRECOMBAT_MAIN, active=P0, priority=P0)
    state = scenario.build()
    first = request_of(state)
    assert (first.player, first.for_player) == (P1, P0)
    concede(state, P0, by=P0)
    assert state.player(P0).left_game and state.player(P0).lost
    assert not state.player(P1).left_game and not state.player(P2).left_game
    follow_up = request_of(state)
    assert follow_up.id != first.id and follow_up.for_player != P0
    assert invariant_violations(state) == []
