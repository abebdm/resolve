"""Spell primitives: targets (``TargetSpec`` and its filters), references, values, the spell
ability and its mode, and the effects ``DealDamage``, ``Destroy``, ``Exile``, ``GainLife`` and
``DrawCards``, on their own.

From the pinned CR: 115.3 and 115.6 (how many targets an instance chooses), 115.4 ("any
target"), 109.5 ("you"), 608.2h (values evaluated as the effect applies; last known information),
608.2b (an illegal target gives no information), 107.1b (no negative numbers printed), 119.10
(gaining 0 life is no event), 120.8 (0 damage isn't dealt), 120.1a (only creatures,
planeswalkers and battles are dealt damage), 701.8a, 701.13a, 121.2.
"""

from __future__ import annotations

import pytest

from resolve.cards.primitives.effects import DealDamage, Destroy, DrawCards, Exile, GainLife
from resolve.cards.primitives.refs import (
    ControllerOf,
    EachCreature,
    EachOpponent,
    TargetRef,
    ThisObject,
    You,
)
from resolve.cards.primitives.spells import Mode, ModeChoice, SpellAbility
from resolve.cards.primitives.targets import (
    ANY_TARGET,
    ObjectFilter,
    PlayerFilter,
    SpellFilter,
    TargetSpec,
    target,
)
from resolve.cards.primitives.values import Fixed, PowerOf, X
from resolve.data.types import CardType
from resolve.effects.evaluation import Context, Timing, evaluate, players
from resolve.engine.drawing import DrawCards as DrawTask
from resolve.engine.loop import run
from resolve.errors import NotImplementedRule
from resolve.events.cards import CardDrawn
from resolve.events.damage import DamageDealt
from resolve.events.life import LifeGained
from resolve.events.permanents import ObjectExiled, PermanentDestroyed
from resolve.events.pipeline import ApplyEvents
from resolve.state.game import move_object
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.spell import Target, TargetObject, TargetPlayer
from resolve.state.zones import EXILE, Zone
from tests.engine_support import Hold
from tests.scenario import Scenario, names

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)
CREATURE = target(CardType.CREATURE)
ARTIFACT = target(CardType.ARTIFACT)


def context(spell: ObjectId, *targets: tuple[Target, ...]) -> Context:
    return Context(Timing.RESOLUTION, spell, P0, targets)


# --- Targets -----------------------------------------------------------------------------------


def test_115_targets_are_written_as_card_text_writes_them() -> None:
    assert CREATURE.text == "target creature"
    assert target(CardType.CREATURE, you_control=True).text == "target creature you control"
    assert ANY_TARGET.text == "any target"
    assert TargetSpec(players=PlayerFilter()).text == "target player"
    assert TargetSpec(players=PlayerFilter(opponents_only=True)).text == "target opponent"
    assert TargetSpec(spells=SpellFilter()).text == "target spell"
    artifacts = ObjectFilter((CardType.ARTIFACT,))
    assert TargetSpec(artifacts, minimum=2, maximum=2).text == "two target artifacts"
    assert TargetSpec(artifacts, minimum=0, maximum=1).text == "up to one target artifact"
    assert TargetSpec(artifacts, minimum=1, maximum=3).text == "from 1 to 3 target artifacts"
    assert ObjectFilter((CardType.ARTIFACT, CardType.ENCHANTMENT)).text == "artifact or enchantment"
    assert ObjectFilter().text == "permanent"


def test_115_6_a_target_spec_needs_something_to_choose_and_sane_bounds() -> None:
    with pytest.raises(ValueError, match="kind"):
        TargetSpec()
    with pytest.raises(ValueError, match="minimum"):
        TargetSpec(ObjectFilter(), minimum=2, maximum=1)
    with pytest.raises(ValueError, match="minimum"):
        TargetSpec(ObjectFilter(), minimum=0, maximum=0)
    assert TargetSpec(ObjectFilter(), minimum=0, maximum=1).minimum == 0  # 115.6


