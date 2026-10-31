"""Palace Guard ({2}{W}, Creature — Human Soldier 1/4): "This creature can block any number of
creatures."

Oracle text, cost, type line, power and toughness checked against Scryfall Snapshot 2026-10-31
(``tools/excerpts/cards.json``); the card has no rulings. Its ability is ``BlocksAnyNumber``
(``resolve.cards.primitives.combat``), read by ``defaults.blocks_allowed`` (509.1a: ``None``,
any number). It still blocks only creatures attacking its controller (802.4a), only while
untapped (509.1a), and divides its damage among the attackers it blocks (510.1d).
"""

from __future__ import annotations

from pathlib import Path

from resolve.cards.definitions import combat
from resolve.cards.primitives.combat import BlocksAnyNumber
from resolve.cards.registry import default_registry
from resolve.data.cards import load_card_excerpt
from resolve.data.types import CardType, Color
from resolve.decisions.spaces import ObjectOption
from resolve.effects.characteristics import characteristics
from resolve.rules import defaults
from resolve.state.ids import PlayerId
from resolve.state.turn import Phase, Step
from tests.combat_support import (
    assign_damage,
    block_space,
    blockable,
    declare_blockers,
    may_block,
    pass_to,
)
from tests.scenario import Scenario

EXCERPT = Path(__file__).resolve().parents[2] / "tools" / "excerpts" / "cards.json"
P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)


def test_its_definition_is_its_oracle_text() -> None:
    """The definition is registered, in ``combat.DEFINITIONS``; its one ability is
    ``BlocksAnyNumber``, whose text is the Oracle text."""
    definition = default_registry().get("Palace Guard")
    assert definition in combat.DEFINITIONS
    card = load_card_excerpt(EXCERPT).get("Palace Guard")
    (ability,) = definition.abilities
    assert isinstance(ability, BlocksAnyNumber)
    assert ability.text == card.faces[0].oracle_text
    assert definition.spell is None
    assert (card.faces[0].mana_cost, card.type_line) == ("{2}{W}", "Creature — Human Soldier")


def test_its_characteristics_come_from_the_card_data() -> None:
    scenario = Scenario(2)
    (guard,) = scenario.battlefield(P0, ["Palace Guard"])
    chars = characteristics(scenario.build(), guard)
    assert (chars.power, chars.toughness) == (1, 4)
    assert chars.card_types == (CardType.CREATURE,)
    assert chars.subtypes == ("Human", "Soldier")
    assert chars.colors == (Color.WHITE,)
    assert BlocksAnyNumber() in chars.abilities


def test_509_1a_palace_guard_may_block_any_number_but_others_one() -> None:
    """``blocks_allowed`` is ``None`` (any number) for Palace Guard, 1 for Grizzly Bears."""
    scenario = Scenario(2)
    (guard,) = scenario.battlefield(P0, ["Palace Guard"])
    (bears,) = scenario.battlefield(P0, ["Grizzly Bears"])
    state = scenario.build()
    assert defaults.blocks_allowed(state, guard) is None
    assert defaults.blocks_allowed(state, bears) == 1


def test_palace_guard_blocks_any_number() -> None:
    """Three creatures attack P1: Palace Guard may block all three (its maximum is the number of
    attackers it may block: 509.1a's "any number"), Grizzly Bears only one. The Guard blocks all
    three, and each is blocked (509.1h)."""
    scenario = Scenario(2)
    attackers = tuple(scenario.battlefield(P0, ["Grizzly Bears", "Savannah Lions", "Hill Giant"]))
    guard, bears = scenario.battlefield(P1, ["Palace Guard", "Grizzly Bears"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, *attackers)
    state = scenario.build()
    assert may_block(state) == (guard, bears)
    assert blockable(state, guard) == attackers
    assert block_space(state).maxima == (3, 1)
    declare_blockers(state, {guard: attackers})
    assert state.turn is not None and state.turn.combat is not None
    combat_state = state.turn.combat
    assert combat_state.blockers[guard].blocking == attackers
    assert all(combat_state.attackers[a].blocked for a in attackers)


def test_palace_guard_blocks_only_creatures_attacking_its_controller() -> None:
    """Three players; Grizzly Bears attacks P1 and Hill Giant attacks P2. P1's Palace Guard may
    block only the Bears (802.4a), so its maximum is 1 here."""
    scenario = Scenario(3)
    bears, giant = scenario.battlefield(P0, ["Grizzly Bears", "Hill Giant"])
    (guard,) = scenario.battlefield(P1, ["Palace Guard"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, bears)
    scenario.attacking(P2, giant)
    state = scenario.build()
    assert blockable(state, guard) == (bears,)
    assert block_space(state).maxima == (1,)


def test_a_tapped_palace_guard_cant_block() -> None:
    scenario = Scenario(2)
    (bears,) = scenario.battlefield(P0, ["Grizzly Bears"])
    guard, wall = scenario.battlefield(P1, ["Palace Guard", "Test Wall"])
    scenario.tap(guard)
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, bears)
    assert may_block(scenario.build()) == (wall,)


def test_palace_guard_blocking_two_divides_its_damage() -> None:
    """Palace Guard blocks Grizzly Bears and Savannah Lions (2/1); P1 assigns its 1 damage to
    the Lions (510.1d), which die. The Bears and the Lions deal it 2 each: 4 damage on toughness
    4 is lethal (704.5g), so it dies too. The Bears survive, and P1 is dealt no damage."""
    scenario = Scenario(2)
    bears, lions = scenario.battlefield(P0, ["Grizzly Bears", "Savannah Lions"])
    (guard,) = scenario.battlefield(P1, ["Palace Guard"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, bears, lions)
    state = scenario.build()
    declare_blockers(state, {guard: (bears, lions)})
    pass_to(state, Phase.COMBAT, Step.COMBAT_DAMAGE)
    assign_damage(state, {guard: {ObjectOption(lions): 1}})
    assert bears in state.battlefield
    assert lions not in state.battlefield and guard not in state.battlefield
    assert state.player(P1).life == 20
