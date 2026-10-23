"""601: casting spells, and paying their mana costs (601.2g-h, 605.3a, 118.3, 107.4a).

From the pinned CR:

- 601.2a: to propose casting a spell, the player moves the card from where it is to the stack; it
  becomes the topmost object, as a new object (400.7), and that player becomes its controller.
- 601.2f: the total cost is usually the mana cost. 601.2g: the player then has a chance to activate
  mana abilities (605.3a), before costs are paid; 118.3c: activating them isn't mandatory.
- 601.2h: the player pays the total cost; partial payments aren't allowed. 107.4a: a colored mana
  symbol is paid with one mana of its color; generic mana with mana of any type (107.4b).
- 118.3a, 106.4a: paying mana removes it from the pool; mana left over is announced. 500.5: it
  empties as the step or phase ends.
- 601.2i: the spell becomes cast; a player who had priority before casting gets it again
  (117.3c), and passing in succession starts over (117.4).
- 601.3, 601.3e: a player may begin to cast a spell only if a rule or effect allows it; some
  cards are cast with alternative characteristics, chosen before the card moves (709.3 split
  cards, 712.11 double-faced cards, 720.3 omens, 715.3 adventurers; 722.3: a preparation card's
  inset is never cast from the card). 903.8: a commander may be cast from the command zone.

Answers stay private to the player who gave them (design.md §7); the events are public.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from resolve.cards.registry import CardDefinition, CardRegistry
from resolve.data.cards import CardDatabase, parse_oracle_cards
from resolve.data.mana_cost import parse_mana_cost
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.request import DecisionAnswer
from resolve.decisions.spaces import (
    ActivateAbilityOption,
    Amounts,
    CastSpellOption,
    ChooseCounts,
    ChooseSubset,
    ManaActivationOption,
    ManaOption,
    Option,
    PlayerOption,
)
from resolve.effects.characteristics import variant_characteristics
from resolve.engine.api import submit, view_for
from resolve.engine.casting import CastSpell
from resolve.engine.concede import concede
from resolve.engine.loop import run
from resolve.engine.payment import PAY
from resolve.errors import InvalidAnswer, NotImplementedRule
from resolve.events.base import AnswerRecord
from resolve.events.mana import ManaSpent
from resolve.events.spells import ActionReversed, SpellCast, SpellProposed
from resolve.rules import defaults, legality
from resolve.state.config import GameConfig
from resolve.state.game import GameState
from resolve.state.ids import PlayerId
from resolve.state.mana import Mana, ManaType
from resolve.state.spell import (
    COMMANDER,
    FROM_HAND,
    NORMAL,
    Alternative,
    AlternativeKind,
    Back,
    Half,
)
from resolve.state.turn import Phase
from resolve.state.turn import Step as TurnStep
from resolve.state.zones import STACK, Zone
from tests import scryfall_fixtures as fx
from tests.casting_support import (
    activate,
    answered,
    cast,
    choose_targets,
    counts,
    options,
    pass_,
    pay,
    records,
    reverse,
)
from tests.game_fixtures import request_of, scenario_registry
from tests.scenario import Scenario, run_script

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)
W, U, R, G, C = (ManaType.WHITE, ManaType.BLUE, ManaType.RED, ManaType.GREEN, ManaType.COLORLESS)


def bears_with_forests(players: int = 2) -> tuple[Scenario, Any, list[Any]]:
    scenario = Scenario(players)
    (bears,) = scenario.hand(P0, ["Grizzly Bears"])
    forests = scenario.battlefield(P0, ["Forest", "Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    return scenario, bears, forests


# --- 601.2a: proposing ----------------------------------------------------------------------------


def test_601_2a_casting_moves_the_card_to_the_top_of_the_stack_under_its_caster() -> None:
    scenario, bears, _ = bears_with_forests()
    card = scenario.card_of(bears)
    state = scenario.build()
    run_script(state, cast(bears, P0))
    assert len(state.stack) == 1
    (spell,) = state.stack
    assert spell != bears and bears not in state.objects  # 400.7: a new object
    obj = state.objects[spell]
    assert obj.card == card and obj.controller == P0 and obj.zone == STACK
    assert obj.spell is not None and obj.spell.variant == NORMAL
    assert obj.spell.permission == FROM_HAND and obj.spell.cast_from == Zone.hand(P0)
    assert state.player(P0).hand == []
    (proposed,) = records(state, SpellProposed)
    assert (proposed.player, proposed.card, proposed.spell) == (P0, bears, spell)


# --- 601.2g-h: mana abilities and paying --------------------------------------------------------


def test_601_2g_the_casters_mana_abilities_are_offered_before_paying() -> None:
    scenario, bears, (forest_a, forest_b) = bears_with_forests()
    scenario.battlefield(P1, ["Plains"])
    state = scenario.build()
    run_script(state, cast(bears, P0))
    request = request_of(state)
    assert request.player == P0 and request.kind is DecisionKind.ACTIVATE_MANA_ABILITIES
    assert "601.2g" in request.rules
    assert options(state) == (
        PAY,
        ActivateAbilityOption(forest_a, 0),
        ActivateAbilityOption(forest_b, 0),
    )


def test_601_2h_a_payment_with_one_possible_answer_isnt_asked() -> None:
    """Both Forests tapped: "pay" is then the only option, and only one payment exists (both
    {G}), so neither is asked; the spell is cast and its caster gets priority."""
    scenario, bears, (forest_a, forest_b) = bears_with_forests()
    state = scenario.build()
    run_script(state, cast(bears, P0), activate(forest_a), activate(forest_b))
    request = request_of(state)
    assert request.player == P0 and request.kind is DecisionKind.PRIORITY_ACTION
    assert answered(state, DecisionKind.PAY_COSTS) == 0
    assert answered(state, DecisionKind.ACTIVATE_MANA_ABILITIES) == 2
    (cast_event,) = records(state, SpellCast)
    assert cast_event.mana_spent == (Mana(G, forest_a), Mana(G, forest_b))
    assert state.player(P0).mana_pool == []


def pool_scenario(*mana: ManaType, card: str = "Grizzly Bears") -> tuple[Scenario, Any]:
    scenario = Scenario(2)
    (spell,) = scenario.hand(P0, [card])
    scenario.mana(P0, *mana)
    scenario.at(Phase.PRECOMBAT_MAIN)
    return scenario, spell


@pytest.mark.parametrize(("amounts", "left"), [((2, 0), [W]), ((1, 1), [G])])
def test_601_2h_the_player_chooses_which_mana_pays(
    amounts: tuple[int, int], left: list[ManaType]
) -> None:
    """Pool {G}{G}{W}, Grizzly Bears {1}{G}: the {G} pays {G}, either the other {G} or the {W}
    pays {1} (107.4b). With no mana ability to activate, 601.2g asks nothing."""
    scenario, bears = pool_scenario(G, G, W)
    state = scenario.build()
    run_script(state, cast(bears, P0))
    request = request_of(state)
    assert request.kind is DecisionKind.PAY_COSTS and "601.2h" in request.rules
    assert request.space == ChooseCounts((ManaOption(Mana(G)), ManaOption(Mana(W))), (2, 1), 2)
    run_script(state, counts(*amounts))
    assert [unit.type for unit in state.player(P0).mana_pool] == left
    (spent,) = records(state, ManaSpent)
    assert spent.left == tuple(Mana(t) for t in left)  # 118.3a, 106.4a: announced


@pytest.mark.parametrize(
    ("pool", "answer"),
    [
        ((G, G, W), (0, 2)),  # outside the space: only one {W}
        ((G, G, W, W), (0, 2)),  # in the space, but {G} must be paid with green mana (107.4a)
    ],
)
def test_601_2h_a_rejected_payment_changes_nothing(
    pool: tuple[ManaType, ...], answer: tuple[int, int]
) -> None:
    """Both pools can pay {1}{G} in two ways ((2 G, 0 W) and (1 G, 1 W)), so the payment is asked.
    (0 G, 2 W) is refused: by the space's maxima, or by the cast's own check (107.4a)."""
    scenario, bears = pool_scenario(*pool)
    state = scenario.build()
    run_script(state, cast(bears, P0))
    request = request_of(state)
    assert request.kind is DecisionKind.PAY_COSTS
    before = copy.deepcopy(state)
    with pytest.raises(InvalidAnswer):
        submit(state, DecisionAnswer(request.id, P0, Amounts(answer)))
    assert state == before


def test_107_4a_colored_mana_can_only_be_paid_with_its_color() -> None:
    """{W}{W}{G}{G} can't pay Hill Giant's {3}{R}: no red mana. The cast is reversed (601.2h,
    733.1); nothing was activated, so nothing is asked."""
    scenario, giant = pool_scenario(W, W, G, G, card="Hill Giant")
    state = scenario.build()
    run_script(state, cast(giant, P0))
    assert state.player(P0).hand == [giant] and state.stack == []
    assert [unit.type for unit in state.player(P0).mana_pool] == [W, W, G, G]
    assert len(records(state, ActionReversed)) == 1 and records(state, SpellCast) == []
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION


def test_118_3a_unspent_mana_stays_and_is_announced() -> None:
    """{G}{G}{G} pays Grizzly Bears with one {G} left (only one payment exists: not asked). It
    stays in the pool, announced, and empties as the main phase ends (500.5)."""
    scenario, bears = pool_scenario(G, G, G)
    state = scenario.build()
    run_script(state, cast(bears, P0))
    assert state.player(P0).mana_pool == [Mana(G)]
    (spent,) = records(state, ManaSpent)
    assert spent.mana == (Mana(G), Mana(G)) and spent.left == (Mana(G),)
    run_script(state, pass_(P0), pass_(P1))  # the Bears resolve
    assert state.player(P0).mana_pool == [Mana(G)]
    run_script(state, pass_(P0), pass_(P1))  # the main phase ends
    assert state.player(P0).mana_pool == []
    turn = state.turn
    assert turn is not None and turn.phase is Phase.COMBAT


# --- 601.2i: becoming cast ------------------------------------------------------------------------


def test_601_2i_the_caster_receives_priority_after_casting() -> None:
    """P0 passed in their upkeep; P1 casts Test Shock with {R}, targeting P0 (601.2c). P1 gets
    priority again (117.3c) and P0's pass no longer counts (117.4)."""
    scenario = Scenario(2)
    (shock,) = scenario.hand(P1, ["Test Shock"])
    scenario.mana(P1, R)
    scenario.at(TurnStep.UPKEEP, priority=P1, passed=[P0])
    state = scenario.build()
    run_script(state, cast(shock, P1), choose_targets(PlayerOption(P0)))
    request = request_of(state)
    assert request.player == P1 and request.kind is DecisionKind.PRIORITY_ACTION
    turn = state.turn
    assert turn is not None and turn.passed == [] and turn.priority == P1
    assert len(state.stack) == 1


