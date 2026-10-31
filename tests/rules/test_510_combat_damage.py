"""510: the combat damage step, for unblocked attackers (M3.2).

From the pinned CR:

- 510.1a: each attacking creature assigns combat damage equal to its power; one that would
  assign 0 or less assigns none.
- 510.1b: an unblocked creature assigns its combat damage to the player it attacks.
- 510.1c: a blocked creature with no creature blocking it any more assigns no combat damage; one
  with blockers assigns it to them (M3.3: a gap until then, as is 510.1d, blockers' damage).
- 510.2: all combat damage that has been assigned is dealt simultaneously: one set of events,
  ``DamageDealt`` with ``combat=True``, one per source (120.4b).
- 120.3a: damage dealt to a player makes them lose that much life; 704.5a: a player with 0 or
  less life loses the game.
- 800.4e: combat damage that would be assigned to a player who has left the game isn't
  assigned.
- 903.10a: a player dealt 21 or more combat damage by the same commander loses. Commander damage
  isn't tallied until M7, so combat damage from a commander to a player is a gap.
"""

from __future__ import annotations

import pytest

from resolve.engine.concede import concede
from resolve.errors import NotImplementedRule
from resolve.events import pipeline
from resolve.events.base import Event
from resolve.events.damage import DamageDealt
from resolve.events.game import PlayerLost
from resolve.state.config import GameConfig
from resolve.state.game import GameState
from resolve.state.ids import PlayerId
from resolve.state.turn import Phase, Step
from resolve.state.zones import BATTLEFIELD
from resolve.tasks import TaskResult
from tests.casting_support import records
from tests.combat_support import declare_attackers, pass_to
from tests.scenario import Scenario

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)


def test_510_1b_an_unblocked_attacker_deals_its_power_to_the_player() -> None:
    """Hill Giant (3/3) attacks P1 and isn't blocked: it deals 3 combat damage to P1, 20 -> 17
    (510.1a-b, 120.3a)."""
    scenario = Scenario(2)
    (giant,) = scenario.battlefield(P0, ["Hill Giant"])
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    declare_attackers(state, {giant: P1})
    pass_to(state, Phase.POSTCOMBAT_MAIN)
    (dealt,) = records(state, DamageDealt)
    assert (dealt.source, dealt.to_players, dealt.to_objects) == (giant, ((P1, 3),), ())
    assert dealt.combat
    assert "510.2" in dealt.rules
    assert state.player(P1).life == 17 and state.player(P0).life == 20


def test_510_1a_a_creature_with_0_power_deals_no_damage() -> None:
    """Darksteel Myr (0/1) attacks: it assigns no combat damage (510.1a), so no damage event."""
    scenario = Scenario(2)
    (myr,) = scenario.battlefield(P0, ["Darksteel Myr"])
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    declare_attackers(state, {myr: P1})
    pass_to(state, Phase.POSTCOMBAT_MAIN)
    assert records(state, DamageDealt) == []
    assert state.player(P1).life == 20


