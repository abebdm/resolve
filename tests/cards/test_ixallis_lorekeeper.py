"""Ixalli's Lorekeeper: {G}, Creature — Human Druid 1/1. "{T}: Add one mana of any color. Spend
this mana only to cast a Dinosaur spell or activate an ability of a Dinosaur source."

Oracle text and ruling checked against the Scryfall snapshot of 2026-10-21
(``tools/excerpts/cards.json``). The ruling: a "Dinosaur source" is any object with the creature
type Dinosaur, so the mana can activate an ability of a Dinosaur you control or of a Dinosaur card
in your hand or graveyard.

From the pinned CR:

- 106.6: some abilities restrict how their mana can be spent; that doesn't change its type.
- 601.2h: a cost is paid only with mana that may be spent on it, so a payment needing the
  restricted mana for anything else can't be made (118.3), and the action is reversed (733.1).
- 500.5, 106.4: restricted mana empties from the pool like any other.
- 302.6: it is a creature, so its {T} ability has summoning sickness (``test_302_6_*``).
- 106.1a, 605.3b: the color is chosen as it resolves, from all five colors.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from resolve.cards.definitions.mana_creatures import IXALLIS_LOREKEEPER
from resolve.cards.primitives.restrictions import SpendOnlyOnSubtype
from resolve.cards.primitives.words import SubtypeWord
from resolve.cards.registry import default_registry
from resolve.data.cards import load_card_excerpt
from resolve.data.types import Color
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import Amounts, ChooseCounts, ChooseOne, ColorOption, ManaOption
from resolve.engine.api import submit
from resolve.errors import InvalidAnswer
from resolve.events.mana import ManaPoolEmptied
from resolve.events.spells import ActionReversed, SpellCast
from resolve.state.ids import PlayerId
from resolve.state.mana import ForAbility, ForSpell, Mana, ManaType
from resolve.state.turn import Phase, Step
from tests.casting_support import (
    activate,
    activate_with_priority,
    answered,
    cast,
    choose_color,
    pass_,
    records,
    reverse,
)
from tests.game_fixtures import answer, request_of
from tests.scenario import Scenario, run_script

P0, P1 = PlayerId(0), PlayerId(1)
G, R = ManaType.GREEN, ManaType.RED
DINOSAUR = SpendOnlyOnSubtype(SubtypeWord("Dinosaur"))
EXCERPT = Path(__file__).resolve().parents[2] / "tools" / "excerpts" / "cards.json"
TEXT = (
    "{T}: Add one mana of any color. Spend this mana only to cast a Dinosaur spell or activate an "
    "ability of a Dinosaur source."
)


def test_its_definition_is_its_oracle_text() -> None:
    assert default_registry().get("Ixalli's Lorekeeper") is IXALLIS_LOREKEEPER
    (ability,) = IXALLIS_LOREKEEPER.abilities
    assert ability.text == TEXT
    card = load_card_excerpt(EXCERPT).get("Ixalli's Lorekeeper")
    assert card.faces[0].oracle_text == TEXT


def test_106_1a_it_adds_one_mana_of_the_chosen_color_with_its_restriction() -> None:
    scenario = Scenario(2)
    (lorekeeper,) = scenario.battlefield(P0, ["Ixalli's Lorekeeper"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, activate_with_priority(lorekeeper))
    request = request_of(state)
    assert request.kind is DecisionKind.CHOOSE_COLOR
    assert request.space == ChooseOne(tuple(ColorOption(color) for color in Color))
    run_script(state, choose_color(Color.BLACK))
    assert state.player(P0).mana_pool == [Mana(ManaType.BLACK, lorekeeper, DINOSAUR)]


def test_106_6_lorekeeper_mana_pays_for_a_dinosaur_spell() -> None:
    """Test Raptor ({1}{G}, a Dinosaur): the Lorekeeper's {R} pays {1}, the Forest's {G} pays
    {G}."""
    scenario = Scenario(2)
    (raptor,) = scenario.hand(P0, ["Test Raptor"])
    lorekeeper, forest = scenario.battlefield(P0, ["Ixalli's Lorekeeper", "Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(raptor, P0), activate(lorekeeper), choose_color(Color.RED))
    run_script(state, activate(forest))
    (cast_event,) = records(state, SpellCast)
    assert sorted(cast_event.mana_spent, key=repr) == sorted(
        (Mana(R, lorekeeper, DINOSAUR), Mana(G, forest)), key=repr
    )


def test_106_6_lorekeeper_mana_cant_pay_for_other_spells() -> None:
    """Grizzly Bears ({1}{G}) is no Dinosaur: with only the Forest's {G} usable, {1}{G} can't be
    paid, and the cast is reversed (733.1)."""
    scenario = Scenario(2)
    (bears,) = scenario.hand(P0, ["Grizzly Bears"])
    lorekeeper, forest = scenario.battlefield(P0, ["Ixalli's Lorekeeper", "Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(bears, P0), activate(lorekeeper), choose_color(Color.GREEN))
    run_script(state, activate(forest))
    assert request_of(state).kind is DecisionKind.REVERSE_MANA_ABILITIES
    assert records(state, SpellCast) == []


def test_106_6_a_payment_spending_restricted_mana_on_another_spell_is_rejected() -> None:
    """Two Forests and a Plains pay Grizzly Bears three ways, so P0 is asked; the Lorekeeper's
    {G} is listed with a maximum of 0, and an answer spending it is refused."""
    scenario = Scenario(2)
    (bears,) = scenario.hand(P0, ["Grizzly Bears"])
    lorekeeper, first, second, plains = scenario.battlefield(
        P0, ["Ixalli's Lorekeeper", "Forest", "Forest", "Plains"]
    )
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(bears, P0), activate(lorekeeper), choose_color(Color.GREEN))
    run_script(state, activate(first), activate(second), activate(plains))
    request = request_of(state)
    assert request.kind is DecisionKind.PAY_COSTS
    assert request.space == ChooseCounts(
        (
            ManaOption(Mana(G, lorekeeper, DINOSAUR)),
            ManaOption(Mana(G, first)),
            ManaOption(Mana(G, second)),
            ManaOption(Mana(ManaType.WHITE, plains)),
        ),
        (0, 1, 1, 1),
        2,
    )
    with pytest.raises(InvalidAnswer):
        submit(state, answer(state, Amounts((1, 1, 0, 0))))
    submit(state, answer(state, Amounts((0, 1, 0, 1))))
    (cast_event,) = records(state, SpellCast)
    assert cast_event.mana_spent == (Mana(G, first), Mana(ManaType.WHITE, plains))
    assert Mana(G, lorekeeper, DINOSAUR) in state.player(P0).mana_pool


def test_106_6_lorekeeper_mana_cant_pay_a_non_dinosaurs_ability() -> None:
    """Selesnya Signet's {1} (an artifact, no Dinosaur): the Lorekeeper's mana can't pay it, so the
    Signet's activation is reversed (733.1). P0 keeps the Lorekeeper's ability: it stays tapped
    and its mana stays, still restricted; the Signet is untapped."""
    scenario = Scenario(2)
    signet, lorekeeper = scenario.battlefield(P0, ["Selesnya Signet", "Ixalli's Lorekeeper"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, activate_with_priority(signet), activate(lorekeeper), choose_color(Color.RED))
    assert request_of(state).kind is DecisionKind.REVERSE_MANA_ABILITIES
    run_script(state, reverse())
    assert not state.objects[signet].tapped and state.objects[lorekeeper].tapped
    assert state.player(P0).mana_pool == [Mana(R, lorekeeper, DINOSAUR)]
    (reversed_,) = records(state, ActionReversed)
    assert reversed_.kept == (lorekeeper,)
    assert answered(state, DecisionKind.PAY_COSTS) == 0


def test_106_6_a_dinosaur_source_is_any_object_with_that_type() -> None:
    """The ruling: a Dinosaur on the battlefield or a Dinosaur card in a hand is a Dinosaur source;
    a Dinosaur spell is a spell with the type; Grizzly Bears and Selesnya Signet aren't."""
    scenario = Scenario(2)
    raptor, bears, signet = scenario.battlefield(
        P0, ["Test Raptor", "Grizzly Bears", "Selesnya Signet"]
    )
    (in_hand,) = scenario.hand(P0, ["Test Raptor"])
    (spell,) = scenario.stack(P0, ["Test Raptor"])
    state = scenario.build()
    assert DINOSAUR.allows(state, ForAbility(raptor, 0))
    assert DINOSAUR.allows(state, ForAbility(in_hand, 0))
    assert DINOSAUR.allows(state, ForSpell(spell))
    assert not DINOSAUR.allows(state, ForAbility(bears, 0))
    assert not DINOSAUR.allows(state, ForAbility(signet, 0))


def test_500_5_restricted_mana_empties_like_any_other() -> None:
    scenario = Scenario(2)
    (lorekeeper,) = scenario.battlefield(P0, ["Ixalli's Lorekeeper"])
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    run_script(state, activate_with_priority(lorekeeper), choose_color(Color.WHITE))
    run_script(state, pass_(P0), pass_(P1))
    emptied = records(state, ManaPoolEmptied)
    assert [e.mana for e in emptied] == [(Mana(ManaType.WHITE, lorekeeper, DINOSAUR),)]
    assert state.player(P0).mana_pool == []
