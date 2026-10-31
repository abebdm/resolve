"""The auto-payer (``resolve.agents.autopay``): an agent-side helper that pays mana costs.

It sees only the view and the request (rule 4): the payments under way (``PlayerView.payments``),
the payer's mana pool, and the abilities of the permanents (``ObjectView.abilities``). It answers
the payment decisions (601.2g ``ACTIVATE_MANA_ABILITIES``, 601.2h ``PAY_COSTS``, 106.1a
``CHOOSE_COLOR`` while paying, 733.1 ``REVERSE_MANA_ABILITIES``) and delegates every other
decision. What a payment needs, from the pinned CR:

- 107.4a: each colored symbol needs one mana of its color; 107.4b: generic mana takes any type;
  107.4c: {C} needs colorless mana.
- 605.3a: mana abilities may be activated while paying; 605.3c: not the one being activated.
- 106.6: restricted mana may be spent only on what its restriction allows.
- 118.3, 733.1: a cost that can't be paid makes the action illegal; it is reversed.
- 723.5a: a player controlling another uses only the controlled player's resources for that
  player's decisions.

Which of several payments it picks is its policy (plan M2.5, §3.6): it prefers exact colors,
keeps flexible mana (a choice of color) and restricted mana for where they are required, then
taps the fewest permanents. The tests check those choices on boards where the policy decides,
and otherwise only that the engine accepts the answers and the spell is cast.
"""

from __future__ import annotations

import copy
import pickle

import pytest

from resolve.agents.autopay import AutoPayAgent
from resolve.agents.driver import play
from resolve.agents.random_agent import RandomAgent
from resolve.cards.primitives.restrictions import SpendOnlyOnSubtype
from resolve.cards.primitives.words import SubtypeWord
from resolve.data.types import Color
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.request import DecisionAnswer, DecisionRequest
from resolve.decisions.spaces import (
    ActivateAbilityOption,
    Amounts,
    ChooseCounts,
    ChooseOne,
    ChooseSubset,
    ColorOption,
    ManaOption,
    Pick,
    PickMany,
    PlayerOption,
)
from resolve.engine.api import new_game, pending_decision, submit, view_for
from resolve.engine.payment import PAY
from resolve.engine.view import PlayerView
from resolve.errors import NotImplementedRule
from resolve.events.spells import ActionReversed, SpellCast
from resolve.rules import defaults
from resolve.state.config import GameConfig
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import Mana, ManaType
from resolve.state.turn import Phase
from resolve.state.zones import ZoneKind
from tests.casting_support import (
    activate,
    activate_with_priority,
    cast,
    choose_targets,
    choose_x,
    records,
)
from tests.game_fixtures import request_of
from tests.scenario import Scenario, run_script
from tools.fuzz import recipe_deck

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)
W, R, G = ManaType.WHITE, ManaType.RED, ManaType.GREEN
DINOSAUR = SpendOnlyOnSubtype(SubtypeWord("Dinosaur"))
PAYMENT_KINDS = (
    DecisionKind.ACTIVATE_MANA_ABILITIES,
    DecisionKind.PAY_COSTS,
    DecisionKind.CHOOSE_COLOR,
    DecisionKind.REVERSE_MANA_ABILITIES,
)


class MustNotBeAsked:
    """An inner agent for boards where the auto-payer must answer everything itself."""

    def decide(self, view: PlayerView, request: DecisionRequest) -> DecisionAnswer:
        raise AssertionError(f"the auto-payer delegated a {request.kind.value} decision")


class FirstOption:
    """An inner agent that answers the first option and records what it was asked."""

    def __init__(self) -> None:
        self.asked: list[DecisionKind] = []

    def decide(self, view: PlayerView, request: DecisionRequest) -> DecisionAnswer:
        self.asked.append(request.kind)
        return DecisionAnswer(request.id, request.player, Pick(0))


