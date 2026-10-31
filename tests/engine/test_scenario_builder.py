"""The scenario builder, ``tests/scenario.py`` (design.md §14)."""

from __future__ import annotations

import copy
import pickle

import pytest

from resolve.agents.scripted import ScriptError, Step, choose
from resolve.cards.registry import CardRegistry
from resolve.data.cards import UnknownCardError
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import Number, PlayerOption
from resolve.engine.api import pending_decision, view_for
from resolve.engine.start import StartGame
from resolve.errors import DeckError, EngineError, InvalidAnswer, NotImplementedRule
from resolve.state.combat import AttackPlayer, AttackRecord, BlockRecord
from resolve.state.config import GameConfig
from resolve.state.game import turn_order
from resolve.state.ids import PlayerId
from resolve.state.invariants import invariant_violations, state_impurities
from resolve.state.turn import Phase
from resolve.state.turn import Step as TurnStep
from resolve.state.zones import BATTLEFIELD, COMMAND, EXILE, STACK, Zone
from tests.engine_support import AskTwice, EndGame, markers
from tests.scenario import Scenario, ScenarioError, names, run_script

P0, P1, P2, P3 = (PlayerId(p) for p in range(4))


def test_an_empty_scenario_has_players_at_starting_life_and_nothing_else() -> None:
    """103.4: each player begins at the starting life total; 40 in Commander (103.4c)."""
    state = Scenario(3).build()
    assert [player.life for player in state.players] == [20, 20, 20]
    assert state.objects == {} and state.cards == {}
    assert state.starting_player == P0
    assert state.tasks == [] and state.pending is None and state.result is None
    commander = Scenario(4, config=GameConfig.commander_game()).build()
    assert [player.life for player in commander.players] == [40] * 4


def test_the_number_of_players_is_the_number_of_seats() -> None:
    """100.1: a game needs two or more players; nothing assumes two."""
    assert Scenario(6).players == tuple(PlayerId(p) for p in range(6))
    with pytest.raises(DeckError, match="at least two players"):
        Scenario(1)


def test_life_totals_can_be_set_to_any_integer() -> None:
    """119: zero and negative life are states a game can be in (704.5a then applies)."""
    scenario = Scenario(3)
    scenario.life(P0, 0).life(P1, -5).life(P2, 123)
    state = scenario.build()
    assert [player.life for player in state.players] == [0, -5, 123]


def test_starting_player_sets_turn_order() -> None:
    """103.1: turn order starts with the starting player and proceeds clockwise."""
    state = Scenario(4, starting_player=2).build()
    assert turn_order(state) == (P2, P3, P0, P1)
    unstarted = Scenario(2, starting_player=None).build()
    assert unstarted.starting_player is None
    with pytest.raises(EngineError, match="no player 4"):
        Scenario(4, starting_player=4)


def test_library_cards_are_listed_top_first() -> None:
    """401.2: the library is a pile; the last element of a pile list is its top."""
    scenario = Scenario(2)
    top, bottom = scenario.library(P1, ["Llanowar Elves", "Forest"])
    state = scenario.build()
    assert state.players[1].library == [bottom, top]
    assert names(state, Zone.library(P1)) == ["Forest", "Llanowar Elves"]
    assert state.players[0].library == []


def test_a_second_library_call_puts_cards_on_top() -> None:
    scenario = Scenario(2)
    first = scenario.library(P0, ["Forest"])
    second = scenario.library(P0, ["Llanowar Elves"])
    assert scenario.build().players[0].library == first + second


def test_graveyard_cards_are_listed_top_first() -> None:
    scenario = Scenario(2)
    top, bottom = scenario.graveyard(P0, ["Llanowar Elves", "Forest"])
    assert scenario.build().players[0].graveyard == [bottom, top]


def test_stack_objects_are_listed_top_first_and_controlled() -> None:
    """405.2: the stack is a pile; objects on it have a controller (110.2 for permanents)."""
    scenario = Scenario(2)
    top, bottom = scenario.stack(P1, ["Llanowar Elves", "Forest"])
    state = scenario.build()
    assert state.stack == [bottom, top]
    assert state.objects[top].controller == P1


