"""The caster (``resolve.agents.caster``): a fuzz seat that casts what it can.

Random seats seldom cast anything worth casting: they pass, tap lands for nothing and try spells
they can't pay for, so a fuzz run rarely reaches the expensive or instant-speed spells
(docs/decisions.md, 2026-10-28, "M2.11"). The caster plays a land when it may (305.1, 116.2a),
then casts each offered spell (117.1a, 601.2) it hasn't tried yet in this priority window, then
passes (117.3d); it casts during a resolution when an effect allows it (608.2g); it keeps X
small, and answers everything else at random. It pays with the auto-payer around it
(``AutoPayAgent(CasterAgent(seed))``), so a spell it can't pay for is reversed (733.1); it then
doesn't try that spell again until the window changes.

It sees only the view and the request (rule 4), and its answers are a function of its seed and
what it was shown.
"""

from __future__ import annotations

from resolve.agents.autopay import AutoPayAgent
from resolve.agents.caster import CASTER_UNBOUNDED_SPAN, CasterAgent
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.request import DecisionRequest
from resolve.decisions.spaces import (
    CastSpellOption,
    ChooseNumber,
    ChooseOne,
    Number,
    PassOption,
    Pick,
    PlayLandOption,
)
from resolve.engine.api import submit, view_for
from resolve.engine.casting import DECLINE
from resolve.events.spells import ActionReversed, SpellCast
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.turn import Phase
from tests.casting_support import pass_, records
from tests.game_fixtures import request_of
from tests.scenario import Scenario, run_script

P0, P1 = PlayerId(0), PlayerId(1)
SEEDS = range(20)


def main_phase(hand: list[str], lands: list[str]) -> tuple[GameState, list[ObjectId]]:
    """P0's precombat main phase, P0 holding ``hand`` with ``lands`` on the battlefield."""
    scenario = Scenario(2)
    held = scenario.hand(P0, hand)
    scenario.battlefield(P0, lands)
    scenario.at(Phase.PRECOMBAT_MAIN)
    return scenario.build(), held


def chosen(state: GameState, agent: CasterAgent | AutoPayAgent) -> object:
    """The option ``agent`` picks for the pending one-of-many decision."""
    request = request_of(state)
    assert isinstance(request.space, ChooseOne)
    answer = agent.decide(view_for(state, request.player), request)
    assert isinstance(answer.value, Pick)
    return request.space.options[answer.value.index]


def test_it_plays_a_land_first() -> None:
    """With a land and a castable spell in hand, it plays the land (305.1): more mana first."""
    for seed in SEEDS:
        state, (forest, _) = main_phase(["Forest", "Sol Ring"], ["Forest"])
        assert chosen(state, CasterAgent(seed)) == PlayLandOption(forest)


def test_it_casts_an_offered_spell_rather_than_passing() -> None:
    """With priority and spells to cast (117.1a), it casts one of them, never passes or taps a
    land for mana on its own (the auto-payer does that while paying, 601.2g)."""
    for seed in SEEDS:
        state, (ring, relic) = main_phase(["Sol Ring", "Darksteel Relic"], ["Forest"])
        option = chosen(state, CasterAgent(seed))
        assert isinstance(option, CastSpellOption) and option.object in (ring, relic)


def test_with_the_auto_payer_it_casts_and_pays() -> None:
    """Around the auto-payer, the cast completes: Sol Ring ({1}) paid with the Forest."""
    state, _ = main_phase(["Sol Ring"], ["Forest"])
    agent = AutoPayAgent(CasterAgent(0))
    while not records(state, SpellCast):
        request = request_of(state)
        submit(state, agent.decide(view_for(state, request.player), request))
    assert [record.name for record in records(state, SpellCast)] == ["Sol Ring"]
    assert records(state, ActionReversed) == []