def autopay(state: GameState) -> list[tuple[DecisionRequest, DecisionAnswer]]:
    """Let the auto-payer answer until a decision other than a payment is pending; returns each
    request and its answer. Every answer must be accepted."""
    agent = AutoPayAgent(MustNotBeAsked())
    answered: list[tuple[DecisionRequest, DecisionAnswer]] = []
    while (request := pending_decision(state)) is not None and request.kind in PAYMENT_KINDS:
        answer = agent.decide(view_for(state, request.player), request)
        submit(state, answer)
        answered.append((request, answer))
    return answered


def board(
    lands: list[str],
    spell: str,
    *,
    config: GameConfig | None = None,
    commander: str | None = None,
) -> tuple[GameState, list[ObjectId], ObjectId]:
    """P0's main phase with ``lands`` (any permanents) and ``spell`` in hand, cast and waiting for
    its payment."""
    scenario = Scenario(2, config=config)
    if commander is not None:
        scenario.commander(P0, commander)
    permanents = scenario.battlefield(P0, lands)
    (card,) = scenario.hand(P0, [spell])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(card, P0))
    return state, permanents, card


def tapped(state: GameState, objs: list[ObjectId]) -> list[bool]:
    return [state.objects[obj].tapped for obj in objs]


def was_cast(state: GameState) -> bool:
    return len(records(state, SpellCast)) == 1


def test_601_2h_pays_grizzly_bears_from_two_forests_and_a_plains_with_the_forests() -> None:
    """{1}{G}: a Forest pays {G} (107.4a); the generic {1} takes either land (107.4b). Exact colors
    first: the second Forest, leaving the Plains."""
    state, (forest, other, plains), _ = board(["Forest", "Forest", "Plains"], "Grizzly Bears")
    autopay(state)
    assert was_cast(state)
    assert tapped(state, [forest, other, plains]) == [True, True, False]
    assert state.player(P0).mana_pool == []


def test_601_2h_pays_hill_giant_with_sol_ring_a_mountain_and_a_forest() -> None:
    """{3}{R}: the Mountain's {R}, then Sol Ring's {C}{C} and the Forest's {G} for {3}."""
    state, permanents, _ = board(["Sol Ring", "Mountain", "Forest"], "Hill Giant")
    autopay(state)
    assert was_cast(state)
    assert tapped(state, permanents) == [True, True, True]
    assert state.player(P0).mana_pool == []


def test_605_3a_pays_hill_giant_through_selesnya_signet_tapping_the_forest_for_the_signet() -> None:
    """{3}{R} from Selesnya Signet ({1}, {T}: Add {G}{W}), Forest, Mountain and Plains: only all
    four make enough mana, so the Signet is activated and a land pays its {1} (605.3a). That land
    can't be the Mountain, whose {R} the spell needs. The Plains would pay it as legally; the
    Forest is the auto-payer's choice, its tie-break being the earliest permanent (policy, not a
    rule)."""
    state, (signet, forest, mountain, plains), _ = board(
        ["Selesnya Signet", "Forest", "Mountain", "Plains"], "Hill Giant"
    )
    answered = autopay(state)
    assert was_cast(state)
    assert tapped(state, [signet, forest, mountain, plains]) == [True, True, True, True]
    for_signet = [
        (request, answer)
        for request, answer in answered
        if request.kind is DecisionKind.ACTIVATE_MANA_ABILITIES and request.source == signet
    ]
    assert for_signet, "the Signet's {1} was paid by activating a land"
    request, answer = for_signet[0]
    assert isinstance(request.space, ChooseOne) and isinstance(answer.value, Pick)
    assert request.space.chosen(answer.value) == ActivateAbilityOption(forest, 0)
    assert state.player(P0).mana_pool == []


def test_601_2h_paying_the_signet_from_the_pool_keeps_the_red_the_spell_needs() -> None:
    """Pool {R}{G}{G} and Selesnya Signet, casting Hill Giant ({3}{R}): the Signet's {1} could take
    the {R} or a {G} (601.2h asks); spending the {R} would leave the spell's {R} unpaid."""
    scenario = Scenario(2)
    (signet,) = scenario.battlefield(P0, ["Selesnya Signet"])
    (giant,) = scenario.hand(P0, ["Hill Giant"])
    scenario.mana(P0, R, G, G)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(giant, P0))
    answered = autopay(state)
    assert DecisionKind.PAY_COSTS in [request.kind for request, _ in answered]
    assert was_cast(state)
    assert state.objects[signet].tapped
    assert state.player(P0).mana_pool == []