def test_every_zone_can_be_filled() -> None:
    scenario = Scenario(3, config=GameConfig.commander_game())
    hand = scenario.hand(P0, ["Forest", "Llanowar Elves"])
    elves = scenario.battlefield(P1, ["Llanowar Elves"])
    stolen = scenario.battlefield(P2, ["Forest"], owner=P0)
    exiled = scenario.exile(P1, ["Forest"])
    in_command = scenario.command(P2, ["Forest"])
    state = scenario.build()
    assert state.players[0].hand == hand
    assert state.battlefield == elves + stolen
    assert state.objects[elves[0]].controller == P1 and state.objects[elves[0]].owner == P1
    assert state.objects[stolen[0]].controller == P2 and state.objects[stolen[0]].owner == P0
    assert state.exile == exiled and state.command == in_command
    assert invariant_violations(state) == []
    assert state_impurities(state) == []


def test_objects_get_ids_and_timestamps_in_call_order() -> None:
    """400.7 and 613.7d: each object gets a new ID and a timestamp when it enters its zone."""
    scenario = Scenario(2)
    a = scenario.battlefield(P0, ["Forest"])[0]
    b = scenario.hand(P1, ["Forest"])[0]
    c = scenario.battlefield(P1, ["Llanowar Elves"])[0]
    state = scenario.build()
    assert [a, b, c] == [1, 2, 3]
    assert [state.objects[obj].timestamp for obj in (a, b, c)] == [1, 2, 3]
    assert state.next_object_id == 4 and state.next_timestamp == 4
    assert [state.objects[obj].card for obj in (a, b, c)] == [1, 2, 3]
    assert state.card_of(state.objects[b]).owner == P1


def test_known_to_records_who_knows_a_hidden_card() -> None:
    """400.2: library cards are hidden, but a player may know one (for example after scry)."""
    scenario = Scenario(3)
    known = scenario.add("Forest", owner=P0, zone=Zone.library(P0), known_to=[P2, P0, P2])
    hidden = scenario.hand(P0, ["Llanowar Elves"])[0]
    state = scenario.build()
    assert state.objects[known].known_to == (P0, P2)
    assert state.objects[hidden].known_to == ()
    assert [view.name for view in view_for(state, P1).players[0].hand] == [None]
    assert [view.name for view in view_for(state, P0).players[0].hand] == ["Llanowar Elves"]


def test_known_to_works_with_more_than_two_players() -> None:
    """400.2: a hidden card is known to its owner (402.3) and to the players listed, not to
    the others."""
    scenario = Scenario(4)
    card = scenario.add("Forest", owner=P1, zone=Zone.hand(P1), known_to=[P2])
    state = scenario.build()
    shown = {p: view_for(state, p).players[1].hand[0].name for p in (P0, P1, P2, P3)}
    assert shown == {P0: None, P1: "Forest", P2: "Forest", P3: None}
    assert state.objects[card].known_to == (P2,)


def test_a_card_cant_be_put_into_another_players_own_zones() -> None:
    """400.3: a card can only be in its owner's library, hand or graveyard."""
    scenario = Scenario(2)
    for zone in (Zone.library(P1), Zone.hand(P1), Zone.graveyard(P1)):
        with pytest.raises(ScenarioError, match=r"\(400\.3\)"):
            scenario.add("Forest", owner=P0, zone=zone)
    assert scenario.build().cards == {}


@pytest.mark.parametrize(
    ("zone", "controller", "error", "message"),
    [
        (BATTLEFIELD, None, EngineError, "objects in the battlefield need controller"),
        (STACK, None, EngineError, "objects in the stack need controller"),
        (EXILE, P0, EngineError, "objects in the exile have no controller"),
        (Zone.hand(P0), P0, EngineError, "hand of player 0 have no controller"),
        (COMMAND, P0, NotImplementedRule, r"^109\.4c: "),
    ],
)
def test_a_controller_is_required_exactly_on_the_battlefield_and_the_stack(
    zone: Zone, controller: PlayerId | None, error: type[Exception], message: str
) -> None:
    """108.4 and 110.2: only permanents and objects on the stack have controllers. A controlled
    object in the command zone (an emblem, 109.4c) is a gap. A refused card changes nothing:
    the next card still gets object ID 1 and timestamp 1 (400.7, 613.7d)."""
    scenario = Scenario(2)
    with pytest.raises(error, match=message):
        scenario.add("Forest", owner=P0, zone=zone, controller=controller)
    obj = scenario.hand(P0, ["Forest"])[0]
    state = scenario.build()
    assert obj == 1 and state.objects[obj].timestamp == 1 and state.objects[obj].card == 1
    assert list(state.cards) == [1] and state.next_object_id == 2 and state.next_timestamp == 2