def test_510_2_combat_damage_is_dealt_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Grizzly Bears and Hill Giant attack P1: their damage is one set of simultaneous events,
    one ``DamageDealt`` per source in declaration order (510.2, 120.4b), 20 -> 15."""
    batches: list[tuple[Event, ...]] = []
    run = pipeline.ApplyEvents.run

    def spy(self: pipeline.ApplyEvents, state: GameState) -> TaskResult:
        batches.append(self.events)
        return run(self, state)

    monkeypatch.setattr(pipeline.ApplyEvents, "run", spy)
    scenario = Scenario(2)
    bears, giant = scenario.battlefield(P0, ["Grizzly Bears", "Hill Giant"])
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    declare_attackers(state, {bears: P1, giant: P1})
    pass_to(state, Phase.POSTCOMBAT_MAIN)
    damage = [batch for batch in batches if any(isinstance(e, DamageDealt) for e in batch)]
    assert len(damage) == 1
    (batch,) = damage
    assert all(isinstance(event, DamageDealt) and event.combat for event in batch)
    assert [(e.source, e.to_players) for e in batch if isinstance(e, DamageDealt)] == [
        (bears, ((P1, 2),)),
        (giant, ((P1, 3),)),
    ]
    assert state.player(P1).life == 15


def test_704_5a_combat_damage_ends_the_game() -> None:
    """P1 at 3 life is dealt 3 by Hill Giant: 704.5a, they lose and P0 wins (104.2a)."""
    scenario = Scenario(2)
    (giant,) = scenario.battlefield(P0, ["Hill Giant"])
    scenario.life(P1, 3)
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    declare_attackers(state, {giant: P1})
    pass_to(state, Phase.POSTCOMBAT_MAIN)
    assert state.result is not None
    (lost,) = records(state, PlayerLost)
    assert lost.player == P1 and lost.rules[0] == "704.5a"
    assert state.result.winners == (P0,)


def test_800_4e_damage_to_a_player_who_left_isnt_assigned() -> None:
    """Three players: Grizzly Bears attacks P1 and Hill Giant P2. P1 concedes in the declare
    attackers step: the Bears stay attacking (P1's leaving doesn't remove them from combat) but
    their damage to P1 isn't assigned (800.4e); the Giant deals 3 to P2."""
    scenario = Scenario(3)
    bears, giant = scenario.battlefield(P0, ["Grizzly Bears", "Hill Giant"])
    scenario.at(Step.DECLARE_ATTACKERS, begin=True)
    state = scenario.build()
    declare_attackers(state, {bears: P1, giant: P2})
    concede(state, P1)
    turn = state.turn
    assert turn is not None and turn.combat is not None and bears in turn.combat.attackers
    pass_to(state, Phase.POSTCOMBAT_MAIN)
    (dealt,) = records(state, DamageDealt)
    assert (dealt.source, dealt.to_players) == (giant, ((P2, 3),))
    assert state.player(P2).life == 17


def test_510_1c_a_blocked_attacker_whose_blockers_left_deals_no_damage() -> None:
    """Grizzly Bears was blocked by Test Wall, which has left combat (removed from the combat
    state as the scenario is set up): the Bears stay blocked (509.1h) and, with no creature
    blocking them, assign no combat damage (510.1c). Hill Giant, unblocked, deals its 3."""
    scenario = Scenario(2)
    bears, giant = scenario.battlefield(P0, ["Grizzly Bears", "Hill Giant"])
    (wall,) = scenario.battlefield(P1, ["Test Wall"])
    scenario.at(Step.COMBAT_DAMAGE, begin=True)
    scenario.attacking(P1, bears, giant)
    scenario.blocking(wall, bears)
    turn = scenario._state.turn  # pyright: ignore[reportPrivateUsage]
    assert turn is not None and turn.combat is not None
    del turn.combat.blockers[wall]
    state = scenario.build()
    assert [(e.source, e.to_players) for e in records(state, DamageDealt)] == [(giant, ((P1, 3),))]
    assert state.player(P1).life == 17


def test_510_1c_damage_with_blockers_is_a_gap_until_m3_3() -> None:
    """A blocked attacker with a blocker assigns its damage to it (510.1c) and the blocker
    assigns its own (510.1d): M3.3's, a gap until then."""
    scenario = Scenario(2)
    (bears,) = scenario.battlefield(P0, ["Grizzly Bears"])
    (wall,) = scenario.battlefield(P1, ["Test Wall"])
    scenario.at(Step.COMBAT_DAMAGE, begin=True)
    scenario.attacking(P1, bears)
    scenario.blocking(wall, bears)
    with pytest.raises(NotImplementedRule) as gap:
        scenario.build()
    assert gap.value.rule == "510.1c"


def test_903_10a_combat_damage_from_a_commander_is_a_gap_until_m7() -> None:
    """In a Commander game P0's commander, Grizzly Bears, attacks P1 unblocked: the combat
    damage it would deal to P1 must be tallied for 903.10a, which is M7's, so it is a gap. A
    creature that isn't a commander deals its damage as normal in the same game."""
    scenario = Scenario(2, config=GameConfig.commander_game())
    commander = scenario.commander(P0, "Grizzly Bears", zone=BATTLEFIELD)
    scenario.at(Step.COMBAT_DAMAGE, begin=True)
    scenario.attacking(P1, commander)
    with pytest.raises(NotImplementedRule) as gap:
        scenario.build()
    assert gap.value.rule == "903.10a"

    scenario = Scenario(2, config=GameConfig.commander_game())
    scenario.commander(P0, "Grizzly Bears")
    (giant,) = scenario.battlefield(P0, ["Hill Giant"])
    scenario.at(Step.COMBAT_DAMAGE, begin=True)
    scenario.attacking(P1, giant)
    state = scenario.build()
    assert state.player(P1).life == 40 - 3
