"""702.11: hexproof, and "hexproof from [quality]".

From the pinned CR:

- 702.11b: "Hexproof" on a permanent means "This permanent can't be the target of spells or
  abilities your opponents control."
- 702.11c: on a player, "You can't be the target of spells or abilities your opponents
  control."
- 702.11d: "hexproof from [quality]" on a permanent: "This permanent can't be the target of
  [quality] spells your opponents control or abilities your opponents control from [quality]
  sources."
- 608.2b: as a spell resolves, a target that can no longer legally be chosen is illegal.
- 113.6: a permanent's abilities function only on the battlefield; on the stack a creature spell
  with hexproof can still be targeted (by Cancel).

The prohibitions are judged by ``targeting.target_problem`` (``legality.allowed(TargetAction)``),
so a spell that couldn't choose a legal target isn't offered (601.2c).
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from resolve.agents.scripted import ScriptError
from resolve.cards.keywords import ColorQuality, Hexproof, Shroud
from resolve.cards.primitives.base import Ability
from resolve.cards.primitives.targets import TargetSpec
from resolve.cards.primitives.words import ColorWord
from resolve.data.types import Color
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import CastSpellOption, ObjectOption, PickMany, PlayerOption
from resolve.effects.characteristics import characteristics
from resolve.engine.api import submit
from resolve.errors import InvalidAnswer, NotImplementedRule
from resolve.events.damage import DamageDealt
from resolve.events.spells import SpellDidNotResolve
from resolve.rules import legality, targeting
from resolve.rules.legality import Targeter
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import ManaType
from resolve.state.spell import TargetObject, TargetPlayer
from resolve.state.turn import Phase
from resolve.state.zones import Zone
from tests.casting_support import cast, choose_targets, options, pass_, records, target_choices
from tests.game_fixtures import answer, request_of
from tests.scenario import Scenario, names, run_script
from tests.seams import patch

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)
W, R = ManaType.WHITE, ManaType.RED


def castable(state: GameState) -> list[ObjectId]:
    return [o.object for o in options(state) if isinstance(o, CastSpellOption)]


@pytest.mark.parametrize("players", [2, 3])
def test_702_11b_opponents_spells_cant_target_it(players: int) -> None:
    """P0 controls Gladecover Scout; P1, an opponent, casts Swords to Plowshares. With Grizzly
    Bears also out, only the Bears is offered (702.11b). In three players, P2 (also P0's
    opponent) can't target it either. When the Scout is the only creature, Swords isn't offered at
    all (601.2c: no legal target)."""
    for caster in [P1] if players == 2 else [P1, P2]:
        scenario = Scenario(players)
        (scout,) = scenario.battlefield(P0, ["Gladecover Scout"])
        (bears,) = scenario.battlefield(P0, ["Grizzly Bears"])
        (swords,) = scenario.hand(caster, ["Swords to Plowshares"])
        scenario.mana(caster, W)
        scenario.at(Phase.PRECOMBAT_MAIN, active=caster)
        state = scenario.build()
        run_script(state, cast(swords, caster))
        assert target_choices(state) == (ObjectOption(bears),)
        verdict = targeting.target_problem(
            state, Targeter(caster, state.stack[0], characteristics(state, state.stack[0])),
            _spec(state), TargetObject(scout),
        )  # fmt: skip
        assert verdict is not None and "702.11b" in verdict.rules and "101.2" in verdict.rules

        scenario = Scenario(players)
        scenario.battlefield(P0, ["Gladecover Scout"])
        scenario.hand(caster, ["Swords to Plowshares"])
        scenario.at(Phase.PRECOMBAT_MAIN, active=caster)
        state = scenario.build()
        assert castable(state) == []


def _spec(state: GameState) -> TargetSpec:
    """The one instance of "target" of the spell on the bottom of the stack."""
    ability = characteristics(state, state.stack[0]).spell_ability
    assert ability is not None
    return ability.modes[0].targets[0]


def test_702_11b_its_controller_can_target_it() -> None:
    """P0's own Swords to Plowshares may target P0's Gladecover Scout: hexproof stops only
    opponents (702.11b)."""
    scenario = Scenario(2)
    (scout,) = scenario.battlefield(P0, ["Gladecover Scout"])
    (swords,) = scenario.hand(P0, ["Swords to Plowshares"])
    scenario.mana(P0, W)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(swords, P0))
    assert target_choices(state) == (ObjectOption(scout),)


def test_702_11b_untargeted_effects_still_apply() -> None:
    """Hexproof stops targeting only. P1's Fiery Confluence (1 damage to each creature, three
    times) kills P0's Gladecover Scout; P1's Chandra's Ignition, targeting P1's Hill Giant, deals
    3 damage to each other creature, the Scout included."""
    scenario = Scenario(2)
    (confluence,) = scenario.stack(P1, ["Fiery Confluence"])
    scenario.modes(confluence, 0, 0, 0)
    (scout,) = scenario.battlefield(P0, ["Gladecover Scout"])
    scenario.at(Phase.PRECOMBAT_MAIN, active=P1)
    state = scenario.build()
    run_script(state, pass_(P1), pass_(P0))
    damage = records(state, DamageDealt)
    assert [d.to_objects for d in damage] == [((scout, 1),)] * 3
    assert scout not in state.objects
    assert names(state, Zone.graveyard(P0)) == ["Gladecover Scout"]  # 704.5g

    scenario = Scenario(2)
    (ignition,) = scenario.stack(P1, ["Chandra's Ignition"])
    (giant,) = scenario.battlefield(P1, ["Hill Giant"])
    (scout,) = scenario.battlefield(P0, ["Gladecover Scout"])
    scenario.targets(ignition, [TargetObject(giant)])
    scenario.at(Phase.PRECOMBAT_MAIN, active=P1)
    state = scenario.build()
    run_script(state, pass_(P1), pass_(P0))
    (damage,) = records(state, DamageDealt)
    assert damage.source == giant and damage.to_objects == ((scout, 3),)


def test_702_11d_hexproof_from_red() -> None:
    """Test Redproof Bear (hexproof from red), controlled by P0. P1's Test Shock (red) can't
    target it; P1's Swords to Plowshares (white) can; P0's own Test Shock can (702.11d: only
    [quality] spells *opponents* control)."""
    scenario = Scenario(2)
    (bear,) = scenario.battlefield(P0, ["Test Redproof Bear"])
    (shock,) = scenario.hand(P1, ["Test Shock"])
    scenario.mana(P1, R)
    scenario.at(Phase.PRECOMBAT_MAIN, active=P1)
    state = scenario.build()
    run_script(state, cast(shock, P1))
    assert ObjectOption(bear) not in target_choices(state)
    assert target_choices(state) == (PlayerOption(P0), PlayerOption(P1))

    scenario = Scenario(2)
    (bear,) = scenario.battlefield(P0, ["Test Redproof Bear"])
    (swords,) = scenario.hand(P1, ["Swords to Plowshares"])
    scenario.mana(P1, W)
    scenario.at(Phase.PRECOMBAT_MAIN, active=P1)
    state = scenario.build()
    run_script(state, cast(swords, P1))
    assert target_choices(state) == (ObjectOption(bear),)

    scenario = Scenario(2)
    (bear,) = scenario.battlefield(P0, ["Test Redproof Bear"])
    (shock,) = scenario.hand(P0, ["Test Shock"])
    scenario.mana(P0, R)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(shock, P0))
    assert ObjectOption(bear) in target_choices(state)


def _player_hexproof(player: PlayerId) -> Callable[[GameState, PlayerId], tuple[Ability, ...]]:
    """A replacement for ``defaults.player_abilities`` giving ``player`` hexproof."""

    def abilities(state: GameState, who: PlayerId) -> tuple[Ability, ...]:
        return (Hexproof(),) if who == player else ()

    return abilities


def test_702_11c_a_player_with_hexproof(monkeypatch: pytest.MonkeyPatch) -> None:
    """With ``defaults.player_abilities`` giving P1 hexproof (Leyline of Sanctity, M5), P0's Test
    Shock offers every creature and P0 but not P1 (702.11c); P1's own Test Shock may still target
    P1. In three players P2 is still a legal target of P0's. This is also the seam test of
    ``player_abilities``: the targeting check reads players' abilities only through it."""
    patch(monkeypatch, "player_abilities", _player_hexproof(P1))
    scenario = Scenario(3)
    (shock,) = scenario.hand(P0, ["Test Shock"])
    (bears,) = scenario.battlefield(P1, ["Grizzly Bears"])
    scenario.mana(P0, R)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(shock, P0))
    assert target_choices(state) == (ObjectOption(bears), PlayerOption(P0), PlayerOption(P2))

    scenario = Scenario(3)
    (shock,) = scenario.hand(P1, ["Test Shock"])
    scenario.mana(P1, R)
    scenario.at(Phase.PRECOMBAT_MAIN, active=P1)
    state = scenario.build()
    run_script(state, cast(shock, P1))
    assert PlayerOption(P1) in target_choices(state)


