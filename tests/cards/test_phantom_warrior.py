"""Phantom Warrior ({1}{U}{U}, Creature — Illusion Warrior 2/2): "This creature can't be
blocked."

Oracle text, cost, type line, power and toughness checked against Scryfall Snapshot 2026-10-31
(``tools/excerpts/cards.json``); the card has no rulings. Its ability is ``CantBeBlocked``
(``resolve.cards.primitives.combat``), a prohibition of ``legality.allowed(BlockAction)`` read from
the attacker (509.1b); the restriction itself is tested in tests/rules/test_509_1b_restrictions.py
(``test_phantom_warrior_cant_be_blocked``, ``test_phantom_warrior_blocks_as_usual``).
"""

from __future__ import annotations

from pathlib import Path

from resolve.cards.definitions import combat
from resolve.cards.primitives.combat import CantBeBlocked
from resolve.cards.registry import default_registry
from resolve.data.cards import load_card_excerpt
from resolve.data.types import CardType, Color
from resolve.decisions.kinds import DecisionKind
from resolve.effects.characteristics import characteristics
from resolve.state.ids import PlayerId
from resolve.state.turn import Phase, Step
from tests.combat_support import declare_attackers, pass_to
from tests.game_fixtures import request_of
from tests.scenario import Scenario

EXCERPT = Path(__file__).resolve().parents[2] / "tools" / "excerpts" / "cards.json"
P0, P1 = PlayerId(0), PlayerId(1)


def test_its_definition_is_its_oracle_text() -> None:
    definition = default_registry().get("Phantom Warrior")
    assert definition in combat.DEFINITIONS
    card = load_card_excerpt(EXCERPT).get("Phantom Warrior")
    (ability,) = definition.abilities
    assert isinstance(ability, CantBeBlocked)
    assert ability.text == card.faces[0].oracle_text
    assert definition.spell is None
    face = card.faces[0]
    assert (face.mana_cost, card.type_line, face.power, face.toughness) == (
        "{1}{U}{U}", "Creature — Illusion Warrior", "2", "2",
    )  # fmt: skip


def test_its_characteristics_come_from_the_card_data() -> None:
    scenario = Scenario(2)
    (warrior,) = scenario.battlefield(P0, ["Phantom Warrior"])
    chars = characteristics(scenario.build(), warrior)
    assert (chars.power, chars.toughness) == (2, 2)
    assert chars.card_types == (CardType.CREATURE,)
    assert chars.subtypes == ("Illusion", "Warrior")
    assert chars.colors == (Color.BLUE,)
    assert CantBeBlocked() in chars.abilities


def test_it_attacks_past_any_blocker() -> None:
    """Phantom Warrior attacks P1, who controls Grizzly Bears and Wind Drake: P1 has no block to
    declare, so on reaching the declare blockers step the first decision is P0's priority, and
    the Warrior deals its 2 combat damage to P1 (510.1b)."""
    scenario = Scenario(2)
    (warrior,) = scenario.battlefield(P0, ["Phantom Warrior"])
    scenario.battlefield(P1, ["Grizzly Bears", "Wind Drake"])
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    declare_attackers(state, {warrior: P1})
    pass_to(state, Phase.COMBAT, Step.DECLARE_BLOCKERS)
    request = request_of(state)
    assert (request.kind, request.player) == (DecisionKind.PRIORITY_ACTION, P0)
    pass_to(state, Phase.POSTCOMBAT_MAIN)
    assert state.player(P1).life == 18