def test_601_2i_casting_is_logged_publicly() -> None:
    """P1 sees the proposal and the cast, with the total cost (601.2f) and the mana spent; P0's
    answers stay P0's."""
    scenario, bears, (forest_a, forest_b) = bears_with_forests()
    state = scenario.build()
    run_script(state, cast(bears, P0), activate(forest_a), activate(forest_b))
    seen = [entry.record for entry in view_for(state, P1).log]
    assert any(isinstance(record, SpellProposed) for record in seen)
    (cast_event,) = [record for record in seen if isinstance(record, SpellCast)]
    assert cast_event.total_cost == parse_mana_cost("{1}{G}")
    assert cast_event.mana_spent == (Mana(G, forest_a), Mana(G, forest_b))
    assert not any(isinstance(r, AnswerRecord) and r.player == P0 for r in seen)
    assert any(
        isinstance(entry.record, AnswerRecord) and entry.record.player == P0
        for entry in view_for(state, P0).log
    )


def test_601_2_paying_works_the_same_with_more_players() -> None:
    """Three players: only the caster's mana abilities are offered (605.3a, 602.2)."""
    scenario, bears, (forest_a, forest_b) = bears_with_forests(players=3)
    scenario.battlefield(P1, ["Forest"])
    scenario.battlefield(P2, ["Forest"])
    state = scenario.build()
    run_script(state, cast(bears, P0))
    assert options(state) == (
        PAY,
        ActivateAbilityOption(forest_a, 0),
        ActivateAbilityOption(forest_b, 0),
    )