def test_a_reversed_spell_isnt_tried_again_in_the_same_window() -> None:
    """Grizzly Bears ({1}{G}) with one Forest can't be paid (107.4b): the auto-payer answers
    "pay" and the cast is reversed (118.3, 733.1). Back at the same priority, with nothing
    changed, the caster passes instead of trying the Bears again."""
    state, _ = main_phase(["Grizzly Bears"], ["Forest"])
    agent = AutoPayAgent(CasterAgent(0))
    while not records(state, ActionReversed):
        request = request_of(state)
        submit(state, agent.decide(view_for(state, request.player), request))
    assert records(state, SpellCast) == []
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION
    assert chosen(state, agent) == PassOption()


def test_it_tries_again_once_the_window_changes() -> None:
    """The window is the turn, step, stack and the player's untapped permanents and mana pool:
    after the Bears were reversed with one Forest, a board with a second untapped Forest is a
    new window, and the caster tries the Bears again."""
    agent = CasterAgent(0)
    state, (bears,) = main_phase(["Grizzly Bears"], ["Forest"])
    assert chosen(state, agent) == chosen_cast(state, bears)
    assert chosen(state, agent) == PassOption()
    state, (bears,) = main_phase(["Grizzly Bears"], ["Forest", "Forest"])
    assert chosen(state, agent) == chosen_cast(state, bears)


def chosen_cast(state: GameState, obj: ObjectId) -> CastSpellOption:
    """The priority option casting ``obj``."""
    request = request_of(state)
    assert isinstance(request.space, ChooseOne)
    (option,) = [
        option
        for option in request.space.options
        if isinstance(option, CastSpellOption) and option.object == obj
    ]
    return option


def test_it_passes_when_nothing_is_left_to_cast() -> None:
    """With only a Forest on the battlefield and nothing in hand, it passes (117.3d) rather than
    activating the Forest's mana ability (605.3a) for nothing."""
    for seed in SEEDS:
        state, _ = main_phase([], ["Forest"])
        assert chosen(state, CasterAgent(seed)) == PassOption()


def test_it_casts_during_a_resolution_rather_than_declining() -> None:
    """Rishkar's Expertise resolving lets P0 cast Grizzly Bears without paying its mana cost
    (608.2g, 118.9): the caster casts it instead of declining."""
    for seed in SEEDS:
        scenario = Scenario(2)
        scenario.stack(P0, ["Rishkar's Expertise"])
        (bears,) = scenario.hand(P0, ["Grizzly Bears"])
        scenario.library(P0, ["Forest"] * 5)
        scenario.at(Phase.PRECOMBAT_MAIN)
        state = scenario.build()
        run_script(state, pass_(P0), pass_(P1))
        assert request_of(state).kind is DecisionKind.CAST_DURING_RESOLUTION
        option = chosen(state, CasterAgent(seed))
        assert option != DECLINE
        assert isinstance(option, CastSpellOption) and option.object == bears


def test_it_announces_a_small_x() -> None:
    """X has no upper bound (107.3a); the caster picks it from 0 to ``CASTER_UNBOUNDED_SPAN``, a
    value the fuzz decks' mana can pay, never more."""
    request = DecisionRequest(
        1, P0, P0, DecisionKind.CHOOSE_X, ChooseNumber(0, None), "X?", ("107.3a",)
    )
    state, _ = main_phase([], [])
    view = view_for(state, P0)
    values: set[int] = set()
    for seed in SEEDS:
        answer = CasterAgent(seed).decide(view, request)
        assert isinstance(answer.value, Number)
        values.add(answer.value.value)
    assert values == set(range(CASTER_UNBOUNDED_SPAN + 1))


def test_the_same_seed_gives_the_same_answers() -> None:
    """Reproducible: two casters with one seed answer the same views the same way."""
    state, _ = main_phase(["Sol Ring", "Darksteel Relic", "Grizzly Bears"], ["Forest"])
    first, second = CasterAgent(7), CasterAgent(7)
    for _ in range(3):
        assert chosen(state, first) == chosen(state, second)