def test_601_2g_answers_pay_when_the_pool_already_pays() -> None:
    """Pool {G}{G}{W} pays {1}{G} without tapping the Forest. Two payments are possible (GG and
    GW), so 601.2h asks; the engine accepts the answer."""
    scenario = Scenario(2)
    (forest,) = scenario.battlefield(P0, ["Forest"])
    (bears,) = scenario.hand(P0, ["Grizzly Bears"])
    scenario.mana(P0, G, G, W)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(bears, P0))
    answered = autopay(state)
    kinds = [request.kind for request, _ in answered]
    assert kinds == [DecisionKind.ACTIVATE_MANA_ABILITIES, DecisionKind.PAY_COSTS]
    first_request, first_answer = answered[0]
    assert isinstance(first_request.space, ChooseOne) and isinstance(first_answer.value, Pick)
    assert first_request.space.chosen(first_answer.value) == PAY
    assert was_cast(state)
    assert not state.objects[forest].tapped
    assert len(state.player(P0).mana_pool) == 1


def test_106_1a_picks_the_color_the_cost_needs_from_command_tower() -> None:
    """Commander Avacyn's Pilgrim (green and white, 903.4): Command Tower and a Plains pay {1}{G}
    only if the Tower's mana is green."""
    state, permanents, _ = board(
        ["Command Tower", "Plains"],
        "Grizzly Bears",
        config=GameConfig.commander_game(),
        commander="Avacyn's Pilgrim",
    )
    answered = autopay(state)
    colors = [
        request.space.chosen(answer.value)
        for request, answer in answered
        if request.kind is DecisionKind.CHOOSE_COLOR
        and isinstance(request.space, ChooseOne)
        and isinstance(answer.value, Pick)
    ]
    assert colors == [ColorOption(Color.GREEN)]
    assert was_cast(state)
    assert tapped(state, permanents) == [True, True]


def test_keeps_command_tower_when_basic_lands_pay() -> None:
    """Command Tower, Forest and Plains for {1}{G}: the Forest and Plains pay, and the Tower's
    flexible mana is kept for where it's required."""
    state, (tower, forest, plains), _ = board(
        ["Command Tower", "Forest", "Plains"],
        "Grizzly Bears",
        config=GameConfig.commander_game(),
        commander="Avacyn's Pilgrim",
    )
    autopay(state)
    assert was_cast(state)
    assert tapped(state, [tower, forest, plains]) == [False, True, True]


def test_106_6_spends_lorekeeper_mana_on_a_dinosaur() -> None:
    """Test Raptor ({1}{G}, a Dinosaur) from Ixalli's Lorekeeper and a Forest: the Lorekeeper's
    mana may pay for it (106.6) and is needed."""
    state, permanents, _ = board(["Ixalli's Lorekeeper", "Forest"], "Test Raptor")
    autopay(state)
    assert was_cast(state)
    assert tapped(state, permanents) == [True, True]


def test_106_6_doesnt_tap_lorekeeper_for_another_spell() -> None:
    """Grizzly Bears from Ixalli's Lorekeeper and two Forests: the Lorekeeper's mana can't pay for
    it (106.6), so the Forests pay and the Lorekeeper stays untapped."""
    state, (lorekeeper, forest, other), _ = board(
        ["Ixalli's Lorekeeper", "Forest", "Forest"], "Grizzly Bears"
    )
    autopay(state)
    assert was_cast(state)
    assert tapped(state, [lorekeeper, forest, other]) == [False, True, True]


