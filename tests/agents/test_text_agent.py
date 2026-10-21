"""The text renderer and TextAgent (``resolve.agents.text``)."""

from __future__ import annotations

import io

import pytest

from resolve.agents.text import (
    HELP,
    AnswerSyntaxError,
    QuitGame,
    TextAgent,
    describe_option,
    describe_turn,
    parse_answer,
    render_log_entry,
    render_request,
    render_view,
)
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.request import DecisionRequest
from resolve.decisions.spaces import (
    ActivateAbilityOption,
    Amounts,
    AnswerSpace,
    AnswerValue,
    CastSpellOption,
    ChooseCounts,
    ChooseNumber,
    ChooseOne,
    ChooseOrder,
    ChooseSubset,
    Distribute,
    ManaActivationOption,
    ManaOption,
    Number,
    ObjectOption,
    Order,
    PassOption,
    Pick,
    PickMany,
    PlayerOption,
    PlayLandOption,
)
from resolve.engine.api import view_for
from resolve.engine.view import PlayerView
from resolve.state.config import GameConfig
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import Mana, ManaType
from resolve.state.spell import (
    COMMANDER,
    FROM_HAND,
    NORMAL,
    Alternative,
    AlternativeKind,
    Back,
    Half,
)
from resolve.state.turn import Phase
from resolve.state.turn import Step as TurnStep
from resolve.state.zones import Zone
from tests.engine_support import AskTwice
from tests.game_fixtures import choose_starting_player, request_of, start
from tests.scenario import Scenario

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)
OPTIONS = (PlayerOption(P0), PlayerOption(P1), PlayerOption(P2))


def board() -> tuple[PlayerView, PlayerView, dict[str, ObjectId]]:
    """Views for players 0 and 1 of a small three-player board."""
    scenario = Scenario(3, config=GameConfig.commander_game(), starting_player=1)
    hand = scenario.hand(P0, ["Llanowar Elves"])[0]
    elves = scenario.battlefield(P1, ["Llanowar Elves"])[0]
    grave = scenario.graveyard(P2, ["Forest"])[0]
    scenario.library(P2, ["Forest", "Forest"])
    commander = scenario.commander(P2, "Test Daybreaker")
    exiled = scenario.exile(P0, ["Forest"])[0]
    state = scenario.build(AskTwice(P0))
    ids = {"hand": hand, "elves": elves, "grave": grave, "commander": commander, "exile": exiled}
    return view_for(state, P0), view_for(state, P1), ids


def test_render_view_shows_what_the_viewer_may_see() -> None:
    """402.3 and 401.3: own hand by name, other hands hidden, libraries as counts."""
    own, other, ids = board()
    text = render_view(own)
    assert "=== Player 0's view ===" in text
    assert "Player 0 (you): life 40, library 0" in text
    assert "Player 1 (starting player): life 40, library 0" in text
    assert "Player 2: life 40, library 2" in text
    assert f"hand: Llanowar Elves #{ids['hand']}" in text
    assert f"Battlefield: Llanowar Elves #{ids['elves']}" in text
    assert f"graveyard (top last): Forest #{ids['grave']}" in text
    assert f"Command zone: Test Daybreaker // Test Nightfall #{ids['commander']}" in text
    assert f"Exile: Forest #{ids['exile']}" in text
    assert "Waiting for player 0 (choose_x)." in text
    hidden = render_view(other)
    assert f"hand: hidden card #{ids['hand']}" in hidden
    assert "Llanowar Elves #" + str(ids["hand"]) not in hidden


def test_render_view_shows_only_the_visible_recent_log() -> None:
    state = start(2)
    chooser = request_of(state).player
    choose_starting_player(state, 1)
    own = render_view(view_for(state, chooser), recent_log=100)
    other = render_view(view_for(state, PlayerId(1 - chooser)), recent_log=100)
    assert "answered choose_starting_player: Pick(index=1)" in own
    assert "answered" not in other  # answers are visible only to their player
    assert "StartingPlayerChosen" in other and "(103.1)" in other
    assert "Recent log" not in render_view(view_for(state, chooser), recent_log=0)


def test_render_view_reports_the_result() -> None:
    from tests.engine_support import EndGame, running

    won = running(EndGame((P1,)))
    assert "Game over: won by player 1." in render_view(view_for(won, P0))
    drawn = running(EndGame(()))
    assert "Game over: a draw." in render_view(view_for(drawn, P0))


def test_render_log_entry_lists_fields_and_rules() -> None:
    state = start(2)
    choose_starting_player(state, 0)
    entry = [e for e in state.event_log if type(e.record).__name__ == "LibraryShuffled"][-1]
    assert render_log_entry(entry) == f"[{entry.index}] LibraryShuffled(player=1)  (103.3, 701.24a)"