def test_unknown_and_unimplemented_cards_are_refused() -> None:
    scenario = Scenario(2, registry=CardRegistry())
    with pytest.raises(DeckError, match="not implemented"):
        scenario.hand(P0, ["Forest"])
    with pytest.raises(UnknownCardError):
        Scenario(2).hand(P0, ["Forrest"])


def test_players_and_known_to_must_exist() -> None:
    scenario = Scenario(2)
    with pytest.raises(EngineError, match="no player 2"):
        scenario.hand(PlayerId(2), ["Forest"])
    with pytest.raises(EngineError, match="no player 5"):
        scenario.add("Forest", owner=P0, zone=Zone.hand(P0), known_to=[PlayerId(5)])
    with pytest.raises(EngineError, match="no player 3"):
        scenario.life(PlayerId(3), 1)


def test_commanders_are_designated_in_any_zone() -> None:
    """903.3: a commander is designated for the whole game, whatever zone it is in.

    Whether a card may be a commander (903.3: legendary creature; 903.5) is deck construction,
    which neither ``new_game`` nor the builder checks until deck validation in M7
    (docs/decisions.md). The fixtures have no legendary card, so the commanders here aren't
    legal ones."""
    scenario = Scenario(3, config=GameConfig.commander_game())
    in_command = scenario.commander(P0, "Test Daybreaker")
    on_battlefield = scenario.commander(P1, "Test Daybreaker", zone=BATTLEFIELD)
    in_hand = scenario.commander(P2, "Llanowar Elves", zone=Zone.hand(P2))
    state = scenario.build()
    assert state.command == [in_command]
    assert state.objects[on_battlefield].controller == P1
    assert state.players[2].hand == [in_hand]
    for player, obj in zip(state.players, (in_command, on_battlefield, in_hand), strict=True):
        assert player.commanders == (state.objects[obj].card,)


def test_a_commander_cant_be_in_another_players_hand() -> None:
    """400.3: a card can only be in its owner's hand."""
    scenario = Scenario(2, config=GameConfig.commander_game())
    with pytest.raises(ScenarioError, match=r"\(400\.3\)"):
        scenario.commander(P0, "Test Daybreaker", zone=Zone.hand(P1))
    state = scenario.build()
    assert state.players[0].commanders == () and state.cards == {}


def test_a_second_commander_is_recorded_without_a_legality_check() -> None:
    """903.3 and 702.124a: two commanders need partner, which neither card has. Whether the pair
    is legal is deck construction, not checked until M7; the engine raises the 613.7m gap when
    it would have to order them entering the command zone together."""
    scenario = Scenario(2, config=GameConfig.commander_game(), starting_player=None)
    first = scenario.commander(P0, "Test Daybreaker", zone=Zone.library(P0))
    second = scenario.commander(P0, "Llanowar Elves", zone=Zone.library(P0))
    state = scenario.build(StartGame())
    assert state.players[0].commanders == (
        state.objects[first].card,
        state.objects[second].card,
    )
    with pytest.raises(NotImplementedRule, match=r"^613\.7m: "):
        run_script(state, choose(PlayerOption(P0)))


def test_commanders_need_the_commander_rules() -> None:
    with pytest.raises(ScenarioError, match="903"):
        Scenario(2).commander(P0, "Test Daybreaker")


def test_a_scenario_builds_once() -> None:
    scenario = Scenario(2)
    scenario.build()
    with pytest.raises(ScenarioError, match="already been built"):
        scenario.hand(P0, ["Forest"])
    with pytest.raises(ScenarioError, match="already been built"):
        scenario.build()


def test_build_runs_tasks_to_their_first_decision() -> None:
    state = Scenario(2).build(AskTwice(P1))
    request = pending_decision(state)
    assert request is not None and request.player == P1 and request.kind is DecisionKind.CHOOSE_X


def test_the_seed_feeds_the_games_rng() -> None:
    def chooser(seed: int) -> PlayerId:
        state = Scenario(4, seed=seed, starting_player=None).build(StartGame())
        request = pending_decision(state)
        assert request is not None
        return request.player

    assert chooser(3) == chooser(3)
    assert len({chooser(seed) for seed in range(40)}) == 4


