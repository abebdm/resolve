"""Fiery Confluence: {2}{R}{R}, Sorcery. "Choose three. You may choose the same mode more than once.
• Fiery Confluence deals 1 damage to each creature. • Fiery Confluence deals 2 damage to each
opponent. • Destroy target artifact."

A torture test (docs/torture-tests.md): the same mode chosen more than once, each with its own
target (700.2d).

Oracle text and rulings checked against the Scryfall snapshot of 2026-10-26
(``tools/excerpts/cards.json``). The rulings (2015-11-04), and the tests for each:

1. "No player can cast spells or activate abilities in between the modes of a resolving spell."
   The modes resolve in one task, which asks nothing (``test_..._separate_events``: the Bears
   die only after the whole spell has resolved).
2. "You choose the modes as you cast the spell. Once modes are chosen, they can't be changed."
   (tests/rules/test_700_2_modes.py, ``test_700_2_modes_cant_change_after_casting``.)
3. "If a mode requires a target, you can select that mode only if there's a legal target
   available. ... Each time you select that mode, you can choose a different target, or you can
   choose the same target." (test_700_2_modes.py: the multisets offered, and the same or a
   different artifact.)
4. Copies keep the modes: copies arrive in M5 (707.10, 700.2g).
5. "... you always follow the instructions of a Confluence in the order they are written. If the
   same mode is chosen more than once, you choose their relative order as you cast the spell."
   (test_700_2_modes.py, ``test_608_2c_modes_follow_the_printed_order``; the relative order of a
   repeated mode is the order its targets are chosen, ``test_..._a_different_artifact``.)
6. "If all targets for the chosen modes become illegal before the Confluence resolves, the spell
   won't resolve and none of its effects will happen. If at least one target is still legal, the
   spell will resolve but will have no effect on any illegal targets." (608.2b, below.)
7. "If the first or second modes are chosen multiple times, each of those modes represents a
   separate damage-dealing event." (Below.)
"""

from __future__ import annotations

from pathlib import Path

from resolve.cards.definitions.removal import FIERY_CONFLUENCE
from resolve.cards.registry import default_registry
from resolve.data.cards import load_card_excerpt
from resolve.events.damage import DamageDealt
from resolve.events.permanents import PermanentDestroyed
from resolve.events.spells import SpellDidNotResolve, SpellResolved
from resolve.state.game import GameState
from resolve.state.ids import PlayerId
from resolve.state.spell import TargetObject
from resolve.state.turn import Step
from tests.casting_support import pass_, records
from tests.scenario import Scenario, run_script

P0, P1, P2, P3 = PlayerId(0), PlayerId(1), PlayerId(2), PlayerId(3)
EXCERPT = Path(__file__).resolve().parents[2] / "tools" / "excerpts" / "cards.json"
NAME = "Fiery Confluence"


def test_its_definition_is_its_oracle_text() -> None:
    """The definition's text is the Oracle text, with "this spell" where the card names itself
    (201.5)."""
    assert default_registry().get(NAME) is FIERY_CONFLUENCE
    card = load_card_excerpt(EXCERPT).get(NAME)
    oracle = card.faces[0].oracle_text
    assert FIERY_CONFLUENCE.spell is not None
    assert FIERY_CONFLUENCE.spell.text == oracle.replace(
        "Fiery Confluence deals", "This spell deals"
    )
    assert (card.faces[0].mana_cost, card.type_line) == ("{2}{R}{R}", "Sorcery")


def _resolve_all(state: GameState, players: int = 2) -> None:
    """Every player passes in turn order until the stack is empty (117.4, 608.1)."""
    while state.stack:
        run_script(state, *(pass_(PlayerId(p)) for p in range(players)))


def test_fiery_confluence_repeated_damage_modes_are_separate_events() -> None:
    """Modes (1 damage to each creature, twice; 2 damage to each opponent): two DamageDealt of 1
    to every creature, then one of 2 to the opponent. Grizzly Bears (2/2) has lethal damage only
    once the spell has resolved, and dies then (704.5g); Test Wall (0/4) survives with 2 damage."""
    scenario = Scenario(2)
    (confluence,) = scenario.stack(P0, [NAME])
    scenario.modes(confluence, 0, 0, 1)
    bears, wall = scenario.battlefield(P1, ["Grizzly Bears", "Test Wall"])
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    life = state.player(P1).life
    run_script(state, pass_(P0), pass_(P1))
    damage = records(state, DamageDealt)
    assert [(d.to_objects, d.to_players) for d in damage] == [
        (((bears, 1), (wall, 1)), ()),
        (((bears, 1), (wall, 1)), ()),
        ((), ((P1, 2),)),
    ]
    assert all(d.source == confluence for d in damage)
    log = [e.record for e in state.event_log]
    resolved = next(i for i, r in enumerate(log) if isinstance(r, SpellResolved))
    destroyed = next(i for i, r in enumerate(log) if isinstance(r, PermanentDestroyed))
    assert resolved < destroyed and records(state, PermanentDestroyed)[0].obj == bears
    assert state.battlefield == [wall] and state.objects[wall].damage == 2
    assert state.player(P1).life == life - 2
    assert state.player(P0).life == life


