"""M3.5's combat-rules cards: Juggernaut, Prized Unicorn, Ghostly Prison, Mogg Flunkies and Silent
Arbiter (the M3 plan's section 7), and the primitives they are built from.

Oracle text, costs, type lines, power and toughness checked against Scryfall Snapshot 2026-11-02
(``tools/excerpts/cards.json``). Their rules in play, and each ruling, are tested with the rules
they exercise: tests/rules/test_508_1_requirements_and_restrictions.py (Juggernaut, Ghostly Prison,
Mogg Flunkies, Silent Arbiter's attacking half), test_509_1c_blocking_requirements.py (Prized
Unicorn, Mogg Flunkies and Silent Arbiter blocking) and
tests/interactions/test_lure_ghostly_prison.py (the Lure torture test). This file checks each
definition against its card and Juggernaut's Walls restriction (509.1b), which nothing else
covers.
"""

from __future__ import annotations

import copy
import pickle
from pathlib import Path

import pytest

from resolve.cards.definitions import combat
from resolve.cards.keywords.qualities import SubtypeQuality
from resolve.cards.primitives.combat import (
    AtMostCreatures,
    AttacksEachCombat,
    AttackTax,
    BlocksEachCombat,
    BlockTax,
    CantAttackOrBlockAlone,
    CantAttackOrBlockUnless,
    CantBeBlockedBy,
    CreaturesYouControl,
    MustBeBlockedByAll,
)
from resolve.cards.primitives.conditions import ControlsAtLeast
from resolve.cards.primitives.words import SubtypeWord
from resolve.cards.registry import default_registry
from resolve.data.cards import load_card_excerpt
from resolve.data.mana_cost import parse_mana_cost
from resolve.data.types import CardType
from resolve.rules import legality
from resolve.state.ids import PlayerId
from resolve.state.turn import Step
from tests.combat_support import blockable, declare_blockers, may_block
from tests.scenario import Scenario

EXCERPT = Path(__file__).resolve().parents[2] / "tools" / "excerpts" / "cards.json"
P0, P1 = PlayerId(0), PlayerId(1)

CARDS = {
    "Juggernaut": ("{4}", "Artifact Creature — Juggernaut", ("5", "3")),
    "Prized Unicorn": ("{3}{G}", "Creature — Unicorn", ("2", "2")),
    "Ghostly Prison": ("{2}{W}", "Enchantment", None),
    "Mogg Flunkies": ("{1}{R}", "Creature — Goblin", ("3", "3")),
    "Silent Arbiter": ("{4}", "Artifact Creature — Construct", ("1", "5")),
}


@pytest.mark.parametrize("name", sorted(CARDS))
def test_its_definition_is_its_oracle_text(name: str) -> None:
    """Each card is registered, in ``combat.DEFINITIONS``; its abilities' texts, one per line,
    are its Oracle text; its cost, type line, power and toughness are the snapshot's."""
    definition = default_registry().get(name)
    assert definition in combat.DEFINITIONS
    card = load_card_excerpt(EXCERPT).get(name)
    face = card.faces[0]
    assert "\n".join(a.text for a in definition.abilities) == face.oracle_text
    assert definition.spell is None
    cost, type_line, pt = CARDS[name]
    assert (face.mana_cost, card.type_line) == (cost, type_line)
    assert (None if face.power is None else (face.power, face.toughness)) == pt


def test_the_definitions_use_the_planned_primitives() -> None:
    registry = default_registry()
    assert registry.get("Juggernaut").abilities == (
        AttacksEachCombat(),
        CantBeBlockedBy(SubtypeQuality(SubtypeWord("Wall"))),
    )
    assert registry.get("Prized Unicorn").abilities == (MustBeBlockedByAll(),)
    assert registry.get("Ghostly Prison").abilities == (AttackTax(parse_mana_cost("{2}")),)
    assert registry.get("Mogg Flunkies").abilities == (CantAttackOrBlockAlone(),)
    assert registry.get("Silent Arbiter").abilities == (
        AtMostCreatures(1, blocking=False),
        AtMostCreatures(1, blocking=True),
    )


def test_the_primitives_texts() -> None:
    """The fixtures' texts, and plurals and numbers the cards don't show."""
    assert AttacksEachCombat(CreaturesYouControl()).text == (
        "Creatures you control attack each combat if able."
    )
    assert BlocksEachCombat().text == "This creature blocks each combat if able."
    assert CantAttackOrBlockUnless(ControlsAtLeast(7, CardType.LAND)).text == (
        "This creature can't attack or block unless you control seven or more lands."
    )
    assert BlockTax(parse_mana_cost("{1}")).text == (
        "Creatures can't block unless their controller pays {1} for each creature they control "
        "that's blocking."
    )
    assert (
        AtMostCreatures(2, blocking=True).text
        == "No more than two creatures can block each combat."
    )
    assert CantBeBlockedBy(SubtypeQuality(SubtypeWord("Elf"))).text == (
        "This creature can't be blocked by Elves."
    )
    with pytest.raises(ValueError):
        AtMostCreatures(0, blocking=False)


def test_the_primitives_are_pure_data() -> None:
    abilities = (
        AttackTax(parse_mana_cost("{2}")),
        CantAttackOrBlockUnless(ControlsAtLeast(7, CardType.LAND)),
        AttacksEachCombat(CreaturesYouControl()),
    )
    assert copy.deepcopy(abilities) == abilities
    assert pickle.loads(pickle.dumps(abilities)) == abilities


def test_juggernaut_cant_be_blocked_by_walls() -> None:
    """Juggernaut attacks P1, who controls Wall of Stone (a Wall) and Grizzly Bears: the Wall may
    not block it (509.1b, a prohibition citing 509.1b), the Bears may."""
    scenario = Scenario(2)
    (juggernaut,) = scenario.battlefield(P0, ["Juggernaut"])
    wall, bears = scenario.battlefield(P1, ["Wall of Stone", "Grizzly Bears"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, juggernaut)
    state = scenario.build()
    verdict = legality.allowed(state, legality.BlockAction(P1, wall, juggernaut))
    assert not verdict.allowed and "509.1b" in verdict.rules
    assert may_block(state) == (bears,)
    assert blockable(state, bears) == (juggernaut,)
    declare_blockers(state, {bears: (juggernaut,)})


def test_juggernaut_can_be_blocked_by_a_wall_only_through_its_own_ability() -> None:
    """A Wall can still block other attackers: Wall of Stone may block Grizzly Bears attacking
    beside Juggernaut."""
    scenario = Scenario(2)
    juggernaut, bears = scenario.battlefield(P0, ["Juggernaut", "Grizzly Bears"])
    (wall,) = scenario.battlefield(P1, ["Wall of Stone"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, juggernaut, bears)
    state = scenario.build()
    assert blockable(state, wall) == (bears,)