def test_a_scenario_with_commanders_in_the_library_starts_like_a_game() -> None:
    """103.2c: after the starting player is chosen, commanders go to the command zone."""
    scenario = Scenario(2, config=GameConfig.commander_game(), starting_player=None)
    scenario.library(P0, ["Forest", "Forest"])
    scenario.commander(P0, "Test Daybreaker", zone=Zone.library(P0))
    scenario.commander(P1, "Test Daybreaker", zone=Zone.library(P1))
    state = scenario.build(StartGame())
    run_script(state, choose(PlayerOption(P1), kind=DecisionKind.CHOOSE_STARTING_PLAYER))
    assert state.starting_player == P1
    assert names(state, COMMAND) == ["Test Daybreaker // Test Nightfall"] * 2
    # The two Forests were all of P0's library, so the opening hand draws both (103.5).
    assert names(state, Zone.hand(P0)) == ["Forest", "Forest"]
    assert names(state, Zone.library(P0)) == []


def test_run_script_uses_every_step() -> None:
    state = Scenario(2).build(AskTwice(P0), AskTwice(P1))
    assert run_script(state, Step(Number(2)), Step(Number(4), player=P0)) == 2
    assert markers(state) == ["got (2, 4)"]
    with pytest.raises(ScriptError, match="expects player 0"):
        run_script(state, Step(Number(2), player=P0))


def test_run_script_raises_a_rejected_answer() -> None:
    state = Scenario(2).build(AskTwice(P0))
    with pytest.raises(InvalidAnswer, match="even"):
        run_script(state, Step(Number(3)))


def test_run_script_reports_a_game_that_ends_before_the_script() -> None:
    state = Scenario(2).build(AskTwice(P0), EndGame(()))
    with pytest.raises(ScriptError, match="1 of 3 script steps were unused"):
        run_script(state, Step(Number(2)), Step(Number(4)), Step(Number(6)))
    assert state.result is not None


def test_built_states_survive_copy_and_pickle() -> None:
    """CLAUDE.md rule 5: the state is pure data at any moment."""
    scenario = Scenario(3, config=GameConfig.commander_game())
    scenario.library(P0, ["Forest", "Llanowar Elves"])
    scenario.battlefield(P1, ["Llanowar Elves"])
    scenario.commander(P2, "Test Daybreaker")
    state = scenario.build(AskTwice(P2))
    assert copy.deepcopy(state) == state
    assert pickle.loads(pickle.dumps(state)) == state


# --- The turn (at) -------------------------------------------------------------------------------


def test_at_resumes_a_step_as_a_player_is_about_to_receive_priority() -> None:
    scenario = Scenario(3)
    scenario.at(TurnStep.END_OF_COMBAT, active=P1, number=6, priority=P0, passed=[P1, P2])
    state = scenario.build()
    turn = state.turn
    assert turn is not None
    assert (turn.number, turn.active_player, turn.phase, turn.step) == (
        6,
        P1,
        Phase.COMBAT,
        TurnStep.END_OF_COMBAT,
    )
    assert turn.priority == P0 and turn.passed == [P1, P2]
    request = pending_decision(state)
    assert request is not None and request.player == P0
    assert request.kind is DecisionKind.PRIORITY_ACTION
    assert state.event_log == []  # resuming logs nothing: the step had already begun
    assert invariant_violations(state) == []


def test_at_a_main_phase_and_the_default_active_player() -> None:
    scenario = Scenario(2, starting_player=1)
    scenario.at(Phase.POSTCOMBAT_MAIN, lands_played=1)
    state = scenario.build()
    turn = state.turn
    assert turn is not None
    assert (turn.active_player, turn.phase, turn.step, turn.lands_played) == (
        P1,
        Phase.POSTCOMBAT_MAIN,
        None,
        1,
    )


def test_at_with_begin_starts_the_step_from_its_beginning() -> None:
    scenario = Scenario(2)
    scenario.library(P0, ["Forest"])
    scenario.at(TurnStep.DRAW, number=2, begin=True)
    state = scenario.build()
    assert len(state.player(P0).hand) == 1  # 504.1: the turn-based action happened
    first = state.event_log[0].record
    assert type(first).__name__ == "StepBegan"


def test_at_refuses_what_a_turn_cant_be() -> None:
    with pytest.raises(ScenarioError, match="starting player"):
        Scenario(2, starting_player=None).at(TurnStep.UPKEEP)
    with pytest.raises(ScenarioError, match="numbered from 1"):
        Scenario(2).at(TurnStep.UPKEEP, number=0)
    with pytest.raises(ScenarioError, match="no priority yet"):
        Scenario(2).at(TurnStep.UPKEEP, begin=True, priority=P1)
    with pytest.raises(ScenarioError, match="no priority yet"):
        Scenario(2).at(TurnStep.CLEANUP, passed=[P0])
    with pytest.raises(ValueError, match="has steps"):
        Scenario(2).at(Phase.ENDING)
    with pytest.raises(EngineError, match="no player 4"):
        Scenario(2).at(TurnStep.UPKEEP, priority=PlayerId(4))