def test_608_2b_a_target_that_gained_hexproof_is_illegal() -> None:
    """P1's Swords to Plowshares already targets P0's Gladecover Scout on the stack (as if the
    Scout gained hexproof after it was targeted, which M5's grants make possible). As Swords
    resolves, the Scout can't legally be chosen any more, so it is an illegal target; Swords'
    only target is illegal, so it doesn't resolve and the Scout stays (608.2b). Interpretation:
    608.2b's "illegal target" is judged with the same rules as choosing one (601.2c), the
    target's abilities as they are on resolution."""
    scenario = Scenario(2)
    (swords,) = scenario.stack(P1, ["Swords to Plowshares"])
    (scout,) = scenario.battlefield(P0, ["Gladecover Scout"])
    scenario.targets(swords, [TargetObject(scout)])
    scenario.at(Phase.PRECOMBAT_MAIN, active=P1)
    state = scenario.build()
    life = state.player(P0).life
    run_script(state, pass_(P1), pass_(P0))
    (failed,) = records(state, SpellDidNotResolve)
    assert failed.spell == swords
    assert state.battlefield == [scout] and state.player(P0).life == life


def test_113_6_a_hexproof_creature_spell_can_be_countered() -> None:
    """On the stack Gladecover Scout's hexproof doesn't function (113.6: a permanent's abilities
    work on the battlefield; 702.11b speaks of a permanent): P1's Cancel may target P0's Scout
    spell."""
    scenario = Scenario(2)
    (scout,) = scenario.stack(P0, ["Gladecover Scout"])
    (cancel,) = scenario.hand(P1, ["Cancel"])
    scenario.mana(P1, ManaType.BLUE, ManaType.BLUE, ManaType.BLUE)
    scenario.at(Phase.PRECOMBAT_MAIN, priority=P1, passed=[P0])
    state = scenario.build()
    assert cancel in castable(state)
    run_script(state, cast(cancel, P1))
    assert target_choices(state) == (ObjectOption(scout),)


