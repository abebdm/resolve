"""Decimate: {2}{R}{G}, Sorcery. "Destroy target artifact, target creature, target enchantment,
and target land. (You can't cast this spell unless you have legal choices for all its targets.)"

A torture test (docs/torture-tests.md): four instances of the word "target", one object chosen
for several of them, no cast unless every instance has a legal target, and partial fizzling.

Oracle text and ruling checked against the Scryfall snapshot of 2026-10-22
(``tools/excerpts/cards.json``). The ruling (2022-12-08): "You must choose a legal target for each
target required by Decimate. However, if a permanent has multiple card types, it may be chosen as
the target for more than one instance of the word 'target.'"

From the pinned CR: 601.2c (each instance needs a legal target; the same object may be chosen once
for each instance), 608.2b (only the illegal targets are spared; the spell resolves while any
target is legal), 701.8a (destroying moves a permanent to its owner's graveyard; a permanent
chosen twice is still one permanent, destroyed once).
"""

from __future__ import annotations

from pathlib import Path

from resolve.cards.definitions.removal import DECIMATE
from resolve.cards.registry import default_registry
from resolve.data.cards import load_card_excerpt
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import CastSpellOption, ObjectOption
from resolve.events.base import AnswerRecord
from resolve.events.permanents import PermanentDestroyed
from resolve.events.spells import SpellDidNotResolve, SpellResolved
from resolve.state.ids import PlayerId
from resolve.state.mana import ManaType
from resolve.state.spell import TargetObject
from resolve.state.turn import Phase
from resolve.state.zones import Zone
from tests.casting_support import cast, choose_targets, options, pass_, records
from tests.rules.test_115_targets import target_options
from tests.scenario import Scenario, names, run_script

P0, P1 = PlayerId(0), PlayerId(1)
R, G, W = ManaType.RED, ManaType.GREEN, ManaType.WHITE
EXCERPT = Path(__file__).resolve().parents[2] / "tools" / "excerpts" / "cards.json"
TEXT = "Destroy target artifact, target creature, target enchantment, and target land."
REMINDER = " (You can't cast this spell unless you have legal choices for all its targets.)"


def test_its_definition_is_its_oracle_text() -> None:
    """The definition's text is the Oracle text without its reminder text, which 601.2c says."""
    assert default_registry().get("Decimate") is DECIMATE
    assert DECIMATE.spell is not None and DECIMATE.spell.text == TEXT
    card = load_card_excerpt(EXCERPT).get("Decimate")
    assert card.faces[0].oracle_text == TEXT + REMINDER
    assert (card.faces[0].mana_cost, card.type_line) == ("{2}{R}{G}", "Sorcery")


def offered(scenario: Scenario) -> bool:
    return any(isinstance(o, CastSpellOption) for o in options(scenario.build()))


def test_601_2c_decimate_needs_a_legal_target_for_every_instance() -> None:
    """With an artifact, a creature and a land but no enchantment, Decimate isn't offered; with
    Test Totem (an enchantment) as well, it is."""
    without = Scenario(2)
    without.hand(P0, ["Decimate"])
    without.battlefield(P1, ["Sol Ring", "Grizzly Bears", "Forest"])
    without.at(Phase.PRECOMBAT_MAIN)
    assert not offered(without)

    with_totem = Scenario(2)
    with_totem.hand(P0, ["Decimate"])
    with_totem.battlefield(P1, ["Sol Ring", "Grizzly Bears", "Forest", "Test Totem"])
    with_totem.at(Phase.PRECOMBAT_MAIN)
    assert offered(with_totem)


def test_601_2c_one_object_can_be_several_targets() -> None:
    """Test Artifact Land Creature is the only artifact, creature and land, and Test Totem the
    only enchantment: each instance has one legal choice, so nothing is asked, and the one
    object is the target of three instances (601.2c). On resolution both permanents are
    destroyed, the shared one once."""
    scenario = Scenario(2)
    (decimate,) = scenario.hand(P0, ["Decimate"])
    shared, totem = scenario.battlefield(P1, ["Test Artifact Land Creature", "Test Totem"])
    scenario.mana(P0, R, G, W, W)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(decimate, P0))
    assert not any(r.kind is DecisionKind.CHOOSE_TARGETS for r in records(state, AnswerRecord))
    (spell,) = state.stack
    record = state.objects[spell].spell
    assert record is not None
    one, two = TargetObject(shared), TargetObject(totem)
    assert record.targets == ((one,), (one,), (two,), (one,))
    run_script(state, pass_(P0), pass_(P1))
    destroyed = records(state, PermanentDestroyed)
    assert [r.obj for r in destroyed] == [shared, totem]
    assert names(state, Zone.graveyard(P1)) == ["Test Artifact Land Creature", "Test Totem"]
    assert state.battlefield == []