def test_115_filters_match_types_and_controllers() -> None:
    scenario = Scenario(2)
    ring, bears = scenario.battlefield(P0, ["Sol Ring", "Grizzly Bears"])
    (lions,) = scenario.battlefield(P1, ["Savannah Lions"])
    (spell,) = scenario.stack(P0, ["Test Shock"])
    state = scenario.build()
    creature = ObjectFilter((CardType.CREATURE,))
    assert [creature.matches(state, o, P0) for o in (ring, bears, lions)] == [False, True, True]
    yours = ObjectFilter((CardType.CREATURE,), You())
    assert [yours.matches(state, o, P0) for o in (bears, lions)] == [True, False]
    assert ObjectFilter().matches(state, ring, P1)
    assert PlayerFilter(opponents_only=True).matches(state, P1, P0)
    assert not PlayerFilter(opponents_only=True).matches(state, P0, P0)
    assert SpellFilter().matches(state, spell, P1) and not SpellFilter().matches(state, ring, P1)


# --- Spell abilities and values ----------------------------------------------------------------


def test_113_3a_a_spell_ability_has_modes_and_text() -> None:
    mode = Mode((), (GainLife(You(), Fixed(3)),))
    assert SpellAbility((mode,)).text == "You gain 3 life."
    with pytest.raises(ValueError, match="effect"):
        Mode((), ())
    with pytest.raises(ValueError, match="mode"):
        SpellAbility(())
    with pytest.raises(ValueError, match="nonmodal"):
        SpellAbility((mode, mode))
    modal = SpellAbility((mode, Mode((), (DrawCards(),))), ModeChoice(1, 1))
    assert modal.text == "Choose one \u2014\n\u2022 You gain 3 life.\n\u2022 Draw a card."


def test_700_2_a_modal_spells_text_lists_its_modes() -> None:
    """700.2: the instruction to choose, then the modes as a bulleted list; 700.2d: "You may
    choose the same mode more than once." for a repeatable choice."""
    gain, draw = Mode((), (GainLife(You(), Fixed(3)),)), Mode((), (DrawCards(),))

    def triple_up_to(most: int) -> str:
        return SpellAbility((gain, draw, gain), ModeChoice(0, most)).text

    three = SpellAbility((gain, draw), ModeChoice(3, 3, repeatable=True))
    assert three.text == (
        "Choose three. You may choose the same mode more than once.\n"
        "\u2022 You gain 3 life.\n\u2022 Draw a card."
    )
    assert SpellAbility((gain, draw), ModeChoice(1, 2)).text.startswith(
        "Choose one or both \u2014\n"
    )
    triple = SpellAbility((gain, draw, gain), ModeChoice(1, 3))
    assert triple.text.startswith("Choose one or more \u2014\n")
    assert SpellAbility((gain, draw), ModeChoice(0, 2)).text.startswith("Choose any number \u2014")
    assert triple_up_to(1).startswith("Choose up to one \u2014\n")
    with pytest.raises(ValueError, match="mode"):
        ModeChoice(-1, 1)
    with pytest.raises(ValueError, match="mode"):
        ModeChoice(2, 1)
    with pytest.raises(ValueError, match="more modes"):
        SpellAbility((gain, draw), ModeChoice(3, 3))


def test_700_2d_mode_combinations() -> None:
    """Every choice of modes among the legal ones (700.2a), each once, listed in printed order:
    without repeats each mode at most once, with repeats (700.2d) every multiset."""
    pair = ModeChoice(2, 2)
    assert pair.combinations((0, 1, 2)) == ((0, 1), (0, 2), (1, 2))
    assert pair.combinations((1, 2)) == ((1, 2),)
    assert pair.combinations((2,)) == ()
    assert ModeChoice(1, 2).combinations((0, 1)) == ((0,), (1,), (0, 1))
    three = ModeChoice(3, 3, repeatable=True)
    assert len(three.combinations((0, 1, 2))) == 10
    assert three.combinations((0, 1)) == ((0, 0, 0), (0, 0, 1), (0, 1, 1), (1, 1, 1))
    assert three.combinations(()) == ()


def test_601_2c_700_2c_the_instances_of_target_are_the_chosen_modes() -> None:
    """A nonmodal spell's instances are its one mode's; a modal spell's are each chosen mode's in
    turn, a repeated mode's once per repetition (700.2d)."""
    shatter = Mode((ARTIFACT,), (Destroy((TargetRef(0),)),))
    draw = Mode((), (DrawCards(),))
    modal = SpellAbility((draw, shatter), ModeChoice(2, 2, repeatable=True))
    assert modal.instances((0, 1)) == (ARTIFACT,)
    assert modal.instances((1, 1)) == (ARTIFACT, ARTIFACT)
    assert modal.instances((0, 0)) == ()
    assert modal.chosen((0, 1)) == (draw, shatter)
    single = SpellAbility((shatter,))
    assert single.instances(()) == (ARTIFACT,) and single.chosen(()) == (shatter,)


