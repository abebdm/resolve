"""The events of M2.6: ``DamageDealt`` (120), ``LifeGained`` (119.3), ``ObjectExiled``
(701.13a), ``BecameTargets`` (601.2c), ``SpellDidNotResolve`` (608.2b) and ``SpellResolved``
(608.2n, 608.2m): the change each makes, what each refuses, and that each is public."""

from __future__ import annotations

import pytest

from resolve.cards.registry import CardDefinition, CardRegistry
from resolve.data.cards import CardDatabase, parse_oracle_cards
from resolve.engine.loop import run
from resolve.errors import EngineError, NotImplementedRule
from resolve.events.base import Event
from resolve.events.damage import DamageDealt
from resolve.events.life import LifeGained
from resolve.events.permanents import ObjectExiled
from resolve.events.pipeline import ApplyEvents
from resolve.events.spells import BecameTargets, SpellDidNotResolve, SpellResolved
from resolve.state.game import GameState, move_object
from resolve.state.ids import PlayerId
from resolve.state.spell import TargetObject, TargetPlayer
from resolve.state.zones import EXILE, Zone
from tests import scryfall_fixtures as fx
from tests.engine_support import Hold
from tests.game_fixtures import scenario_database, scenario_registry
from tests.scenario import Scenario, names

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)


def apply(state: GameState, event: Event) -> Event:
    """Apply ``event`` through the pipeline (over a ``Hold``, which then pauses the game); the
    logged record, checked to be public."""
    state.pending = None
    state.tasks = [Hold(), ApplyEvents((event,))]
    run(state)
    entry = state.event_log[-1]
    assert entry.visible_to is None  # public
    record = entry.record
    assert isinstance(record, Event)
    return record


def test_120_3_damage_marks_creatures_and_takes_life() -> None:
    scenario = Scenario(3)
    (shock,) = scenario.stack(P0, ["Test Shock"])
    (bears,) = scenario.battlefield(P1, ["Grizzly Bears"])
    scenario.damage(bears, 1)
    state = scenario.build()
    apply(
        state,
        DamageDealt(source=shock, to_objects=((bears, 2),), to_players=((P2, 3),), rules=("120.3",)),
    )
    assert state.objects[bears].damage == 3 and state.player(P2).life == 17
    assert state.player(P1).life == 20


def test_120_3_a_source_that_left_still_deals_damage() -> None:
    """113.7a, 608.2h: the source's last known information is used."""
    scenario = Scenario(2)
    (giant,) = scenario.battlefield(P0, ["Hill Giant"])
    state = scenario.build()
    move_object(state, giant, Zone.graveyard(P0))
    apply(state, DamageDealt(source=giant, to_players=((P1, 3),), rules=("120.3",)))
    assert state.player(P1).life == 17


def test_damage_refuses_impossible_events() -> None:
    scenario = Scenario(2)
    (shock,) = scenario.stack(P0, ["Test Shock"])
    (ring,) = scenario.battlefield(P1, ["Sol Ring"])
    (card,) = scenario.hand(P1, ["Grizzly Bears"])
    state = scenario.build()
    bad = [
        DamageDealt(source=shock, rules=("120.3",)),  # no recipient
        DamageDealt(source=shock, to_players=((P1, 0),), rules=("120.8",)),
        DamageDealt(source=shock, to_objects=((ring, 1),), rules=("120.1a",)),
        DamageDealt(source=shock, to_objects=((card, 1),), rules=("120.1a",)),
        DamageDealt(source=shock + 100, to_players=((P1, 1),), rules=("120.3",)),
    ]
    for event in bad:
        with pytest.raises(EngineError):
            event.apply(state)
    state.player(P1).left_game = True
    with pytest.raises(EngineError):
        DamageDealt(source=shock, to_players=((P1, 1),), rules=("120.3",)).apply(state)
    assert state.player(P1).life == 20