# --- 601.3: variants and permissions -------------------------------------------------------------


def test_601_3_the_option_carries_its_variant_and_permission() -> None:
    scenario = Scenario(2, config=GameConfig.commander_game())
    (bears,) = scenario.hand(P0, ["Grizzly Bears"])
    commander = scenario.commander(P0, "Hill Giant")
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    assert CastSpellOption(bears, NORMAL, FROM_HAND) in options(state)
    assert CastSpellOption(commander, NORMAL, COMMANDER) in options(state)
    assert COMMANDER.rule == "903.8" and FROM_HAND.rule == "601.3"


MDFC: dict[str, Any] = {
    "object": "card",
    "oracle_id": "oid-test-mdfc",
    "name": "Test Bloom // Test Root",
    "layout": "modal_dfc",
    "cmc": 1.0,
    "type_line": "Instant // Sorcery",
    "color_identity": ["G"],
    "keywords": [],
    "card_faces": [
        {
            "object": "card_face",
            "name": "Test Bloom",
            "mana_cost": "{G}",
            "type_line": "Instant",
            "oracle_text": "",
            "colors": ["G"],
        },
        {
            "object": "card_face",
            "name": "Test Root",
            "mana_cost": "{1}{G}",
            "type_line": "Sorcery",
            "oracle_text": "",
            "colors": ["G"],
        },
    ],
}