def test_effects_are_written_as_card_text_writes_them() -> None:
    def text(targets: tuple[TargetSpec, ...], *effects: object) -> str:
        return Mode(targets, effects).text  # type: ignore[arg-type]

    player = TargetSpec(players=PlayerFilter())
    assert text((), DrawCards()) == "Draw a card."
    assert text((), DrawCards(Fixed(2))) == "Draw two cards."
    assert text((player,), DrawCards(player=TargetRef(0))) == "Target player draws a card."
    assert text((ANY_TARGET,), DealDamage(Fixed(3), (TargetRef(0),))) == (
        "This spell deals 3 damage to any target."
    )
    assert text((), DealDamage(Fixed(1), (EachCreature(), EachOpponent()))) == (
        "This spell deals 1 damage to each creature and each opponent."
    )
    assert text((CREATURE,), DealDamage(Fixed(1), (EachCreature(except_=TargetRef(0)),))) == (
        "This spell deals 1 damage to each creature other than target creature."
    )
    assert text((ANY_TARGET,), DealDamage(X(), (TargetRef(0),))) == (
        "This spell deals X damage to any target."
    )
    assert text((CREATURE,), Destroy((TargetRef(0),))) == "Destroy target creature."
    assert text((CREATURE,), Exile((TargetRef(0),)), GainLife(You(), PowerOf(TargetRef(0)))) == (
        "Exile target creature. You gain life equal to its power."
    )


def test_107_1b_a_printed_number_cant_be_negative() -> None:
    with pytest.raises(ValueError, match="negative"):
        Fixed(-1)
    assert (Fixed(2).word, Fixed(12).word) == ("two", "12")


def test_608_2h_values_are_evaluated_now() -> None:
    """``PowerOf`` reads the object as it is now, its last known information once it has left
    (608.2h), and nothing for an illegal target (608.2b: no target left in the context)."""
    scenario = Scenario(2)
    (spell,) = scenario.stack(P0, ["Swords to Plowshares"])
    (giant,) = scenario.battlefield(P1, ["Hill Giant"])
    state = scenario.build()
    power = PowerOf(TargetRef(0))
    found = context(spell, (TargetObject(giant),))
    assert evaluate(state, Fixed(4), found) == 4
    assert evaluate(state, power, found) == 3
    move_object(state, giant, EXILE)
    assert evaluate(state, power, found) == 3  # last known information
    assert evaluate(state, power, context(spell, ())) is None
    assert evaluate(state, PowerOf(ThisObject()), found) is None  # an instant has no power


def test_107_3a_x_is_the_value_announced_for_the_spell() -> None:
    """``X()`` is the value announced for the spell (107.3a), read from its record, also once it
    has left the stack (its last known information, 608.2h). A spell without an announced X
    (107.3f: X only in its text) is a gap."""
    scenario = Scenario(2)
    blaze, shock = scenario.stack(P0, ["Test Blaze", "Test Shock"])
    scenario.x(blaze, 4)
    state = scenario.build()
    assert evaluate(state, X(), context(blaze, ())) == 4
    move_object(state, blaze, Zone.graveyard(P0))
    assert evaluate(state, X(), context(blaze, ())) == 4
    with pytest.raises(NotImplementedRule) as gap:
        evaluate(state, X(), context(shock, ()))
    assert gap.value.rule == "107.3f"


def test_109_5_players_are_you_controllers_and_targets_still_in_the_game() -> None:
    scenario = Scenario(3)
    (spell,) = scenario.stack(P0, ["Test Shock"])
    (bears,) = scenario.battlefield(P2, ["Grizzly Bears"])
    state = scenario.build()
    found = context(spell, (TargetObject(bears), TargetPlayer(P1)))
    assert players(state, You(), found) == (P0,)
    assert players(state, ControllerOf(TargetRef(0)), found) == (P2,)
    assert players(state, TargetRef(0), found) == (P1,)
    state.player(P1).left_game = True
    assert players(state, TargetRef(0), found) == ()


