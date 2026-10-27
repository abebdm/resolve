"""702.18: shroud.

From the pinned CR:

- 702.18a: "Shroud" means "This permanent or player can't be the target of spells or
  abilities." Unlike hexproof (702.11b), that includes its controller's.
- 115.10: an effect that doesn't say "target" doesn't target, so shroud doesn't stop it.
"""

from __future__ import annotations

from resolve.decisions.spaces import CastSpellOption, ObjectOption
from resolve.events.damage import DamageDealt
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import ManaType
from resolve.state.spell import TargetObject
from resolve.state.turn import Phase
from tests.casting_support import cast, options, pass_, records, target_choices
from tests.scenario import Scenario, run_script

P0, P1 = PlayerId(0), PlayerId(1)
W, R = ManaType.WHITE, ManaType.RED


def castable(state: GameState) -> list[ObjectId]:
    return [o.object for o in options(state) if isinstance(o, CastSpellOption)]


def test_702_18a_no_one_can_target_it() -> None:
    """Humble Budoka (shroud), controlled by P0. P1's Swords to Plowshares offers only Grizzly
    Bears; P0's own Swords too. P0's Chandra's Ignition ("target creature you control") isn't
    offered while the Budoka is P0's only creature, and offers only the Bears beside it."""
    for caster in (P1, P0):
        scenario = Scenario(2)
        _, bears = scenario.battlefield(P0, ["Humble Budoka", "Grizzly Bears"])
        (swords,) = scenario.hand(caster, ["Swords to Plowshares"])
        scenario.mana(caster, W)
        scenario.at(Phase.PRECOMBAT_MAIN, active=caster)
        state = scenario.build()
        run_script(state, cast(swords, caster))
        assert target_choices(state) == (ObjectOption(bears),)

    scenario = Scenario(2)
    scenario.battlefield(P0, ["Humble Budoka"])
    scenario.hand(P0, ["Chandra's Ignition"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    assert castable(state) == []

    scenario = Scenario(2)
    _, bears = scenario.battlefield(P0, ["Humble Budoka", "Grizzly Bears"])
    (ignition,) = scenario.hand(P0, ["Chandra's Ignition"])
    scenario.mana(P0, R, R, R, R, R)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(ignition, P0))
    assert target_choices(state) == (ObjectOption(bears),)


def test_702_18a_untargeted_effects_still_apply() -> None:
    """P0's Chandra's Ignition, targeting P0's Grizzly Bears, deals 2 damage to each other
    creature: the Humble Budoka (P0's) and P1's Savannah Lions, neither targeted (115.10)."""
    scenario = Scenario(2)
    (ignition,) = scenario.stack(P0, ["Chandra's Ignition"])
    bears, budoka = scenario.battlefield(P0, ["Grizzly Bears", "Humble Budoka"])
    (lions,) = scenario.battlefield(P1, ["Savannah Lions"])
    scenario.targets(ignition, [TargetObject(bears)])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1))
    (damage,) = records(state, DamageDealt)
    assert damage.source == bears and damage.to_objects == ((budoka, 2), (lions, 2))