def test_601_2c_each_instance_with_a_choice_is_asked_in_order() -> None:
    """Two artifacts and two lands: the artifact and the land are asked, in the order of the
    text; the creature (Test Artifact Land Creature) and the enchantment have one choice each.
    The shared object may be chosen as the land too."""
    scenario = Scenario(2)
    (decimate,) = scenario.hand(P0, ["Decimate"])
    ring, shared, totem, forest = scenario.battlefield(
        P1, ["Sol Ring", "Test Artifact Land Creature", "Test Totem", "Forest"]
    )
    scenario.mana(P0, R, G, W, W)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(decimate, P0))
    assert target_options(state) == (ObjectOption(ring), ObjectOption(shared))
    run_script(state, choose_targets(ring))
    assert target_options(state) == (ObjectOption(shared), ObjectOption(forest))
    run_script(state, choose_targets(shared))
    (spell,) = state.stack
    record = state.objects[spell].spell
    assert record is not None
    assert record.targets == (
        (TargetObject(ring),),
        (TargetObject(shared),),
        (TargetObject(totem),),
        (TargetObject(shared),),
    )


def test_608_2b_decimate_destroys_the_still_legal_targets() -> None:
    """Decimate targets Test Artifact Land Creature as the artifact and the land, Grizzly Bears
    as the creature and Test Totem as the enchantment. The Bears are exiled in response (Swords
    to Plowshares). Decimate still resolves (608.2b): the other three targets are destroyed, the
    shared object once; the illegal target is spared."""
    scenario = Scenario(2)
    (decimate,) = scenario.stack(P0, ["Decimate"])
    shared, bears, totem = scenario.battlefield(
        P1, ["Test Artifact Land Creature", "Grizzly Bears", "Test Totem"]
    )
    scenario.targets(
        decimate,
        [TargetObject(shared)],
        [TargetObject(bears)],
        [TargetObject(totem)],
        [TargetObject(shared)],
    )
    (swords,) = scenario.hand(P1, ["Swords to Plowshares"])
    scenario.mana(P1, W)
    scenario.at(Phase.PRECOMBAT_MAIN, priority=P1, passed=[P0])
    state = scenario.build()
    run_script(state, cast(swords, P1), choose_targets(bears), pass_(P1), pass_(P0))
    assert bears not in state.objects
    run_script(state, pass_(P0), pass_(P1))
    assert records(state, SpellDidNotResolve) == []
    assert [r.spell for r in records(state, SpellResolved)][-1] == decimate
    assert [r.obj for r in records(state, PermanentDestroyed)] == [shared, totem]
    assert state.battlefield == []
    assert names(state, Zone.graveyard(P0)) == ["Decimate"]


def test_608_2b_decimate_with_every_target_gone_doesnt_resolve() -> None:
    """P0's Decimate targets Test Artifact Land Creature (artifact, creature, land) and Test
    Totem; P1's Decimate on top targets the same two and resolves first. Every target of P0's is
    then gone: it doesn't resolve (608.2b)."""
    scenario = Scenario(2)
    (first,) = scenario.stack(P0, ["Decimate"])
    shared, totem = scenario.battlefield(P1, ["Test Artifact Land Creature", "Test Totem"])
    (second,) = scenario.stack(P1, ["Decimate"])
    for spell in (first, second):
        scenario.targets(
            spell,
            [TargetObject(shared)],
            [TargetObject(shared)],
            [TargetObject(totem)],
            [TargetObject(shared)],
        )
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1))
    assert state.battlefield == [] and state.stack == [first]
    run_script(state, pass_(P0), pass_(P1))
    assert [r.spell for r in records(state, SpellDidNotResolve)] == [first]
    assert len(records(state, PermanentDestroyed)) == 2