def test_608_2b_every_target_illegal_means_no_effect_at_all() -> None:
    """Modes (1 damage to each creature, twice; destroy target artifact), targeting Sol Ring. Test
    Shatter destroys Sol Ring in response: Fiery Confluence's only target is illegal, so it
    doesn't resolve and none of its effects happen (608.2b, ruling 6), not even the damage."""
    scenario = Scenario(2)
    (confluence,) = scenario.stack(P0, [NAME])
    (shatter,) = scenario.stack(P1, ["Test Shatter"])  # cast in response: on top
    (ring,) = scenario.battlefield(P1, ["Sol Ring"])
    (bears,) = scenario.battlefield(P0, ["Grizzly Bears"])
    scenario.modes(confluence, 0, 0, 2).targets(confluence, [TargetObject(ring)])
    scenario.targets(shatter, [TargetObject(ring)])
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    assert state.stack == [confluence, shatter]
    _resolve_all(state)
    assert [r.obj for r in records(state, PermanentDestroyed)] == [ring]
    assert records(state, DamageDealt) == []
    (failed,) = records(state, SpellDidNotResolve)
    assert failed.spell == confluence
    assert state.objects[bears].damage == 0


def test_608_2b_one_legal_target_is_enough() -> None:
    """Modes (1 damage to each creature; destroy target artifact, twice), targeting Sol Ring and
    Selesnya Signet. Test Shatter destroys Sol Ring in response: one target is still legal, so
    the spell resolves (608.2b, ruling 6): the damage is dealt and the Signet destroyed, while
    the instance whose target is gone does nothing."""
    scenario = Scenario(2)
    (confluence,) = scenario.stack(P0, [NAME])
    (shatter,) = scenario.stack(P1, ["Test Shatter"])  # cast in response: on top
    ring, signet = scenario.battlefield(P1, ["Sol Ring", "Selesnya Signet"])
    (wall,) = scenario.battlefield(P0, ["Test Wall"])
    scenario.modes(confluence, 0, 2, 2)
    scenario.targets(confluence, [TargetObject(ring)], [TargetObject(signet)])
    scenario.targets(shatter, [TargetObject(ring)])
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    _resolve_all(state)
    assert [r.obj for r in records(state, PermanentDestroyed)] == [ring, signet]
    (damage,) = records(state, DamageDealt)
    assert damage.to_objects == ((wall, 1),)
    assert not records(state, SpellDidNotResolve)
    assert len(records(state, SpellResolved)) == 2


def test_115_6_without_targeted_modes_it_isnt_targeted() -> None:
    """Modes (2 damage to each opponent, three times) choose no target, so the spell isn't
    targeted (115.6) and 608.2b can't stop it."""
    scenario = Scenario(2)
    (confluence,) = scenario.stack(P0, [NAME])
    scenario.modes(confluence, 1, 1, 1)
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    life = state.player(P1).life
    _resolve_all(state)
    assert state.player(P1).life == life - 6
    assert len(records(state, DamageDealt)) == 3


def test_fiery_confluence_each_opponent_in_multiplayer() -> None:
    """Four players; P0's Fiery Confluence with "2 damage to each opponent" three times: three
    damage events, each dealing 2 to every opponent (102.2), so each is down 6; P0 isn't dealt
    any."""
    scenario = Scenario(4)
    (confluence,) = scenario.stack(P0, [NAME])
    scenario.modes(confluence, 1, 1, 1)
    scenario.at(Step.UPKEEP)
    state = scenario.build()
    life = state.player(P0).life
    _resolve_all(state, players=4)
    damage = records(state, DamageDealt)
    assert [d.to_players for d in damage] == [((P1, 2), (P2, 2), (P3, 2))] * 3
    assert [state.player(p).life for p in (P0, P1, P2, P3)] == [life, life - 6, life - 6, life - 6]