def test_options_are_described_from_the_view_only() -> None:
    own, other, ids = board()
    assert describe_option(PlayerOption(P0), own) == "player 0 (you)"
    assert describe_option(PlayerOption(P1), own) == "player 1"
    hand = ObjectOption(ids["hand"])
    assert describe_option(hand, own) == f"Llanowar Elves #{ids['hand']}"
    assert describe_option(hand, other) == f"hidden card #{ids['hand']}"
    assert describe_option(ObjectOption(ObjectId(999)), own) == "object #999"


def test_render_request_numbers_the_options_from_zero() -> None:
    own, _, ids = board()
    request = DecisionRequest(
        id=3,
        player=P0,
        for_player=P0,
        kind=DecisionKind.CHOOSE_TARGETS,
        space=ChooseOne((PlayerOption(P2), ObjectOption(ids["elves"]))),
        prompt="Choose a target.",
        rules=("601.2c",),
    )
    assert render_request(request, own).splitlines() == [
        "Player 0: Choose a target. (choose_targets; CR 601.2c)",
        "  0: player 2",
        f"  1: Llanowar Elves #{ids['elves']}",
        "Type one option number.",
    ]


def test_render_request_numbers_the_options_of_a_counts_space() -> None:
    own, _, ids = board()
    space = ChooseCounts((PlayerOption(P2), ObjectOption(ids["elves"])), (2, 1), 2)
    request = DecisionRequest(4, P0, P0, DecisionKind.PAY_COSTS, space, "Pay.", ("601.2h",))
    lines = render_request(request, own).splitlines()
    assert lines[1:3] == ["  0: player 2", f"  1: Llanowar Elves #{ids['elves']}"]


@pytest.mark.parametrize(
    ("space", "hint"),
    [
        (ChooseSubset(OPTIONS, 1, 2), "Type 1 to 2 option numbers ('-' for none)."),
        (ChooseOrder(OPTIONS), "Type every option number, in the order you choose."),
        (ChooseNumber(0, 5), "Type a number from 0 to 5."),
        (ChooseNumber(1), "Type a number from 1."),
        (Distribute(OPTIONS[:2], 3), "adding up to 3."),
        (ChooseCounts(OPTIONS[:2], (2, 1), 2), "at most 2, 1"),
        (ChooseCounts(OPTIONS[:2], (2, 1), 2), "adding up to 2."),
    ],
)
def test_render_request_explains_how_to_answer(space: AnswerSpace, hint: str) -> None:
    own, _, _ = board()
    request = DecisionRequest(1, P0, P0, DecisionKind.DIVIDE, space, "Decide.", ("601.2d",))
    assert hint in render_request(request, own)


@pytest.mark.parametrize(
    ("space", "text", "value"),
    [
        (ChooseOne(OPTIONS), "2", Pick(2)),
        (ChooseOne(OPTIONS), " 0 \n", Pick(0)),
        (ChooseSubset(OPTIONS, 0, 3), "2 0", PickMany((0, 2))),
        (ChooseSubset(OPTIONS, 0, 3), "2,1", PickMany((1, 2))),
        (ChooseSubset(OPTIONS, 0, 3), "-", PickMany(())),
        (ChooseOrder(OPTIONS), "1 0 2", Order((1, 0, 2))),
        (ChooseNumber(-5, 5), "-3", Number(-3)),
        (Distribute(OPTIONS[:2], 3), "2 1", Amounts((2, 1))),
        (ChooseCounts(OPTIONS[:2], (2, 1), 2), "1 1", Amounts((1, 1))),
        (ChooseCounts(OPTIONS[:2], (2, 1), 2), "2,0", Amounts((2, 0))),
        (ChooseOne(OPTIONS), "7", Pick(7)),  # out of range: the engine rejects it, not the parser
    ],
)
def test_parse_answer(space: AnswerSpace, text: str, value: AnswerValue) -> None:
    assert parse_answer(space, text) == value


@pytest.mark.parametrize(
    ("space", "text"),
    [
        (ChooseOne(OPTIONS), ""),
        (ChooseOne(OPTIONS), "one"),
        (ChooseOne(OPTIONS), "1 2"),
        (ChooseNumber(0), "1.5"),
        (ChooseOrder(OPTIONS), "-"),
    ],
)
def test_parse_answer_refuses_text_of_the_wrong_shape(space: AnswerSpace, text: str) -> None:
    with pytest.raises(AnswerSyntaxError):
        parse_answer(space, text)


def agent_with(lines: str) -> tuple[TextAgent, io.StringIO]:
    output = io.StringIO()
    return TextAgent(io.StringIO(lines), output), output


def test_text_agent_reads_an_answer_after_retyping_bad_input() -> None:
    state = start(3)
    request = request_of(state)
    agent, output = agent_with("zero\n\nview\nlog\nhelp\n2\n")
    answer = agent.decide(view_for(state, request.player), request)
    assert (answer.request_id, answer.player, answer.value) == (request.id, request.player, Pick(2))
    text = output.getvalue()
    assert text.count("Not an answer") == 2
    assert text.count(f"=== Player {request.player}'s view ===") == 2  # first, then "view"
    assert HELP in text
    assert "(no log)" in text  # the chooser has no visible log entries yet