def test_120_3c_damage_to_a_planeswalker_is_a_gap_until_counters() -> None:
    walker = {**fx.spell("Test Walker", "{2}", 2.0, "Planeswalker — Test", []), "loyalty": "3"}
    database = CardDatabase([*scenario_database().cards(), *parse_oracle_cards([walker])])
    base = scenario_registry()
    registry = CardRegistry([*(base.get(n) for n in base.names()), CardDefinition("Test Walker")])
    scenario = Scenario(2, database=database, registry=registry)
    (shock,) = scenario.stack(P0, ["Test Shock"])
    (planeswalker,) = scenario.battlefield(P1, ["Test Walker"])
    state = scenario.build()
    with pytest.raises(NotImplementedRule) as gap:
        DamageDealt(source=shock, to_objects=((planeswalker, 1),), rules=("120.3",)).apply(state)
    assert gap.value.rule == "120.3c"


def test_119_3_life_gained() -> None:
    state = Scenario(2).build()
    apply(state, LifeGained(player=P1, amount=4, rules=("119.3",)))
    assert state.player(P1).life == 24
    with pytest.raises(EngineError):
        LifeGained(player=P1, amount=0, rules=("119.10",)).apply(state)
    state.player(P0).left_game = True
    with pytest.raises(EngineError):
        LifeGained(player=P0, amount=1, rules=("119.3",)).apply(state)


def test_701_13a_exiling_from_any_zone() -> None:
    scenario = Scenario(2)
    (bears,) = scenario.battlefield(P1, ["Grizzly Bears"])
    (dead,) = scenario.graveyard(P1, ["Savannah Lions"])
    (gone,) = scenario.exile(P1, ["Hill Giant"])
    state = scenario.build()
    record = apply(state, ObjectExiled(obj=bears, rules=("701.13a",)))
    assert isinstance(record, ObjectExiled) and record.moved in state.exile
    apply(state, ObjectExiled(obj=dead, rules=("701.13a",)))
    assert names(state, EXILE) == ["Hill Giant", "Grizzly Bears", "Savannah Lions"]
    with pytest.raises(EngineError):
        ObjectExiled(obj=gone, rules=("701.13a",)).apply(state)


def test_601_2c_targets_join_the_spells_record_once() -> None:
    scenario = Scenario(2)
    (spell,) = scenario.stack(P0, ["Test Shock"])
    (bears,) = scenario.battlefield(P1, ["Grizzly Bears"])
    state = scenario.build()
    event = BecameTargets(spell=spell, targets=((TargetObject(bears),),), rules=("601.2c",))
    apply(state, event)
    record = state.objects[spell].spell
    assert record is not None and record.targets == ((TargetObject(bears),),) and record.targeted
    with pytest.raises(EngineError):
        event.apply(state)  # already chosen
    with pytest.raises(EngineError):
        BecameTargets(spell=bears, targets=((TargetPlayer(P1),),), rules=("601.2c",)).apply(state)


def test_608_2b_a_spell_that_doesnt_resolve_goes_to_its_owners_graveyard() -> None:
    scenario = Scenario(3)
    (spell,) = scenario.stack(P0, ["Test Shock"], owner=P1)
    (bears,) = scenario.battlefield(P1, ["Grizzly Bears"])
    state = scenario.build()
    record = apply(state, SpellDidNotResolve(spell=spell, rules=("608.2b",)))
    assert isinstance(record, SpellDidNotResolve)
    assert state.player(P1).graveyard == [record.moved] and state.stack == []
    with pytest.raises(EngineError):
        SpellDidNotResolve(spell=bears, rules=("608.2b",)).apply(state)


def test_608_2n_608_2m_a_resolved_spell_moves_unless_it_already_left() -> None:
    scenario = Scenario(2)
    (spell,) = scenario.stack(P0, ["Test Shock"])
    state = scenario.build()
    with pytest.raises(EngineError):
        SpellResolved(spell=spell, destination=None, rules=("608.2m",)).apply(state)
    record = apply(state, SpellResolved(spell=spell, destination=EXILE, rules=("608.2n",)))
    assert isinstance(record, SpellResolved) and state.exile == [record.moved]
    # 608.2m: it left the stack while resolving; nothing moves.
    record = apply(state, SpellResolved(spell=spell, destination=None, rules=("608.2m",)))
    assert isinstance(record, SpellResolved) and record.moved is None