def test_702_11b_the_prohibition_is_hexproofs_rule() -> None:
    """The verdict for an opponent's target names 702.11b; for its controller there is none."""
    scenario = Scenario(2)
    (scout,) = scenario.battlefield(P0, ["Gladecover Scout"])
    (swords,) = scenario.stack(P1, ["Swords to Plowshares"])
    state = scenario.build()
    spec = _spec(state)
    chars = characteristics(state, swords)
    action = legality.TargetAction(P1, Targeter(P1, swords, chars), spec, TargetObject(scout))
    forbidden = legality.prohibitions(state, action)
    assert [p.rule for p in forbidden] == ["702.11b"]
    mine = legality.TargetAction(P0, Targeter(P0, swords, chars), spec, TargetObject(scout))
    assert legality.prohibitions(state, mine) == ()


def test_702_11b_hexproof_follows_the_controller_not_the_owner() -> None:
    """P1 controls a Gladecover Scout P0 owns. "Your opponents" are its controller's (702.11b,
    108.4): P0's Swords to Plowshares can't target it (P0 is P1's opponent), P1's can."""
    for caster, offered in ((P0, False), (P1, True)):
        scenario = Scenario(2)
        (scout,) = scenario.battlefield(P1, ["Gladecover Scout"], owner=P0)
        scenario.battlefield(P1, ["Grizzly Bears", "Savannah Lions"])
        (swords,) = scenario.hand(caster, ["Swords to Plowshares"])
        scenario.mana(caster, W)
        scenario.at(Phase.PRECOMBAT_MAIN, active=caster)
        state = scenario.build()
        run_script(state, cast(swords, caster))
        assert (ObjectOption(scout) in target_choices(state)) is offered


