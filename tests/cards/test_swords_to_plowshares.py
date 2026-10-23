"""Swords to Plowshares: {W}, Instant. "Exile target creature. Its controller gains life equal to
its power."

Oracle text and ruling checked against the Scryfall snapshot of 2026-10-22
(``tools/excerpts/cards.json``). The ruling (2022-12-08): "Use the power of the creature from when
it was last on the battlefield to determine how much life is gained."

From the pinned CR: the target is chosen as it is cast (601.2c) and checked again as it resolves
(608.2b); the instructions are followed in order (608.2c), so the creature is already in exile
when its controller gains life, and "its controller" and "its power" are its last known
information from the battlefield (608.2h). Exiling moves it to exile as a new object (701.13a,
400.7). Gaining 0 life is no life gain event (119.10).
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from resolve.cards.definitions.removal import SWORDS_TO_PLOWSHARES
from resolve.cards.registry import default_registry
from resolve.data.cards import load_card_excerpt
from resolve.decisions.spaces import CastSpellOption
from resolve.effects.characteristics import Characteristics
from resolve.events.life import LifeGained
from resolve.events.permanents import ObjectExiled
from resolve.state import last_known
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import ManaType
from resolve.state.spell import TargetObject
from resolve.state.turn import Phase, Step
from resolve.state.zones import EXILE, ZoneKind
from tests.casting_support import cast, choose_targets, options, pass_, records
from tests.scenario import Scenario, names, run_script

P0, P1 = PlayerId(0), PlayerId(1)
W = ManaType.WHITE
EXCERPT = Path(__file__).resolve().parents[2] / "tools" / "excerpts" / "cards.json"
ORACLE = "Exile target creature. Its controller gains life equal to its power."


def test_its_definition_is_its_oracle_text() -> None:
    assert default_registry().get("Swords to Plowshares") is SWORDS_TO_PLOWSHARES
    assert SWORDS_TO_PLOWSHARES.abilities == ()
    assert SWORDS_TO_PLOWSHARES.spell is not None
    assert SWORDS_TO_PLOWSHARES.spell.text == ORACLE
    card = load_card_excerpt(EXCERPT).get("Swords to Plowshares")
    assert card.faces[0].oracle_text == ORACLE
    assert (card.faces[0].mana_cost, card.type_line) == ("{W}", "Instant")


def swords_on(target: str, *, controller: PlayerId = P1, owner: PlayerId | None = None,
              damage: int = 0) -> tuple[Scenario, ObjectId, ObjectId]:  # fmt: skip
    """P0's Swords to Plowshares on the stack, targeting a creature ``controller`` controls."""
    scenario = Scenario(2)
    (spell,) = scenario.stack(P0, ["Swords to Plowshares"])
    (creature,) = scenario.battlefield(controller, [target], owner=owner)
    if damage:
        scenario.damage(creature, damage)
    scenario.targets(spell, [TargetObject(creature)])
    scenario.at(Phase.PRECOMBAT_MAIN)
    return scenario, spell, creature


def test_608_2h_swords_uses_last_known_power() -> None:
    """A Hill Giant (3/3) with 2 damage marked on it: damage doesn't change power (120.3e), so its
    controller gains 3, its power as it last existed on the battlefield (the ruling)."""
    scenario, _, giant = swords_on("Hill Giant", damage=2)
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1))
    (gained,) = records(state, LifeGained)
    assert (gained.player, gained.amount) == (P1, 3)
    assert state.player(P1).life == 23 and state.player(P0).life == 20
    assert giant not in state.objects


def test_608_2h_its_controller_gains_the_life() -> None:
    """An opponent's creature: the opponent gains the life; one's own: oneself."""
    scenario, _, _ = swords_on("Grizzly Bears", controller=P1)
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1))
    assert (state.player(P0).life, state.player(P1).life) == (20, 22)

    scenario, _, _ = swords_on("Grizzly Bears", controller=P0)
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1))
    assert (state.player(P0).life, state.player(P1).life) == (22, 20)