@pytest.mark.parametrize("lines", ["quit\n", "q\n", ""])
def test_text_agent_quits_on_quit_or_end_of_input(lines: str) -> None:
    state = start(2)
    request = request_of(state)
    agent, _ = agent_with(lines)
    with pytest.raises(QuitGame):
        agent.decide(view_for(state, request.player), request)


def test_text_agent_can_skip_the_view() -> None:
    state = start(2)
    request = request_of(state)
    output = io.StringIO()
    TextAgent(io.StringIO("0\n"), output, show_view=False).decide(
        view_for(state, request.player), request
    )
    assert "view ===" not in output.getvalue()
    assert "Choose which player takes the first turn." in output.getvalue()


def test_a_hidden_library_card_never_appears_in_any_view() -> None:
    """401.2: no player may look at the cards in a library; the view shows only a count (401.3)."""
    scenario = Scenario(2)
    scenario.library(P0, ["Llanowar Elves"])
    scenario.add("Forest", owner=P1, zone=Zone.library(P1), known_to=[P1])
    state = scenario.build(AskTwice(P0))
    for player in (P0, P1):
        text = render_view(view_for(state, player))
        assert "Llanowar Elves" not in text and "Forest" not in text


def test_priority_options_are_described_in_words() -> None:
    own, other, ids = board()
    assert describe_option(PassOption(), own) == "pass priority"
    assert describe_option(CastSpellOption(ids["hand"], NORMAL, FROM_HAND), own) == (
        f"cast Llanowar Elves #{ids['hand']}"
    )
    assert (
        describe_option(CastSpellOption(ids["hand"], NORMAL, FROM_HAND), other)
        == f"cast hidden card #{ids['hand']}"
    )
    assert describe_option(PlayLandOption(ids["grave"]), own) == f"play Forest #{ids['grave']}"


def test_casting_and_paying_options_are_described_in_words() -> None:
    """The variant (601.3e) and a zone other than the hand (903.8) are named; a class of mana
    (601.2h) is its symbol and source; an activation to reverse (733.1) names the ability."""
    own, _, ids = board()
    hand, elves, commander = ids["hand"], ids["elves"], ids["commander"]
    assert describe_option(CastSpellOption(hand, Half(1), FROM_HAND), own) == (
        f"cast Llanowar Elves #{hand} (right half)"
    )
    assert describe_option(CastSpellOption(hand, Back(), FROM_HAND), own) == (
        f"cast Llanowar Elves #{hand} (back face)"
    )
    omen = CastSpellOption(hand, Alternative(AlternativeKind.OMEN), FROM_HAND)
    assert describe_option(omen, own) == f"cast Llanowar Elves #{hand} (as an Omen)"
    assert describe_option(CastSpellOption(commander, NORMAL, COMMANDER), own) == (
        f"cast Test Daybreaker // Test Nightfall #{commander} from the command zone"
    )
    assert describe_option(ManaOption(Mana(ManaType.GREEN, elves)), own) == (
        f"{{G}} from Llanowar Elves #{elves}"
    )
    assert describe_option(ManaOption(Mana(ManaType.COLORLESS)), own) == "{C}"
    assert describe_option(ManaActivationOption(0, elves, 0), own) == (
        f"reverse ability 0 of Llanowar Elves #{elves}"
    )


def test_render_view_shows_the_turn_and_who_lost() -> None:
    scenario = Scenario(2)
    scenario.at(Phase.PRECOMBAT_MAIN, active=P1, number=3, priority=P0, passed=[P1])
    view = view_for(scenario.build(), P0)
    text = render_view(view)
    assert "Turn 3, player 1's turn: precombat main phase; player 0 has priority." in text
    assert describe_turn(view_for(Scenario(2).build(), P0)) is None

    scenario = Scenario(2)
    scenario.life(P1, 0)
    scenario.at(TurnStep.UPKEEP)
    text = render_view(view_for(scenario.build(), P0))
    assert "Player 1 (lost) (left the game): life 0" in text
    assert "Turn 1, player 0's turn: upkeep step; nobody has priority." in text


def test_render_view_shows_tapped_permanents_mana_and_abilities() -> None:
    scenario = Scenario(2)
    (forest,) = scenario.battlefield(P0, ["Forest"])
    scenario.tap(forest).mana(P0, ManaType.GREEN, ManaType.GREEN)
    view = view_for(scenario.build(), P1)
    text = render_view(view)
    assert f"Forest #{forest} (tapped)" in text
    assert "library 0, mana {G}{G}" in text
    assert describe_option(ActivateAbilityOption(forest, 0), view) == (
        f"activate ability 0 of Forest #{forest} (tapped)"
    )


def test_describe_object_shows_damage() -> None:
    scenario = Scenario(2)
    (bears,) = scenario.battlefield(P0, ["Grizzly Bears"])
    scenario.damage(bears, 1)
    text = render_view(view_for(scenario.build(), P1))
    assert f"Grizzly Bears #{bears} (1 damage)" in text
