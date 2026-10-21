"""Sol Ring: {1}, Artifact. "{T}: Add {C}{C}."

Oracle text checked against the Scryfall snapshot of 2026-10-21 (``tools/excerpts/cards.json``).
Its rulings (2004-10-04 onward) are about its legality and about colorless mana not being a
color, which these tests cover: {C} pays generic mana (107.4b), never a colored symbol (107.4a).

From the pinned CR: an artifact spell is cast with sorcery timing (301.1, 117.1a); 302.6
(summoning sickness) applies only to creatures, so Sol Ring can tap the turn it enters (605.3a).
"""

from __future__ import annotations

from pathlib import Path

from resolve.cards.definitions.mana_rocks import SOL_RING
from resolve.cards.registry import default_registry
from resolve.data.cards import load_card_excerpt
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import ActivateAbilityOption, CastSpellOption
from resolve.events.spells import SpellCast
from resolve.state.ids import PlayerId
from resolve.state.mana import Mana, ManaType
from resolve.state.spell import FROM_HAND, NORMAL
from resolve.state.turn import Phase, Step
from tests.casting_support import (
    activate,
    activate_with_priority,
    answered,
    cast,
    options,
    pass_,
    records,
)
from tests.game_fixtures import request_of
from tests.scenario import Scenario, run_script

P0, P1 = PlayerId(0), PlayerId(1)
C = ManaType.COLORLESS
EXCERPT = Path(__file__).resolve().parents[2] / "tools" / "excerpts" / "cards.json"


def test_its_definition_is_its_oracle_text() -> None:
    assert default_registry().get("Sol Ring") is SOL_RING
    (ability,) = SOL_RING.abilities
    assert ability.text == "{T}: Add {C}{C}."
    card = load_card_excerpt(EXCERPT).get("Sol Ring")
    assert card.faces[0].oracle_text == "{T}: Add {C}{C}."
    assert card.faces[0].mana_cost == "{1}"


def test_301_1_it_is_cast_with_sorcery_timing_for_1() -> None:
    upkeep = Scenario(2)
    upkeep.hand(P0, ["Sol Ring"])
    upkeep.battlefield(P0, ["Forest"])
    upkeep.at(Step.UPKEEP)
    assert not any(isinstance(o, CastSpellOption) for o in options(upkeep.build()))

    scenario = Scenario(2)
    (ring,) = scenario.hand(P0, ["Sol Ring"])
    (forest,) = scenario.battlefield(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    assert CastSpellOption(ring, NORMAL, FROM_HAND) in options(state)
    run_script(state, cast(ring, P0), activate(forest))
    (cast_event,) = records(state, SpellCast)
    assert cast_event.total_cost.text == "{1}"
    assert cast_event.mana_spent == (Mana(ManaType.GREEN, forest),)


def test_302_6_it_taps_for_mana_the_turn_it_enters() -> None:
    scenario = Scenario(2)
    (ring,) = scenario.hand(P0, ["Sol Ring"])
    (forest,) = scenario.battlefield(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(ring, P0), activate(forest), pass_(P0), pass_(P1))
    (permanent,) = [o for o in state.battlefield if o != forest]
    assert ActivateAbilityOption(permanent, 0) in options(state)
    run_script(state, activate_with_priority(permanent))
    assert state.player(P0).mana_pool == [Mana(C, permanent), Mana(C, permanent)]


def test_107_4b_sol_ring_a_mountain_and_a_forest_pay_hill_giant_without_a_question() -> None:
    """{C}{C}{R}{G} pays {3}{R} one way only: {R} for {R}, the rest for {3}."""
    scenario = Scenario(2)
    (giant,) = scenario.hand(P0, ["Hill Giant"])
    ring, mountain, forest = scenario.battlefield(P0, ["Sol Ring", "Mountain", "Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(giant, P0), activate(ring), activate(mountain), activate(forest))
    assert answered(state, DecisionKind.PAY_COSTS) == 0
    assert len(records(state, SpellCast)) == 1 and state.player(P0).mana_pool == []
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION


def test_107_4a_colorless_mana_cant_pay_a_colored_symbol() -> None:
    """Sol Ring alone can't pay Savannah Lions' {W}: the cast is reversed (733.1)."""
    scenario = Scenario(2)
    (lions,) = scenario.hand(P0, ["Savannah Lions"])
    (ring,) = scenario.battlefield(P0, ["Sol Ring"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(lions, P0), activate(ring))
    assert request_of(state).kind is DecisionKind.REVERSE_MANA_ABILITIES