def with_cards(*records_: dict[str, Any], players: int = 2) -> Scenario:
    """A scenario whose database and registry hold these cards besides the default ones."""
    names = [face["name"] for r in records_ for face in r.get("card_faces", [r])]
    registry = scenario_registry()
    definitions = [*(registry.get(n) for n in registry.names()), *map(CardDefinition, names)]
    return Scenario(
        players,
        database=CardDatabase(parse_oracle_cards([*_default_records(), *records_])),
        registry=CardRegistry(definitions),
    )


def _default_records() -> list[dict[str, Any]]:
    extra = [fx.INSTANT_CARD, fx.SORCERY_CARD, fx.NONBASIC_FOREST, fx.LAND_CREATURE, fx.DUAL_LAND]
    extra += [fx.GRIZZLY_BEARS, fx.SAVANNAH_LIONS, fx.HILL_GIANT, fx.ZERO_TOUGHNESS]
    extra += [fx.STAR_CREATURE, fx.VEHICLE, fx.SOL_RING]
    lands = [fx.PLAINS, fx.ISLAND, fx.SWAMP, fx.MOUNTAIN]
    return [*fx.default_cards(), *lands, *extra]


def test_709_3_712_11b_other_variants_are_gaps() -> None:
    """A split card offers its two halves only (709.3), each judged on its own characteristics
    (709.3a); casting either is a gap until M5. A modal double-faced card offers either face
    (712.11b); its back face is a gap until M4. A transforming card is cast front face up
    (712.11): casting it transformed (712.11a) is a gap too.

    A split card in hand still has no combined characteristics (709.4, M5), so these are asked of
    ``cast_options`` directly rather than through priority, which reaches 109.3 first."""
    scenario = with_cards(MDFC)
    (split,) = scenario.hand(P0, ["Test Spark // Test Frost"])
    (mdfc,) = scenario.hand(P0, ["Test Bloom // Test Root"])
    (daybreaker,) = scenario.hand(P0, ["Test Daybreaker // Test Nightfall"])
    state = scenario.build()
    offered = defaults.cast_options(state, P0)
    # No turn: only instants have the timing (117.1a); the halves are instants.
    assert offered == (
        CastSpellOption(split, Half(0), FROM_HAND),
        CastSpellOption(split, Half(1), FROM_HAND),
        CastSpellOption(mdfc, NORMAL, FROM_HAND),
    )
    assert variant_characteristics(state, split, Half(1)).name == "Test Frost"
    assert variant_characteristics(state, mdfc, Back()).name == "Test Root"
    for card, variant, rule in (
        (split, Half(0), "709.3"),
        (split, Half(1), "709.3"),
        (mdfc, Back(), "712.11b"),
        (daybreaker, Back(), "712.11a"),
    ):
        again = copy.deepcopy(state)
        again.tasks = [CastSpell(P0, card, variant, FROM_HAND)]
        with pytest.raises(NotImplementedRule) as gap:
            run(again)
        assert gap.value.rule == rule