def test_106_6_with_only_lorekeeper_mana_for_another_spell_there_is_no_plan() -> None:
    """Grizzly Bears from Ixalli's Lorekeeper and one Forest: no payment exists (106.6), so the
    auto-payer answers "pay" without tapping anything and the cast is reversed (118.3, 733.1)."""
    state, permanents, bears = board(["Ixalli's Lorekeeper", "Forest"], "Grizzly Bears")
    answered = autopay(state)
    assert [request.kind for request, _ in answered] == [DecisionKind.ACTIVATE_MANA_ABILITIES]
    assert not was_cast(state)
    assert len(records(state, ActionReversed)) == 1
    assert tapped(state, permanents) == [False, False]
    assert state.objects[bears].zone.kind is ZoneKind.HAND


def test_733_1_with_no_plan_it_answers_pay_and_reverses_everything() -> None:
    """Hill Giant ({3}{R}) with only a Forest and a Mountain: the player (a script) already tapped
    the Forest while paying. The auto-payer finds no plan, answers "pay", and when the cast is
    reversed it reverses every mana ability activated (733.1): the Forest untaps."""
    state, (forest, mountain), giant = board(["Forest", "Mountain"], "Hill Giant")
    run_script(state, activate(forest))
    answered = autopay(state)
    kinds = [request.kind for request, _ in answered]
    assert kinds == [DecisionKind.ACTIVATE_MANA_ABILITIES, DecisionKind.REVERSE_MANA_ABILITIES]
    request, answer = answered[0]
    assert isinstance(request.space, ChooseOne) and isinstance(answer.value, Pick)
    assert request.space.chosen(answer.value) == PAY
    request, answer = answered[1]
    assert isinstance(request.space, ChooseSubset)
    assert answer.value == PickMany(tuple(range(len(request.space.options))))
    (reversal,) = records(state, ActionReversed)
    assert reversal.kept == ()
    assert tapped(state, [forest, mountain]) == [False, False]
    assert state.player(P0).mana_pool == []
    assert state.objects[giant].zone.kind is ZoneKind.HAND


