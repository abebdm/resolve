"""115 and 601.2c: choosing targets as a spell is cast.

From the pinned CR:

- 115.1, 115.1a: an instant or sorcery whose text says "target [something]" chooses its targets
  as it is cast (601.2c).
- 115.2: only permanents are legal targets, unless the spell says it can target an object in
  another zone or a player (or targets a spell).
- 115.3: the same object or player can't be chosen twice for one instance of the word
  "target"; separate instances may each choose it (601.2c).
- 115.4: "any target" means a creature, planeswalker or battle, or a player; nothing else.
- 115.5: a spell on the stack is an illegal target for itself.
- 601.2c: the player announces the targets; each chosen object or player becomes a target of
  the spell (the moment ward and other "becomes the target" abilities trigger). 601.2e and 733:
  a spell that can't get legal targets is illegal and would be reversed; the engine doesn't
  offer it at all (docs/plans/m2.md §3.5: earlier stages offer only legal choices).
- 800.4a: a player who has left the game is no longer in it, so nothing can target them.

``target_problem`` (``resolve.rules.targeting``) is the one check of a target's legality, used
when targets are offered, when they're chosen and when the spell resolves (608.2b).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pytest

from resolve.cards.primitives.effects import Destroy, DrawCards
from resolve.cards.primitives.refs import TargetRef
from resolve.cards.primitives.spells import Mode, SpellAbility
from resolve.cards.primitives.targets import ObjectFilter, SpellFilter, TargetSpec
from resolve.cards.registry import CardDefinition, CardRegistry
from resolve.data.cards import CardDatabase, parse_oracle_cards
from resolve.data.types import CardType
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import (
    CastSpellOption,
    ChooseSubset,
    ObjectOption,
    PickMany,
    PlayerOption,
)
from resolve.effects.characteristics import characteristics
from resolve.engine.api import submit, view_for
from resolve.engine.concede import concede
from resolve.errors import InvalidAnswer
from resolve.events.base import AnswerRecord
from resolve.events.spells import BecameTargets, SpellDidNotResolve
from resolve.rules import legality, targeting
from resolve.rules.legality import Targeter, Verdict
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import ManaType
from resolve.state.spell import Target, TargetObject, TargetPlayer
from resolve.state.turn import Phase
from resolve.state.zones import Zone
from tests import scryfall_fixtures as fx
from tests.casting_support import cast, choose_targets, options, pass_, records
from tests.game_fixtures import answer, request_of, scenario_database, scenario_registry
from tests.scenario import Scenario, names, run_script

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)
W, R = ManaType.WHITE, ManaType.RED


def target_options(state: GameState) -> tuple[object, ...]:
    """The options of the pending 601.2c decision."""
    request = request_of(state)
    assert request.kind is DecisionKind.CHOOSE_TARGETS
    assert isinstance(request.space, ChooseSubset)
    return request.space.options


def casts(state: GameState) -> list[CastSpellOption]:
    return [o for o in options(state) if isinstance(o, CastSpellOption)]


def test_115_2_only_permanents_unless_the_spell_says_otherwise() -> None:
    """Swords to Plowshares ("target creature") offers the creatures on the battlefield, both
    players', and nothing else: not lands, not Sol Ring, not players, not the creature card in
    a graveyard (115.2)."""
    scenario = Scenario(2)
    (swords,) = scenario.hand(P0, ["Swords to Plowshares"])
    bears, _, _ = scenario.battlefield(P0, ["Grizzly Bears", "Plains", "Sol Ring"])
    (lions,) = scenario.battlefield(P1, ["Savannah Lions"])
    scenario.graveyard(P1, ["Hill Giant"])
    scenario.mana(P0, W)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(swords, P0))
    assert target_options(state) == (ObjectOption(bears), ObjectOption(lions))
    request = request_of(state)
    assert request.player == P0 and request.rules == ("601.2c", "115.1")
    space = request.space
    assert isinstance(space, ChooseSubset) and (space.minimum, space.maximum) == (1, 1)


def test_115_4_any_target_is_creatures_and_players() -> None:
    """Test Shock ("any target") offers each creature and each player in the game (115.4), not
    a noncreature artifact or a land."""
    scenario = Scenario(2)
    (shock,) = scenario.hand(P0, ["Test Shock"])
    bears, _ = scenario.battlefield(P0, ["Grizzly Bears", "Sol Ring"])
    lions, _ = scenario.battlefield(P1, ["Savannah Lions", "Mountain"])
    scenario.mana(P0, R)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(shock, P0))
    assert target_options(state) == (
        ObjectOption(bears),
        ObjectOption(lions),
        PlayerOption(P0),
        PlayerOption(P1),
    )


def test_800_4a_a_player_who_left_the_game_cant_be_targeted() -> None:
    scenario = Scenario(3)
    (shock,) = scenario.hand(P0, ["Test Shock"])
    scenario.mana(P0, R)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    concede(state, P2)
    run_script(state, cast(shock, P0))
    assert target_options(state) == (PlayerOption(P0), PlayerOption(P1))


def test_601_2c_a_spell_with_no_legal_target_isnt_offered() -> None:
    """With no creature on the battlefield Swords to Plowshares can't be cast (601.2c), so it
    isn't offered; Chandra's Ignition ("target creature you control") isn't offered while only
    an opponent controls a creature. Test Shock always can target a player."""
    scenario = Scenario(2)
    _, _, shock = scenario.hand(P0, ["Swords to Plowshares", "Chandra's Ignition", "Test Shock"])
    scenario.graveyard(P0, ["Grizzly Bears"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    assert [o.object for o in casts(state)] == [shock]

    scenario = Scenario(2)
    swords, _, shock = scenario.hand(
        P0, ["Swords to Plowshares", "Chandra's Ignition", "Test Shock"]
    )
    scenario.battlefield(P1, ["Savannah Lions"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    assert [o.object for o in casts(state)] == [swords, shock]


def test_601_2c_a_single_legal_target_isnt_asked() -> None:
    """With one creature on the battlefield, Swords to Plowshares's target is chosen without a
    question: the only legal choice (601.2c). It is recorded on the spell and logged."""
    scenario = Scenario(2)
    (swords,) = scenario.hand(P0, ["Swords to Plowshares"])
    (lions,) = scenario.battlefield(P1, ["Savannah Lions"])
    scenario.mana(P0, W)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(swords, P0))
    (spell,) = state.stack
    record = state.objects[spell].spell
    assert record is not None and record.targets == ((TargetObject(lions),),)
    assert not any(
        isinstance(r, AnswerRecord) and r.kind is DecisionKind.CHOOSE_TARGETS
        for r in records(state, AnswerRecord)
    )
    (became,) = records(state, BecameTargets)
    assert (became.spell, became.targets) == (spell, ((TargetObject(lions),),))
    assert became.rules[0] == "601.2c"
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION  # cast, P0 has priority


def test_601_2c_becoming_a_target_is_logged_publicly() -> None:
    """The targets are announced (601.2c): the other player sees ``BecameTargets`` and the
    spell's record with its targets, but not the caster's answer."""
    scenario = Scenario(2)
    (shock,) = scenario.hand(P0, ["Test Shock"])
    scenario.mana(P0, R)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(shock, P0), choose_targets(PlayerOption(P1)))
    view = view_for(state, P1)
    logged = [entry.record for entry in view.log]
    assert any(isinstance(r, BecameTargets) and r.targets == ((TargetPlayer(P1),),) for r in logged)
    assert not any(
        isinstance(r, AnswerRecord) and r.kind is DecisionKind.CHOOSE_TARGETS for r in logged
    )
    (spell_view,) = view.stack
    assert spell_view.spell is not None
    assert spell_view.spell.targets == ((TargetPlayer(P1),),)


def _with(
    records: Sequence[Mapping[str, object]], definitions: list[CardDefinition]
) -> tuple[CardDatabase, CardRegistry]:
    """The scenario cards plus these invented ones."""
    base = scenario_registry()
    registry = CardRegistry([*(base.get(n) for n in base.names()), *definitions])
    cards = [*scenario_database().cards(), *parse_oracle_cards(records)]
    return CardDatabase(cards), registry


def _pair_registry() -> tuple[CardDatabase, CardRegistry]:
    """Test Twin Shatter, invented: "Destroy two target artifacts." One instance of "target"
    that chooses two."""
    record = fx.spell("Test Twin Shatter", "{R}", 1.0, "Instant", ["R"], "Destroy two target "
                      "artifacts.")  # fmt: skip
    definition = CardDefinition(
        "Test Twin Shatter",
        spell=SpellAbility(
            (
                Mode(
                    (TargetSpec(ObjectFilter((CardType.ARTIFACT,)), minimum=2, maximum=2),),
                    (Destroy((TargetRef(0),)),),
                ),
            )
        ),
    )
    return _with([record], [definition])


def test_115_3_one_instance_cant_choose_the_same_object_twice() -> None:
    """ "Destroy two target artifacts": the two must be different artifacts (115.3), so an answer
    naming one twice is refused; with exactly two artifacts both are chosen without asking, and
    with a single artifact the spell isn't offered."""
    database, registry = _pair_registry()
    scenario = Scenario(2, database=database, registry=registry)
    (twin,) = scenario.hand(P0, ["Test Twin Shatter"])
    ring, signet, other = scenario.battlefield(P1, ["Sol Ring", "Arcane Signet", "Sol Ring"])
    scenario.mana(P0, R)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(twin, P0))
    assert target_options(state) == (ObjectOption(ring), ObjectOption(signet), ObjectOption(other))
    space = request_of(state).space
    assert isinstance(space, ChooseSubset) and (space.minimum, space.maximum) == (2, 2)
    with pytest.raises(InvalidAnswer):
        submit(state, answer(state, PickMany((0, 0))))
    run_script(state, choose_targets(ring, signet))
    (spell,) = state.stack
    record = state.objects[spell].spell
    assert record is not None
    assert record.targets == ((TargetObject(ring), TargetObject(signet)),)

    scenario = Scenario(2, database=database, registry=registry)
    (twin,) = scenario.hand(P0, ["Test Twin Shatter"])
    ring, signet = scenario.battlefield(P1, ["Sol Ring", "Arcane Signet"])
    scenario.mana(P0, R)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(twin, P0))
    (spell,) = state.stack
    record = state.objects[spell].spell
    assert record is not None
    assert record.targets == ((TargetObject(ring), TargetObject(signet)),)

    scenario = Scenario(2, database=database, registry=registry)
    scenario.hand(P0, ["Test Twin Shatter"])
    scenario.battlefield(P1, ["Sol Ring"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    assert casts(scenario.build()) == []


def test_115_5_a_spell_is_an_illegal_target_for_itself() -> None:
    """A spell that targets spells can target another spell on the stack, never itself."""
    scenario = Scenario(2)
    top, below = scenario.stack(P0, ["Test Shock", "Test Ponder"])
    state = scenario.build()
    spec = TargetSpec(spells=SpellFilter())
    targeter = Targeter(P0, top, characteristics(state, top))
    assert targeting.target_problem(state, targeter, spec, TargetObject(below)) is None
    problem = targeting.target_problem(state, targeter, spec, TargetObject(top))
    assert problem is not None and "115.5" in problem.rules
    assert targeting.legal_targets(state, targeter, spec) == (TargetObject(below),)


def test_115_2_a_permanent_target_must_be_on_the_battlefield() -> None:
    """``target_problem`` refuses an object of the right type in another zone (115.2), an
    object that no longer exists (608.2b) and a player for a spec without players."""
    scenario = Scenario(2)
    (spell,) = scenario.stack(P0, ["Swords to Plowshares"])
    (bears,) = scenario.battlefield(P1, ["Grizzly Bears"])
    (dead,) = scenario.graveyard(P1, ["Savannah Lions"])
    state = scenario.build()
    spec = TargetSpec(ObjectFilter((CardType.CREATURE,)))
    targeter = Targeter(P0, spell, characteristics(state, spell))
    assert targeting.target_problem(state, targeter, spec, TargetObject(bears)) is None
    for candidate in (TargetObject(dead), TargetObject(ObjectId(bears + 100)), TargetPlayer(P1)):
        problem = targeting.target_problem(state, targeter, spec, candidate)
        assert isinstance(problem, Verdict) and not problem.allowed


def test_115_targeting_uses_one_function_at_casting_and_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Seam: replace ``targeting.target_problem`` so that P1's Grizzly Bears can't be targeted.
    Then Swords to Plowshares (a) isn't offered when the Bears are the only creature, (b) offers
    only the Lions, which it chooses without asking, and (c) on the stack targeting the Bears,
    doesn't resolve (608.2b)."""
    original = targeting.target_problem
    forbidden: list[Target] = []

    def problem(
        state: GameState, targeter: Targeter, spec: TargetSpec, candidate: Target
    ) -> Verdict | None:
        if candidate in forbidden:
            return Verdict(False, ("101.2",), "a test forbids it")
        return original(state, targeter, spec, candidate)

    monkeypatch.setattr(targeting, "target_problem", problem)

    alone = Scenario(2)
    alone.hand(P0, ["Swords to Plowshares"])
    (bears,) = alone.battlefield(P1, ["Grizzly Bears"])
    alone.at(Phase.PRECOMBAT_MAIN)
    forbidden.append(TargetObject(bears))
    assert casts(alone.build()) == []

    scenario = Scenario(2)
    (swords,) = scenario.hand(P0, ["Swords to Plowshares"])
    bears, lions = scenario.battlefield(P1, ["Grizzly Bears", "Savannah Lions"])
    scenario.mana(P0, W)
    scenario.at(Phase.PRECOMBAT_MAIN)
    forbidden[:] = [TargetObject(bears)]
    state = scenario.build()
    run_script(state, cast(swords, P0))
    (spell,) = state.stack
    record = state.objects[spell].spell
    assert record is not None and record.targets == ((TargetObject(lions),),)

    stacked = Scenario(2)
    (spell,) = stacked.stack(P0, ["Swords to Plowshares"])
    (bears,) = stacked.battlefield(P1, ["Grizzly Bears"])
    stacked.targets(spell, [TargetObject(bears)])
    stacked.at(Phase.PRECOMBAT_MAIN)
    forbidden[:] = [TargetObject(bears)]
    state = stacked.build()
    run_script(state, pass_(P0), pass_(P1))
    assert [r.spell for r in records(state, SpellDidNotResolve)] == [spell]
    assert bears in state.battlefield
    assert len(state.player(P0).graveyard) == 1
    assert state.objects[state.player(P0).graveyard[0]].zone == Zone.graveyard(P0)


def test_101_2_targeting_is_a_legality_question(monkeypatch: pytest.MonkeyPatch) -> None:
    """``target_problem`` is ``legality.allowed(TargetAction)``: a prohibition (shroud and the
    like, M2.8) wins over the rules' permission (101.2)."""
    scenario = Scenario(2)
    (spell,) = scenario.stack(P0, ["Swords to Plowshares"])
    (bears,) = scenario.battlefield(P1, ["Grizzly Bears"])
    state = scenario.build()
    spec = TargetSpec(ObjectFilter((CardType.CREATURE,)))
    targeter = Targeter(P0, spell, characteristics(state, spell))
    action = legality.TargetAction(P0, targeter, spec, TargetObject(bears))
    assert legality.allowed(state, action).allowed

    def forbid(state: GameState, action: legality.Action) -> tuple[legality.Prohibition, ...]:
        return (legality.Prohibition("702.18a", "it has shroud"),)

    monkeypatch.setattr(legality, "prohibitions", forbid)
    problem = targeting.target_problem(state, targeter, spec, TargetObject(bears))
    assert problem is not None and problem.rules == ("101.2", "702.18a")


def _glance() -> tuple[CardDatabase, CardRegistry]:
    """Test Glance, invented: "Destroy up to one target artifact. Draw a card." (115.6: it may
    choose no target)."""
    record = fx.spell("Test Glance", "{R}", 1.0, "Instant", ["R"],
                      "Destroy up to one target artifact. Draw a card.")  # fmt: skip
    definition = CardDefinition(
        "Test Glance",
        spell=SpellAbility(
            (
                Mode(
                    (TargetSpec(ObjectFilter((CardType.ARTIFACT,)), minimum=0, maximum=1),),
                    (Destroy((TargetRef(0),)), DrawCards()),
                ),
            )
        ),
    )
    return _with([record], [definition])


def test_115_6_up_to_one_target_is_asked_even_with_one_candidate() -> None:
    """ "Up to one target artifact" with one artifact: zero or one may be chosen, so the question
    is asked (minimum 0, maximum 1). Choosing none, the spell isn't targeted (115.6): it resolves
    and draws a card, and Sol Ring stays."""
    database, registry = _glance()
    scenario = Scenario(2, database=database, registry=registry)
    (glance,) = scenario.hand(P0, ["Test Glance"])
    (ring,) = scenario.battlefield(P1, ["Sol Ring"])
    scenario.library(P0, ["Forest"])
    scenario.mana(P0, R)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(glance, P0))
    assert target_options(state) == (ObjectOption(ring),)
    space = request_of(state).space
    assert isinstance(space, ChooseSubset) and (space.minimum, space.maximum) == (0, 1)
    run_script(state, choose_targets())
    (spell,) = state.stack
    record = state.objects[spell].spell
    assert record is not None and record.targets == ((),) and not record.targeted
    run_script(state, pass_(P0), pass_(P1))
    assert records(state, SpellDidNotResolve) == [] and ring in state.battlefield
    assert names(state, Zone.hand(P0)) == ["Forest"]


def test_115_6_up_to_one_target_with_none_on_the_battlefield_is_offered() -> None:
    database, registry = _glance()
    scenario = Scenario(2, database=database, registry=registry)
    (glance,) = scenario.hand(P0, ["Test Glance"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    assert [o.object for o in casts(scenario.build())] == [glance]


def test_608_2b_up_to_one_target_chosen_and_gone_doesnt_resolve() -> None:
    """Test Glance chose Sol Ring, which is gone as it resolves: it was targeted and every target
    is illegal, so it doesn't resolve and draws nothing (608.2b)."""
    database, registry = _glance()
    scenario = Scenario(2, database=database, registry=registry)
    (glance,) = scenario.stack(P0, ["Test Glance"])
    (ring,) = scenario.battlefield(P1, ["Sol Ring"])
    scenario.targets(glance, [TargetObject(ring)])
    (shatter,) = scenario.stack(P1, ["Test Shatter"])
    scenario.targets(shatter, [TargetObject(ring)])
    scenario.library(P0, ["Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1), pass_(P0), pass_(P1))
    assert [r.spell for r in records(state, SpellDidNotResolve)] == [glance]
    assert state.player(P0).hand == []


def test_115_4_any_target_includes_a_planeswalker() -> None:
    walker = {**fx.spell("Test Walker", "{2}", 2.0, "Planeswalker — Test", []), "loyalty": "3"}
    database, registry = _with([walker], [CardDefinition("Test Walker")])
    scenario = Scenario(2, database=database, registry=registry)
    (shock,) = scenario.hand(P0, ["Test Shock"])
    (planeswalker,) = scenario.battlefield(P1, ["Test Walker"])
    scenario.mana(P0, R)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(shock, P0))
    assert target_options(state) == (
        ObjectOption(planeswalker),
        PlayerOption(P0),
        PlayerOption(P1),
    )