def test_712_11b_a_modal_double_faced_cards_back_face_is_offered_with_its_timing() -> None:
    """The back face (a sorcery) is offered only with sorcery timing; the front (an instant)
    always: each face is judged alone (712.11c)."""
    scenario = with_cards(MDFC)
    (mdfc,) = scenario.hand(P0, ["Test Bloom // Test Root"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    assert CastSpellOption(mdfc, NORMAL, FROM_HAND) in options(state)
    assert CastSpellOption(mdfc, Back(), FROM_HAND) in options(state)


def omen_card(layout: str = "adventure") -> dict[str, Any]:
    front = fx.spell("Test Omen Bear", "{1}{G}", 2.0, "Creature — Bear", ["G"])
    front["power"], front["toughness"] = "2", "2"
    inset = fx.spell("Test Omen Wish", "{U}", 1.0, "Sorcery — Omen", ["U"])
    return {
        **front,
        "layout": layout,
        "name": "Test Omen Bear // Test Omen Wish",
        "card_faces": [{**front, "object": "card_face"}, {**inset, "object": "card_face"}],
    }


@pytest.mark.parametrize("layout", ["adventure", "omen"])
def test_720_3_casting_an_omen_as_an_omen_is_a_gap(layout: str) -> None:
    """The player chooses to cast an omen card normally or as an Omen (720.3); normally it is a
    creature spell that resolves as a creature. As an Omen it is a gap until its step."""
    scenario = with_cards(omen_card(layout))
    (card,) = scenario.hand(P0, ["Test Omen Bear // Test Omen Wish"])
    scenario.mana(P0, G, G)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    omen = CastSpellOption(card, Alternative(AlternativeKind.OMEN), FROM_HAND)
    assert CastSpellOption(card, NORMAL, FROM_HAND) in options(state)
    assert omen in options(state)  # its Omen is a sorcery: sorcery timing is here
    gapped = copy.deepcopy(state)
    with pytest.raises(NotImplementedRule) as gap:
        run_script(gapped, cast(card, P0, omen.variant))
    assert gap.value.rule == "720.3"
    run_script(state, cast(card, P0), pass_(P0), pass_(P1))
    (permanent,) = state.battlefield
    assert state.card_of(state.objects[permanent]).data.name == "Test Omen Bear // Test Omen Wish"


def test_722_3_a_preparation_cards_alternative_part_is_a_gap() -> None:
    """A preparation card is cast normally (722.3: never with its inset's characteristics); those
    characteristics are only its copies' (722.3c, M5): reading them is a gap."""
    record = omen_card("prepare")
    record["card_faces"][1]["type_line"] = "Sorcery"
    scenario = with_cards(record)
    (card,) = scenario.hand(P0, ["Test Omen Bear // Test Omen Wish"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    assert [o for o in options(state) if isinstance(o, CastSpellOption)] == [
        CastSpellOption(card, NORMAL, FROM_HAND)
    ]
    with pytest.raises(NotImplementedRule) as gap:
        variant_characteristics(state, card, Alternative(AlternativeKind.PREPARE))
    assert gap.value.rule == "722.3"


def test_903_8_casting_a_commander_is_a_gap_until_m7() -> None:
    """A commander cast from the command zone costs {2} more for each earlier such cast (903.8,
    the commander tax): M7."""
    scenario = Scenario(2, config=GameConfig.commander_game())
    commander = scenario.commander(P0, "Grizzly Bears")
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    with pytest.raises(NotImplementedRule) as gap:
        run_script(state, cast(commander, P0, permission=COMMANDER))
    assert gap.value.rule == "903.8"


def test_601_2e_a_proposal_that_became_illegal_is_reversed(monkeypatch: pytest.MonkeyPatch) -> None:
    """601.2e, 601.6: once proposed, the spell is checked again; an effect that forbids it then
    (a seam: a prohibition of the spell on the stack, not of the card in hand) makes the cast
    illegal. It is reversed (733.1): back in hand with its old ID, P0 keeps priority (733.2)."""
    scenario, bears, _ = bears_with_forests()
    state = scenario.build()
    original = legality.prohibitions

    def on_the_stack(state: GameState, action: legality.Action) -> tuple[legality.Prohibition, ...]:
        if isinstance(action, legality.CastAction) and action.card in state.stack:
            return (legality.Prohibition("101.2", "a test prohibition"),)
        return original(state, action)

    monkeypatch.setattr(legality, "prohibitions", on_the_stack)
    run_script(state, cast(bears, P0))
    assert state.player(P0).hand == [bears] and state.stack == []
    assert len(records(state, ActionReversed)) == 1 and records(state, SpellCast) == []
    assert answered(state, DecisionKind.ACTIVATE_MANA_ABILITIES) == 0  # 601.2g comes later
    request = request_of(state)
    assert request.player == P0 and request.kind is DecisionKind.PRIORITY_ACTION


def test_601_2g_choosing_pay_too_early_reverses_the_cast() -> None:
    """118.3c: activating mana abilities isn't mandatory. P0 taps one Forest and pays while the
    other is still untapped: {G} can't pay {1}{G} (118.3), the cast is reversed, and the Forest
    tapped during the cast is offered for reversal (733.1)."""
    scenario, bears, (forest_a, forest_b) = bears_with_forests()
    state = scenario.build()
    run_script(state, cast(bears, P0), activate(forest_a), pay())
    request = request_of(state)
    assert request.kind is DecisionKind.REVERSE_MANA_ABILITIES
    assert options_of_subset(state) == (ManaActivationOption(0, forest_a, 0),)
    run_script(state, reverse(ManaActivationOption(0, forest_a, 0)))
    assert not state.objects[forest_a].tapped and not state.objects[forest_b].tapped
    assert state.player(P0).hand == [bears]


def options_of_subset(state: GameState) -> tuple[Option, ...]:
    space = request_of(state).space
    assert isinstance(space, ChooseSubset)
    return space.options


NO_COST = fx.spell("Test Vision", "", 0.0, "Sorcery", ["U"], "Draw two cards.")


def test_118_6_a_spell_with_no_mana_cost_cant_be_cast_by_paying_it() -> None:
    """118.6, 202.1b: a card with no mana cost has an unpayable cost; it may be begun (601.3 looks
    only at permissions and timing) but its total cost can't be paid, so the cast is reversed."""
    scenario = with_cards(NO_COST)
    (vision,) = scenario.hand(P0, ["Test Vision"])
    scenario.mana(P0, U, U)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    assert CastSpellOption(vision, NORMAL, FROM_HAND) in options(state)
    run_script(state, cast(vision, P0))
    assert state.player(P0).hand == [vision] and state.stack == []
    assert len(records(state, ActionReversed)) == 1 and records(state, SpellCast) == []
    assert state.player(P0).mana_pool == [Mana(U), Mana(U)]


def test_800_4a_a_caster_who_concedes_takes_their_spell_with_them() -> None:
    """Three players: P0 concedes while paying for Grizzly Bears. The spell, like everything P0
    owns, leaves the game (800.4a); the cast just ends, and nothing is reversed."""
    scenario, bears, _ = bears_with_forests(players=3)
    state = scenario.build()
    run_script(state, cast(bears, P0))
    concede(state, P0)
    assert state.player(P0).left_game and state.stack == []
    assert records(state, ActionReversed) == [] and records(state, SpellCast) == []
    assert state.result is None
    request = request_of(state)
    assert request.player == P1 and request.kind is DecisionKind.PRIORITY_ACTION  # 800.4j


def test_104_2a_the_opponent_conceding_during_a_cast_ends_a_two_player_game() -> None:
    scenario, bears, _ = bears_with_forests()
    state = scenario.build()
    run_script(state, cast(bears, P0))
    concede(state, P1)
    assert state.result is not None and state.result.winners == (P0,)
    assert state.pending is None
    assert answered(state, DecisionKind.REVERSE_MANA_ABILITIES) == 0


def test_400_2_every_player_sees_how_a_spell_is_being_cast() -> None:
    """The stack is public (400.2): P1's view shows P0's spell with its record."""
    scenario, bears, (forest_a, forest_b) = bears_with_forests()
    state = scenario.build()
    run_script(state, cast(bears, P0), activate(forest_a), activate(forest_b))
    (spell,) = state.stack
    (shown,) = view_for(state, P1).stack
    assert shown.id == spell and shown.name == "Grizzly Bears"
    assert shown.spell == state.objects[spell].spell
    assert shown.spell is not None and shown.spell.total_cost == parse_mana_cost("{1}{G}")
