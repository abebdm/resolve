"""Temple of the False God: Land. "{T}: Add {C}{C}. Activate only if you control five or more
lands."

Oracle text checked against the Scryfall snapshot of 2026-10-21 (``tools/excerpts/cards.json``),
which has no rulings for it.

From the pinned CR:

- 602.5: a player can't begin to activate an ability that's prohibited from being activated; the
  condition is checked as the player would begin (602.2), with priority or while paying (605.3a).
- "You" is the ability's controller (602.2); lands they control count, the Temple included;
  opponents' lands don't. A land creature is a land (305.9); a nonland permanent isn't.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from resolve.cards.definitions.nonbasic_lands import TEMPLE_OF_THE_FALSE_GOD
from resolve.cards.primitives.abilities import ActivatedManaAbility
from resolve.cards.primitives.conditions import ControlsAtLeast
from resolve.cards.registry import default_registry
from resolve.data.cards import load_card_excerpt
from resolve.data.types import CardType
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import ActivateAbilityOption
from resolve.events.spells import SpellCast
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import Mana, ManaType
from resolve.state.turn import Phase
from tests.casting_support import activate, activate_with_priority, cast, options, pay, records
from tests.game_fixtures import request_of
from tests.scenario import Scenario, run_script

P0, P1 = PlayerId(0), PlayerId(1)
C = ManaType.COLORLESS
EXCERPT = Path(__file__).resolve().parents[2] / "tools" / "excerpts" / "cards.json"
TEXT = "{T}: Add {C}{C}. Activate only if you control five or more lands."


def temple_with(mine: Sequence[str], theirs: Sequence[str] = ()) -> tuple[GameState, ObjectId]:
    scenario = Scenario(2)
    (temple,) = scenario.battlefield(P0, ["Temple of the False God"])
    scenario.battlefield(P0, list(mine))
    scenario.battlefield(P1, list(theirs))
    scenario.at(Phase.PRECOMBAT_MAIN)
    return scenario.build(), temple


def test_its_definition_is_its_oracle_text() -> None:
    assert default_registry().get("Temple of the False God") is TEMPLE_OF_THE_FALSE_GOD
    (ability,) = TEMPLE_OF_THE_FALSE_GOD.abilities
    assert ability.text == TEXT
    assert isinstance(ability, ActivatedManaAbility)
    assert ability.activate_only_if == ControlsAtLeast(5, CardType.LAND)
    assert load_card_excerpt(EXCERPT).get("Temple of the False God").faces[0].oracle_text == TEXT


def test_602_5_temple_needs_five_lands() -> None:
    """With three Forests P0 controls four lands, counting the Temple: not offered. With four
    Forests, five: offered, and it adds {C}{C}."""
    state, temple = temple_with(["Forest"] * 3)
    assert ActivateAbilityOption(temple, 0) not in options(state)
    state, temple = temple_with(["Forest"] * 4)
    assert ActivateAbilityOption(temple, 0) in options(state)
    run_script(state, activate_with_priority(temple))
    assert state.player(P0).mana_pool == [Mana(C, temple), Mana(C, temple)]


def test_602_5_opponents_lands_dont_count() -> None:
    state, temple = temple_with(["Forest"] * 3, ["Forest"] * 5)
    assert ActivateAbilityOption(temple, 0) not in options(state)


def test_602_5_only_lands_count_and_land_creatures_are_lands() -> None:
    """Three Forests and a Sol Ring: four lands. Three Forests and Test Land Creature: five."""
    state, temple = temple_with(["Forest", "Forest", "Forest", "Sol Ring"])
    assert ActivateAbilityOption(temple, 0) not in options(state)
    state, temple = temple_with(["Forest", "Forest", "Forest", "Test Land Creature"])
    assert ActivateAbilityOption(temple, 0) in options(state)


def test_602_5_the_condition_applies_while_paying_too() -> None:
    """Paying for Grizzly Bears with four lands: the Forests are offered, the Temple isn't."""
    scenario = Scenario(2)
    (bears,) = scenario.hand(P0, ["Grizzly Bears"])
    (temple,) = scenario.battlefield(P0, ["Temple of the False God"])
    forests = scenario.battlefield(P0, ["Forest"] * 3)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(bears, P0))
    assert request_of(state).kind is DecisionKind.ACTIVATE_MANA_ABILITIES
    assert ActivateAbilityOption(temple, 0) not in options(state)
    assert all(ActivateAbilityOption(f, 0) in options(state) for f in forests)
    run_script(state, activate(forests[0]), activate(forests[1]), pay())
    assert len(records(state, SpellCast)) == 1