def test_702_11b_an_illegal_target_answer_is_rejected() -> None:
    """P1's Swords to Plowshares offers P0's Grizzly Bears and Savannah Lions, not P0's
    Gladecover Scout; an answer naming the Scout is refused (601.2c) and the question stays."""
    scenario = Scenario(2)
    scout, bears, lions = scenario.battlefield(
        P0, ["Gladecover Scout", "Grizzly Bears", "Savannah Lions"]
    )
    (swords,) = scenario.hand(P1, ["Swords to Plowshares"])
    scenario.mana(P1, W)
    scenario.at(Phase.PRECOMBAT_MAIN, active=P1)
    state = scenario.build()
    run_script(state, cast(swords, P1))
    assert target_choices(state) == (ObjectOption(bears), ObjectOption(lions))
    with pytest.raises(ScriptError):
        run_script(state, choose_targets(scout, player=P1))
    with pytest.raises(InvalidAnswer):
        submit(state, answer(state, PickMany((2,))))  # no third option: the Scout isn't one
    assert request_of(state).kind is DecisionKind.CHOOSE_TARGETS


def test_702_11d_hexproof_from_a_quality_on_a_player_is_a_gap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """702.11d defines "hexproof from [quality]" for a permanent only, and no card gives it to a
    player: with ``player_abilities`` giving P1 hexproof from red, judging P0's Test Shock
    against P1 raises the gap."""
    red = Hexproof(ColorQuality(ColorWord(Color.RED)))
    patch(monkeypatch, "player_abilities", lambda state, who: (red,) if who == P1 else ())
    scenario = Scenario(2)
    scenario.hand(P0, ["Test Shock"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    with pytest.raises(NotImplementedRule) as gap:
        scenario.build()  # priority lists the castable spells, judging their targets
    assert gap.value.rule == "702.11d"


def test_702_18a_a_player_with_shroud_and_redundant_instances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With ``player_abilities`` giving P1 shroud twice, neither P0's nor P1's own Test Shock may
    target P1 (702.18a: "permanent or player", no exception for its controller), and the two
    instances forbid it once (702.18b)."""
    patch(
        monkeypatch,
        "player_abilities",
        lambda state, who: (Shroud(), Shroud()) if who == P1 else (),
    )
    for caster in (P0, P1):
        scenario = Scenario(2)
        (shock,) = scenario.hand(caster, ["Test Shock"])
        (bears,) = scenario.battlefield(P0, ["Grizzly Bears"])
        scenario.mana(caster, R)
        scenario.at(Phase.PRECOMBAT_MAIN, active=caster)
        state = scenario.build()
        run_script(state, cast(shock, caster))
        assert target_choices(state) == (ObjectOption(bears), PlayerOption(P0))
        spell = state.stack[0]
        targeter = Targeter(caster, spell, characteristics(state, spell))
        action = legality.TargetAction(caster, targeter, _spec(state), TargetPlayer(P1))
        assert [p.rule for p in legality.prohibitions(state, action)] == ["702.18a"]