def test_608_2h_its_controller_is_read_from_last_known_information() -> None:
    """P1 controls Grizzly Bears that P0 owns. In exile the card has no controller (and its owner
    is P0), so "its controller" is P1, the controller it had on the battlefield (608.2h)."""
    scenario, _, bears = swords_on("Grizzly Bears", controller=P1, owner=P0)
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1))
    assert (state.player(P0).life, state.player(P1).life) == (20, 22)
    (exiled,) = state.exile
    assert state.objects[exiled].controller is None and state.objects[exiled].owner == P0
    assert bears not in state.objects


def test_119_10_gaining_zero_life_is_no_event() -> None:
    """Test Wall (0/4) is exiled; its controller would gain 0 life, which is no life gain event
    at all (119.10)."""
    scenario, _, wall = swords_on("Test Wall")
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1))
    assert records(state, LifeGained) == []
    assert state.player(P1).life == 20 and names(state, EXILE) == ["Test Wall"]
    assert wall not in state.objects


def test_701_13a_exile_moves_to_exile_as_a_new_object() -> None:
    scenario, spell, bears = swords_on("Grizzly Bears")
    card = scenario.card_of(bears)
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1))
    (exiled,) = records(state, ObjectExiled)
    assert exiled.obj == bears and exiled.rules[0] == "701.13a"
    assert state.exile == [exiled.moved] and bears not in state.objects
    new = state.objects[state.exile[0]]
    assert new.card == card and new.zone.kind is ZoneKind.EXILE and new.damage == 0
    assert state.battlefield == [] and spell not in state.objects


def test_304_1_it_is_an_instant_cast_in_an_opponents_turn() -> None:
    """An instant can be cast whenever its controller has priority (117.1a): here in P1's
    upkeep, choosing between two creatures."""
    scenario = Scenario(2)
    (swords,) = scenario.hand(P0, ["Swords to Plowshares"])
    (bears,) = scenario.battlefield(P0, ["Grizzly Bears"])
    (lions,) = scenario.battlefield(P1, ["Savannah Lions"])
    scenario.mana(P0, W)
    scenario.at(Step.UPKEEP, active=P1, priority=P0, passed=[P1])
    state = scenario.build()
    assert any(isinstance(o, CastSpellOption) and o.object == swords for o in options(state))
    run_script(state, cast(swords, P0), choose_targets(lions), pass_(P0), pass_(P1))
    assert names(state, EXILE) == ["Savannah Lions"] and bears in state.battlefield
    assert state.player(P1).life == 22


def test_608_2c_the_creature_is_exiled_before_the_life_is_gained() -> None:
    """The instructions are followed in the order written (608.2c): the exile is logged before
    the life gain."""
    scenario, _, _ = swords_on("Grizzly Bears")
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1))
    order = [
        type(e.record) for e in state.event_log if isinstance(e.record, ObjectExiled | LifeGained)
    ]
    assert order == [ObjectExiled, LifeGained]


def test_608_2h_the_power_is_the_creatures_on_the_battlefield_not_the_exiled_cards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stand-in for an effect that changes power (M5): while on the battlefield the Hill Giant's
    power reads 5; the exiled card's is its printed 3. Its controller gains 5, the power it had
    as it last existed on the battlefield (the ruling; 608.2h)."""
    original = last_known.characteristics

    def pumped(state: GameState, obj: ObjectId) -> Characteristics:
        chars = original(state, obj)
        on_battlefield = state.objects[obj].zone.kind is ZoneKind.BATTLEFIELD
        if on_battlefield and chars.name == "Hill Giant":
            return replace(chars, power_text="5")
        return chars

    monkeypatch.setattr(last_known, "characteristics", pumped)
    scenario, _, _ = swords_on("Hill Giant")
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1))
    (gained,) = records(state, LifeGained)
    assert (gained.player, gained.amount) == (P1, 5)
    (exiled,) = state.exile
    assert original(state, exiled).power == 3
