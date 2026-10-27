"""702.8: flash.

From the pinned CR:

- 702.8a: flash is a static ability that functions in any zone from which you could play the
  card it's on. "Flash" means "You may play this card any time you could cast an instant."
  (117.1a, 304.1: an instant may be cast whenever its caster has priority.)
- 702.8b: multiple instances of flash on the same object are redundant.

Flash changes the timing (``defaults.may_cast_now``), never the zones a card may be cast from
(``defaults.cast_permissions``): a card in the graveyard isn't castable just because it has flash.
"""

from __future__ import annotations

from resolve.decisions.spaces import CastSpellOption
from resolve.events.spells import PermanentSpellResolved
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import ManaType
from resolve.state.spell import FROM_HAND, NORMAL, TargetPlayer
from resolve.state.turn import Phase, Step
from tests.casting_support import cast, options, pass_, records
from tests.game_fixtures import request_of
from tests.scenario import Scenario, run_script

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)
G = ManaType.GREEN


def castable(state: GameState) -> list[ObjectId]:
    """The cards the player with priority may begin to cast now."""
    return [o.object for o in options(state) if isinstance(o, CastSpellOption)]


def test_702_8a_a_flash_creature_can_be_cast_any_time_you_could_cast_an_instant() -> None:
    """P0 holds Ashcoat Bear (flash) and Grizzly Bears. The Ashcoat Bear is offered whenever P0
    has priority, as an instant would be (702.8a, 117.1a): in P1's upkeep, in P0's beginning of
    combat, and in P0's main phase with a spell on the stack (in response). Grizzly Bears, a
    creature without flash, never is at those times (302.1, 307.1: sorcery timing)."""
    # P1's upkeep: P1 passes, P0 receives priority.
    scenario = Scenario(2)
    ashcoat, _ = scenario.hand(P0, ["Ashcoat Bear", "Grizzly Bears"])
    scenario.at(Step.UPKEEP, active=P1, priority=P0, passed=[P1])
    state = scenario.build()
    assert request_of(state).player == P0
    assert castable(state) == [ashcoat]

    # P0's beginning of combat.
    scenario = Scenario(2)
    ashcoat, _ = scenario.hand(P0, ["Ashcoat Bear", "Grizzly Bears"])
    scenario.at(Step.BEGINNING_OF_COMBAT)
    state = scenario.build()
    assert castable(state) == [ashcoat]

    # In response: P0's main phase, with P1's Test Shock on the stack.
    scenario = Scenario(3)
    ashcoat, _ = scenario.hand(P0, ["Ashcoat Bear", "Grizzly Bears"])
    (shock,) = scenario.stack(P1, ["Test Shock"])
    scenario.targets(shock, [TargetPlayer(P0)])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    assert castable(state) == [ashcoat]


def test_702_8a_flash_still_allows_main_phase_casting() -> None:
    """Flash adds times the card may be cast; it takes none away: in P0's own main phase with an
    empty stack both creatures are offered."""
    scenario = Scenario(2)
    ashcoat, bears = scenario.hand(P0, ["Ashcoat Bear", "Grizzly Bears"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    assert castable(state) == [ashcoat, bears]


def test_702_8a_a_flash_permanent_spell_resolves_onto_the_battlefield() -> None:
    """Cast in P1's upkeep, Ashcoat Bear is still a creature spell: it resolves into a creature
    on the battlefield under P0's control (608.3a), not into the graveyard as an instant would."""
    scenario = Scenario(2)
    (ashcoat,) = scenario.hand(P0, ["Ashcoat Bear"])
    scenario.mana(P0, G, G)
    scenario.at(Step.UPKEEP, active=P1, priority=P0, passed=[P1])
    state = scenario.build()
    run_script(state, cast(ashcoat, P0), pass_(P0), pass_(P1))
    (resolved,) = records(state, PermanentSpellResolved)
    assert resolved.permanent is not None and state.battlefield == [resolved.permanent]
    permanent = state.objects[resolved.permanent]
    assert permanent.controller == P0
    assert state.card_of(permanent).data.name == "Ashcoat Bear"
    assert state.player(P0).graveyard == []


def test_702_8a_flash_gives_no_permission_to_cast_from_the_graveyard() -> None:
    """Ashcoat Bear in P0's graveyard isn't offered, at instant speed or in P0's main phase:
    flash says when a card may be cast, not from where (601.3, 702.8a)."""
    for where in (Step.UPKEEP, Phase.PRECOMBAT_MAIN):
        scenario = Scenario(2)
        scenario.graveyard(P0, ["Ashcoat Bear"])
        scenario.at(where)
        state = scenario.build()
        assert castable(state) == []


def test_702_8b_two_instances_are_redundant() -> None:
    """Test Twin Flash has flash twice: it is offered once (one option per permission and
    variant), at instant speed, exactly as with one instance (702.8b)."""
    scenario = Scenario(2)
    (twin,) = scenario.hand(P0, ["Test Twin Flash"])
    scenario.at(Step.UPKEEP, active=P1, priority=P0, passed=[P1])
    state = scenario.build()
    assert [o for o in options(state) if isinstance(o, CastSpellOption)] == [
        CastSpellOption(twin, NORMAL, FROM_HAND)
    ]