# --- Effects -----------------------------------------------------------------------------------


def events_of(tasks: tuple[object, ...]) -> tuple[object, ...]:
    (task,) = tasks
    assert isinstance(task, ApplyEvents)
    return task.events


def test_120_deal_damage_is_one_event_to_creatures_and_players() -> None:
    """Each recipient once, only creatures, planeswalkers and battles among objects (120.1a: not
    Sol Ring), and nothing at all for 0 damage (120.8) or an undeterminable amount (608.2b)."""
    scenario = Scenario(3)
    (spell,) = scenario.stack(P0, ["Test Shock"])
    bears, ring = scenario.battlefield(P1, ["Grizzly Bears", "Sol Ring"])
    state = scenario.build()
    found = context(spell, (TargetObject(bears), TargetObject(ring), TargetPlayer(P2)))
    effect = DealDamage(Fixed(2), (TargetRef(0), EachCreature(), EachOpponent()))
    (event,) = events_of(effect.tasks(state, found))
    assert event == DamageDealt(
        source=spell,
        to_objects=((bears, 2),),
        to_players=((P2, 2), (P1, 2)),
        rules=("120.2b", "120.3"),
    )
    assert DealDamage(Fixed(0), (TargetRef(0),)).tasks(state, found) == ()
    no_power = DealDamage(PowerOf(TargetRef(0)), (EachOpponent(),))
    assert no_power.tasks(state, context(spell, ())) == ()


def test_701_8a_destroy_destroys_each_permanent_once() -> None:
    scenario = Scenario(2)
    (spell,) = scenario.stack(P0, ["Decimate"])
    shared, totem = scenario.battlefield(P1, ["Test Artifact Land Creature", "Test Totem"])
    state = scenario.build()
    found = context(spell, (TargetObject(shared),), (TargetObject(totem),), (TargetObject(shared),))
    effect = Destroy((TargetRef(0), TargetRef(1), TargetRef(2)))
    assert events_of(effect.tasks(state, found)) == (
        PermanentDestroyed(obj=shared, rules=("701.8a",)),
        PermanentDestroyed(obj=totem, rules=("701.8a",)),
    )
    assert Destroy((TargetRef(0),)).tasks(state, context(spell, ())) == ()


def test_701_13a_exile_exiles_from_wherever_it_is() -> None:
    scenario = Scenario(2)
    (spell,) = scenario.stack(P0, ["Swords to Plowshares"])
    (dead,) = scenario.graveyard(P1, ["Grizzly Bears"])
    state = scenario.build()
    effect = Exile((TargetRef(0),))
    found = context(spell, (TargetObject(dead),))
    (event,) = events_of(effect.tasks(state, found))
    assert event == ObjectExiled(obj=dead, rules=("701.13a",))
    gone = context(spell, (TargetObject(ObjectId(999)),))
    assert effect.tasks(state, gone) == ()


def test_119_gain_life_gains_or_does_nothing() -> None:
    scenario = Scenario(2)
    (spell,) = scenario.stack(P0, ["Test Shock"])
    state = scenario.build()
    found = context(spell)
    (event,) = events_of(GainLife(You(), Fixed(3)).tasks(state, found))
    assert event == LifeGained(player=P0, amount=3, rules=("119.3",))
    assert GainLife(You(), Fixed(0)).tasks(state, found) == ()  # 119.10


def test_121_draw_cards_draws_one_at_a_time() -> None:
    """ "Draw two cards": two separate draw events, one card each (121.2), top card first."""
    scenario = Scenario(2)
    (spell,) = scenario.stack(P0, ["Test Ponder"])
    top, second, _ = scenario.library(P0, ["Forest", "Plains", "Island"])
    state = scenario.build()
    (task,) = DrawCards(Fixed(2)).tasks(state, context(spell))
    assert isinstance(task, DrawTask) and task.rules == ("121.1", "121.2")
    state.tasks = [Hold(), task]
    run(state)
    draws = [e.record for e in state.event_log if isinstance(e.record, CardDrawn)]
    assert [(d.player, d.drawn_from) for d in draws] == [(P0, top), (P0, second)]
    assert names(state, Zone.hand(P0)) == ["Forest", "Plains"]
    assert DrawCards(Fixed(0)).tasks(state, context(spell)) == ()