def test_tasks_given_to_build_run_before_the_turn_resumes() -> None:
    scenario = Scenario(2)
    scenario.at(TurnStep.UPKEEP)
    state = scenario.build(AskTwice(P1))
    request = pending_decision(state)
    assert request is not None and request.kind is DecisionKind.CHOOSE_X
    run_script(state, Step(Number(2)), Step(Number(4)))
    request = pending_decision(state)
    assert request is not None and request.kind is DecisionKind.PRIORITY_ACTION


# --- Combat (506-511) --------------------------------------------------------------------------


def test_attacking_and_blocking_set_the_combat_state() -> None:
    """In the declare attackers step (blocks not declared yet) an attacker's blocked status is
    undecided; once blockers are declared it is unblocked unless ``blocking`` names it (509.1h).
    Two players: the defending player is the nonactive one (506.2)."""
    scenario = Scenario(2)
    (bears,) = scenario.battlefield(P0, ["Grizzly Bears"])
    scenario.at(TurnStep.DECLARE_ATTACKERS)
    scenario.attacking(P1, bears)
    state = scenario.build()
    assert state.turn is not None and state.turn.combat is not None
    assert state.turn.combat.defending_players == (P1,)
    assert state.turn.combat.attackers[bears] == AttackRecord(bears, AttackPlayer(P1))
    assert state.turn.combat.attacks_happened

    scenario = Scenario(2)
    bears, giant = scenario.battlefield(P0, ["Grizzly Bears", "Hill Giant"])
    (wall,) = scenario.battlefield(P1, ["Test Wall"])
    scenario.at(TurnStep.COMBAT_DAMAGE, begin=True)
    scenario.attacking(P1, bears, giant, declared=False)
    scenario.blocking(wall, giant)
    combat = scenario._state.turn.combat  # pyright: ignore[reportPrivateUsage]
    assert combat is not None
    assert list(combat.attackers) == [bears, giant]
    assert combat.attackers[bears].blocked is False
    assert combat.attackers[giant] == AttackRecord(giant, AttackPlayer(P1), False, True)
    assert combat.blockers[wall] == BlockRecord(wall, (giant,))


def test_combat_needs_the_combat_phase() -> None:
    scenario = Scenario(2)
    (bears,) = scenario.battlefield(P0, ["Grizzly Bears"])
    with pytest.raises(ScenarioError, match="combat phase"):
        scenario.attacking(P1, bears)
    scenario.at(Phase.POSTCOMBAT_MAIN)
    with pytest.raises(ScenarioError, match="combat phase"):
        scenario.attacking(P1, bears)


def test_blocks_need_blockers_declared_and_an_attacker() -> None:
    scenario = Scenario(2)
    (bears,) = scenario.battlefield(P0, ["Grizzly Bears"])
    (wall,) = scenario.battlefield(P1, ["Test Wall"])
    scenario.at(TurnStep.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, bears)
    with pytest.raises(ScenarioError, match="509.1"):
        scenario.blocking(wall, bears)

    scenario = Scenario(2)
    (bears,) = scenario.battlefield(P0, ["Grizzly Bears"])
    (wall,) = scenario.battlefield(P1, ["Test Wall"])
    scenario.at(TurnStep.DECLARE_BLOCKERS)
    with pytest.raises(ScenarioError, match="isn't attacking"):
        scenario.blocking(wall, bears)
    scenario.attacking(P1, bears)
    with pytest.raises(ScenarioError, match="already attacking"):
        scenario.attacking(P1, bears)
    scenario.blocking(wall, bears)
    with pytest.raises(ScenarioError, match="already blocking"):
        scenario.blocking(wall, bears)


def test_an_illegal_combat_is_refused_when_built() -> None:
    """The builder leaves legality to the invariants: an attacker of the nonactive player."""
    scenario = Scenario(2)
    (bears,) = scenario.battlefield(P1, ["Grizzly Bears"])
    scenario.at(TurnStep.DECLARE_ATTACKERS)
    scenario.attacking(P1, bears)
    with pytest.raises(EngineError, match="active player"):
        scenario.build()