def test_it_delegates_other_decisions() -> None:
    """Priority is the inner agent's, as is a color chosen with no payment under way (a mana
    ability activated with priority, 605.3a)."""
    scenario = Scenario(2)
    scenario.battlefield(P0, ["Ixalli's Lorekeeper"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    inner = FirstOption()
    agent = AutoPayAgent(inner)
    request = request_of(state)
    assert request.kind is DecisionKind.PRIORITY_ACTION
    assert agent.decide(view_for(state, P0), request) == DecisionAnswer(request.id, P0, Pick(0))
    lorekeeper = state.battlefield[0]
    run_script(state, activate_with_priority(lorekeeper))
    request = request_of(state)
    assert request.kind is DecisionKind.CHOOSE_COLOR
    agent.decide(view_for(state, P0), request)
    assert inner.asked == [DecisionKind.PRIORITY_ACTION, DecisionKind.CHOOSE_COLOR]


def test_it_is_deterministic() -> None:
    """The same view and request give the same answer; games played by auto-paying random agents
    from the same seeds end in equal states."""
    state, _, _ = board(["Selesnya Signet", "Forest", "Mountain", "Plains"], "Hill Giant")
    request = request_of(state)
    view = view_for(state, P0)
    first = AutoPayAgent(MustNotBeAsked()).decide(view, request)
    # A copy of the view made by pickling has new objects throughout: an answer that depended on
    # object identity or on the order of a set would show here.
    copied = pickle.loads(pickle.dumps((view, request)))
    second = AutoPayAgent(MustNotBeAsked()).decide(*copied)
    assert first == second

    def game() -> GameState:
        decks = [recipe_deck("creatures", 8), recipe_deck("spells", 8)]
        played = new_game(GameConfig.standard(), decks, 7)
        agents = [AutoPayAgent(RandomAgent(seat)) for seat in range(2)]
        try:
            play(played, agents, max_answers=600, on_invalid=lambda error: None)
        except NotImplementedRule as gap:  # creatures attack: declaring blockers is M3.3
            assert str(gap).startswith("509.1"), gap
        return played

    one, two = game(), game()
    assert one == two
    assert records(one, SpellCast), "the game cast spells"
    assert copy.deepcopy(one) == one


def test_723_5a_deciding_for_another_player_it_uses_only_that_players_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P1 controls P0 (723.5) and makes P0's decisions, through P1's auto-payer. P1's own pool
    ({G}{G}, enough for {1}{G}) and Forest are no resource of P0's (723.5a): P0's Forests pay."""

    def deciding(state: object, player: PlayerId) -> PlayerId:
        return P1 if player == P0 else player

    monkeypatch.setattr(defaults, "deciding_player", deciding)
    scenario = Scenario(2)
    forest, other = scenario.battlefield(P0, ["Forest", "Forest"])
    (own,) = scenario.battlefield(P1, ["Forest"])
    (bears,) = scenario.hand(P0, ["Grizzly Bears"])
    scenario.mana(P1, G, G)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(bears, P1))
    request = request_of(state)
    assert (request.player, request.for_player) == (P1, P0)
    autopay(state)
    assert was_cast(state)
    assert tapped(state, [forest, other, own]) == [True, True, False]
    assert state.player(P1).mana_pool == [Mana(G), Mana(G)]


@pytest.mark.parametrize(
    ("lands", "spell", "cast_"),
    [
        (["Forest", "Forest", "Plains"], "Grizzly Bears", True),
        # 605.3a: the Forest pays one Signet's {1}, that Signet's mana the other's.
        (["Selesnya Signet", "Selesnya Signet", "Forest", "Mountain"], "Hill Giant", True),
        # 903.4f, 106.5: no commander, so neither adds mana; the Mountain alone is 1 < 4.
        (["Command Tower", "Arcane Signet", "Mountain"], "Hill Giant", False),
        # 602.5: Temple needs five lands (it has two), so {C}{C} + {R} is 3 < 4.
        (["Sol Ring", "Temple of the False God", "Mountain"], "Hill Giant", False),
    ],
)
def test_its_answers_are_accepted_and_it_casts_exactly_what_can_be_paid(
    lands: list[str], spell: str, cast_: bool
) -> None:
    """Every answer it gives is accepted (``autopay`` submits them; an ``InvalidAnswer`` fails the
    test), and the spell is cast exactly when the board can pay it."""
    state, permanents, _ = board(lands, spell)
    autopay(state)
    assert was_cast(state) is cast_
    if not cast_:
        assert not any(tapped(state, permanents))  # 733.1: everything reversed


def test_903_4_a_commanders_identity_without_the_color_gives_no_plan() -> None:
    """Commander Hill Giant (red): Command Tower makes only {R} (903.4), so Command Tower and a
    Plains can't pay {1}{G} (107.4a). No plan: the Tower is never activated."""
    state, (tower, plains), _ = board(
        ["Command Tower", "Plains"],
        "Grizzly Bears",
        config=GameConfig.commander_game(),
        commander="Hill Giant",
    )
    answered = autopay(state)
    assert [request.kind for request, _ in answered] == [DecisionKind.ACTIVATE_MANA_ABILITIES]
    assert not was_cast(state)
    assert tapped(state, [tower, plains]) == [False, False]


def test_605_3a_pays_a_signet_activated_with_priority() -> None:
    """The inner agent activates Selesnya Signet with priority (605.3a); its {1} is a payment
    under way (602.2b), so the auto-payer taps the Forest for it and the inner agent isn't asked.
    The pool ends {G}{W}."""
    scenario = Scenario(2)
    signet, forest = scenario.battlefield(P0, ["Selesnya Signet", "Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, activate_with_priority(signet))
    answered = autopay(state)
    assert [request.kind for request, _ in answered] == [DecisionKind.ACTIVATE_MANA_ABILITIES]
    assert tapped(state, [signet, forest]) == [True, True]
    assert state.player(P0).mana_pool == [Mana(G, signet), Mana(W, signet)]
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION


def test_106_1a_chooses_the_color_for_a_signet_activated_with_priority() -> None:
    """Command Tower pays that Signet's {1}: a payment is under way, so the auto-payer chooses the
    Tower's color (106.1a; either of W and G pays generic mana, 107.4b)."""
    scenario = Scenario(2, config=GameConfig.commander_game())
    scenario.commander(P0, "Avacyn's Pilgrim")
    signet, tower = scenario.battlefield(P0, ["Selesnya Signet", "Command Tower"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, activate_with_priority(signet))
    answered = autopay(state)
    assert DecisionKind.CHOOSE_COLOR in [request.kind for request, _ in answered]
    assert tapped(state, [signet, tower]) == [True, True]
    assert state.player(P0).mana_pool == [Mana(G, signet), Mana(W, signet)]


def test_106_6_lorekeeper_mana_cant_pay_a_signet_for_a_dinosaur() -> None:
    """Test Raptor ({1}{G}) from Ixalli's Lorekeeper and Selesnya Signet: the Lorekeeper's mana
    may pay for the Dinosaur spell but not for the Signet's {1} (106.6: the Signet isn't a
    Dinosaur source), so the Signet can't add mana and one unit can't pay {1}{G}. No plan."""
    state, permanents, _ = board(["Ixalli's Lorekeeper", "Selesnya Signet"], "Test Raptor")
    answered = autopay(state)
    assert [request.kind for request, _ in answered] == [DecisionKind.ACTIVATE_MANA_ABILITIES]
    request, answer = answered[0]
    assert isinstance(request.space, ChooseOne) and isinstance(answer.value, Pick)
    assert request.space.chosen(answer.value) == PAY
    assert not was_cast(state)
    assert tapped(state, permanents) == [False, False]


def restricted_pool(spell: str) -> tuple[GameState, ObjectId]:
    """A Forest and {G} in the pool that may be spent only on a Dinosaur (106.6), casting
    ``spell``."""
    scenario = Scenario(2)
    (forest,) = scenario.battlefield(P0, ["Forest"])
    (card,) = scenario.hand(P0, [spell])
    scenario.mana(P0, G, restriction=DINOSAUR)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(card, P0))
    return state, forest


def test_106_6_restricted_mana_in_the_pool_pays_only_for_a_dinosaur() -> None:
    """Test Raptor: the restricted {G} and the Forest pay {1}{G}. Grizzly Bears: the restricted
    {G} can't pay for it, so no plan; the Forest stays untapped and the cast is reversed."""
    state, forest = restricted_pool("Test Raptor")
    autopay(state)
    assert was_cast(state)
    assert state.objects[forest].tapped and state.player(P0).mana_pool == []

    state, forest = restricted_pool("Grizzly Bears")
    answered = autopay(state)
    assert [request.kind for request, _ in answered] == [DecisionKind.ACTIVATE_MANA_ABILITIES]
    assert not was_cast(state)
    assert not state.objects[forest].tapped
    assert state.player(P0).mana_pool == [Mana(G, None, DINOSAUR)]


def test_118_3_a_tapped_land_is_no_resource() -> None:
    """A tapped Forest can't pay {T} (118.3), so it isn't offered: a Plains alone can't pay
    {1}{G}. No plan."""
    scenario = Scenario(2)
    forest, plains = scenario.battlefield(P0, ["Forest", "Plains"])
    scenario.tap(forest)
    (bears,) = scenario.hand(P0, ["Grizzly Bears"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(bears, P0))
    autopay(state)
    assert not was_cast(state)
    assert not state.objects[plains].tapped


def test_302_6_a_summoning_sick_mana_creature_is_no_resource() -> None:
    """Llanowar Elves that came under P0's control this turn can't use {T} (302.6): a Plains and
    the Elves don't pay {1}{G}. From a creature P0 controlled since the turn began, they do."""
    for entered, payable in ((1, False), (0, True)):
        scenario = Scenario(2)
        elves, plains = scenario.battlefield(P0, ["Llanowar Elves", "Plains"], entered_turn=entered)
        (bears,) = scenario.hand(P0, ["Grizzly Bears"])
        scenario.at(Phase.PRECOMBAT_MAIN, number=1)
        state = scenario.build()
        run_script(state, cast(bears, P0))
        autopay(state)
        assert was_cast(state) is payable
        assert tapped(state, [elves, plains]) == [payable, payable]


def test_602_5_temple_of_the_false_god_pays_only_with_five_lands() -> None:
    """Hill Giant ({3}{R}) from Temple of the False God, a Mountain, a Forest and Plains: with four
    lands the Temple can't be activated (602.5) and three mana don't pay; with five it adds
    {C}{C}, and Temple, Mountain and one more land pay."""
    for plains, payable in ((1, False), (2, True)):
        lands = ["Temple of the False God", "Mountain", "Forest", *["Plains"] * plains]
        state, permanents, _ = board(lands, "Hill Giant")
        autopay(state)
        assert was_cast(state) is payable
        if payable:
            assert tapped(state, permanents[:3]) == [True, True, True]
            assert sum(tapped(state, permanents)) == 3  # 3 permanents for 4 mana
        else:
            assert not any(tapped(state, permanents))


def test_107_4c_colorless_symbols_need_colorless_mana() -> None:
    """Test Ember ({1}{C}): Sol Ring's {C}{C} pays it; two Forests' {G}{G} doesn't (107.4c)."""
    state, (ring,), _ = board(["Sol Ring"], "Test Ember")
    autopay(state)
    assert was_cast(state) and state.objects[ring].tapped
    state, forests, _ = board(["Forest", "Forest"], "Test Ember")
    autopay(state)
    assert not was_cast(state) and not any(tapped(state, forests))


def test_118_3a_a_cost_of_0_is_paid_without_tapping_anything() -> None:
    """Test Mox ({0}) with a Forest on the battlefield: 601.2g offers the Forest; the auto-payer
    answers "pay", and nothing pays nothing (118.3a)."""
    state, (forest,), _ = board(["Forest"], "Test Mox")
    answered = autopay(state)
    request, answer = answered[0]
    assert isinstance(request.space, ChooseOne) and isinstance(answer.value, Pick)
    assert request.space.chosen(answer.value) == PAY
    assert was_cast(state) and not state.objects[forest].tapped


def test_in_a_three_player_game_it_pays_with_the_casters_lands_only() -> None:
    """P2 casts Grizzly Bears in its turn; P0 and P1 have untapped Forests and mana in their
    pools, which aren't P2's to spend (106.4: a player's mana pool; 602.2: their permanents)."""
    scenario = Scenario(3)
    others = [*scenario.battlefield(P0, ["Forest"]), *scenario.battlefield(P1, ["Forest"])]
    mine = scenario.battlefield(P2, ["Forest", "Forest"])
    scenario.mana(P0, G, G).mana(P1, G, G)
    (bears,) = scenario.hand(P2, ["Grizzly Bears"])
    scenario.at(Phase.PRECOMBAT_MAIN, active=P2)
    state = scenario.build()
    run_script(state, cast(bears, P2))
    autopay(state)
    assert was_cast(state)
    assert tapped(state, mine) == [True, True] and tapped(state, others) == [False, False]
    assert state.player(P0).mana_pool == [Mana(G), Mana(G)]
    assert state.player(P1).mana_pool == [Mana(G), Mana(G)]


def test_723_5a_in_a_three_player_game_the_controller_pays_with_the_controlled_players_lands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P2 controls P1 (723.5) while P1 casts Grizzly Bears: P2's auto-payer taps P1's Forests,
    not P2's, and leaves P2's pool alone (723.5a)."""

    def deciding(state: object, player: PlayerId) -> PlayerId:
        return P2 if player == P1 else player

    monkeypatch.setattr(defaults, "deciding_player", deciding)
    scenario = Scenario(3)
    p1_lands = scenario.battlefield(P1, ["Forest", "Forest"])
    p2_lands = scenario.battlefield(P2, ["Forest", "Forest"])
    scenario.mana(P2, G, G)
    (bears,) = scenario.hand(P1, ["Grizzly Bears"])
    scenario.at(Phase.PRECOMBAT_MAIN, active=P1)
    state = scenario.build()
    run_script(state, cast(bears, P2))
    assert (request_of(state).player, request_of(state).for_player) == (P2, P1)
    autopay(state)
    assert was_cast(state)
    assert tapped(state, p1_lands) == [True, True] and tapped(state, p2_lands) == [False, False]
    assert state.player(P2).mana_pool == [Mana(G), Mana(G)]


def test_605_3a_one_signets_mana_pays_another_signets_cost() -> None:
    """Hill Giant ({3}{R}) from Arcane Signet (commander Savannah Lions: white, 903.4), two
    Selesnya Signets and a Mountain: the Arcane Signet's {W} pays one Selesnya Signet's {1}, whose
    {G}{W} pays the other's {1} and the spell; nothing else makes six mana for the three costs.
    (Found by ``test_autopay_brute_force``.)"""
    state, permanents, _ = board(
        ["Arcane Signet", "Selesnya Signet", "Mountain", "Selesnya Signet"],
        "Hill Giant",
        config=GameConfig.commander_game(),
        commander="Savannah Lions",
    )
    autopay(state)
    assert was_cast(state)
    assert tapped(state, permanents) == [True, True, True, True]
    assert state.player(P0).mana_pool == []


def test_601_2h_paying_the_signet_from_the_pool_keeps_the_color_a_later_land_cant_make() -> None:
    """Pool {B}{R}, a Plains and Selesnya Signet, casting Hill Giant ({3}{R}): the Signet's {1}
    can take the {B} or the {R} (601.2h asks). Either leaves the spell one symbol short until the
    Plains is tapped, but the Plains can pay only a generic symbol (107.4b), not the {R} (107.4a),
    so spending the {R} loses the spell. The auto-payer plans to pay the Signet from the pool, and
    then spends the {B} (paying it with the Plains instead would be legal too). (Found by
    ``test_autopay_brute_force --thorough``.)"""
    scenario = Scenario(2)
    plains, signet = scenario.battlefield(P0, ["Plains", "Selesnya Signet"])
    (giant,) = scenario.hand(P0, ["Hill Giant"])
    scenario.mana(P0, ManaType.BLACK, R)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(giant, P0))
    answered = autopay(state)
    (paid,) = [(r, a) for r, a in answered if r.kind is DecisionKind.PAY_COSTS]
    request, answer = paid
    assert isinstance(request.space, ChooseCounts) and isinstance(answer.value, Amounts)
    spent = {
        option.mana.type: amount
        for option, amount in zip(request.space.options, answer.value.amounts, strict=True)
        if isinstance(option, ManaOption)
    }
    assert spent == {ManaType.BLACK: 1, R: 0}
    assert was_cast(state)
    assert tapped(state, [plains, signet]) == [True, True]
    assert state.player(P0).mana_pool == []


def test_107_3a_the_auto_payer_pays_the_total_with_x() -> None:
    """Test Blaze with X = 2 from three Mountains: the auto-payer plans from the payment under
    way, whose cost is the total with the announced X, {2}{R} (601.2f), and taps all three."""
    scenario = Scenario(2)
    (blaze,) = scenario.hand(P0, ["Test Blaze"])
    mountains = scenario.battlefield(P0, ["Mountain", "Mountain", "Mountain"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(blaze, P0), choose_x(2), choose_targets(PlayerOption(P1)))
    autopay(state)
    (cast_event,) = records(state, SpellCast)
    assert cast_event.total_cost.text == "{2}{R}"
    assert all(state.objects[m].tapped for m in mountains)


def test_601_2f_the_auto_payer_pays_the_reduced_total() -> None:
    """Grizzly Bears with Emerald Medallion, from a Forest and a Plains: the payment under way
    is the reduced total {G} (601.2f), so the auto-payer taps only the Forest."""
    scenario = Scenario(2)
    (bears,) = scenario.hand(P0, ["Grizzly Bears"])
    _, forest, plains = scenario.battlefield(P0, ["Emerald Medallion", "Forest", "Plains"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(bears, P0))
    autopay(state)
    (cast_event,) = records(state, SpellCast)
    assert cast_event.total_cost.text == "{G}"
    assert tapped(state, [forest, plains]) == [True, False]
