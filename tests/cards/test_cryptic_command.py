"""Cryptic Command: {1}{U}{U}{U}, Instant. "Choose two — • Counter target spell. • Return target
permanent to its owner's hand. • Tap all creatures your opponents control. • Draw a card."

A torture test (docs/torture-tests.md): modes, countering, partial fizzling with one target gone,
returning a permanent to its owner's hand (700.2, 701.6, 608.2b, 400.3).

Oracle text and rulings checked against the Scryfall snapshot of 2026-10-26
(``tools/excerpts/cards.json``). The rulings (2017-11-17), and the tests for each:

1. "You choose both modes as you cast Cryptic Command. You must choose two different modes."
   (``test_cryptic_command_offers_two_different_legal_modes``.)
2. "Look at both chosen modes to determine how many targets Cryptic Command has, if any. If it
   has at least one target, and all its targets are illegal when it tries to resolve, then it
   won't resolve and none of its effects will happen. For example, if you choose the second and
   fourth modes, and the permanent is an illegal target when Cryptic Command tries to resolve,
   you won't draw a card." (``test_cryptic_command_both_targets_illegal_draws_nothing``; with
   one target still legal it resolves, ``test_cryptic_command_counter_and_bounce``; with no
   target at all it isn't targeted, ``test_cryptic_command_tap_and_draw_has_no_targets``.)
"""

from __future__ import annotations

from pathlib import Path

from resolve.cards.definitions.counterspells import CRYPTIC_COMMAND
from resolve.cards.registry import default_registry
from resolve.data.cards import load_card_excerpt
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import ChooseOne, ModesOption, ObjectOption
from resolve.events.cards import CardDrawn
from resolve.events.permanents import PermanentTapped
from resolve.events.spells import (
    ModesChosen,
    SpellCountered,
    SpellDidNotResolve,
    SpellResolved,
)
from resolve.state.game import GameState
from resolve.state.ids import PlayerId
from resolve.state.mana import ManaType
from resolve.state.spell import TargetObject
from resolve.state.turn import Phase
from resolve.state.zones import Zone
from tests.casting_support import answered, cast, choose_modes, pass_, records, target_choices
from tests.game_fixtures import request_of
from tests.scenario import Scenario, names, run_script

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)
EXCERPT = Path(__file__).resolve().parents[2] / "tools" / "excerpts" / "cards.json"
NAME = "Cryptic Command"
U = ManaType.BLUE


def test_its_definition_is_its_oracle_text() -> None:
    assert default_registry().get(NAME) is CRYPTIC_COMMAND
    card = load_card_excerpt(EXCERPT).get(NAME)
    assert CRYPTIC_COMMAND.spell is not None
    assert CRYPTIC_COMMAND.spell.text == card.faces[0].oracle_text
    assert (card.faces[0].mana_cost, card.type_line) == ("{1}{U}{U}{U}", "Instant")


def _resolve_all(state: GameState, players: int = 2) -> None:
    while state.stack:
        run_script(state, *(pass_(PlayerId(p)) for p in range(players)))


def test_cryptic_command_offers_two_different_legal_modes() -> None:
    """With only P1's Gladecover Scout (hexproof) and P0's Grizzly Bears on the battlefield and
    nothing else on the stack, P0 may choose two different modes among those with legal targets
    (ruling 1; 700.2a): "counter target spell" has none (115.5: not Cryptic Command itself), and
    "return target permanent" may target P0's Bears, not the Scout (702.11b)."""
    scenario = Scenario(2)
    (cryptic,) = scenario.hand(P0, [NAME])
    scenario.battlefield(P0, ["Grizzly Bears"])
    scenario.battlefield(P1, ["Gladecover Scout"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(cryptic, P0))
    request = request_of(state)
    assert request.kind is DecisionKind.CHOOSE_MODES and isinstance(request.space, ChooseOne)
    assert request.space.options == (ModesOption((1, 2)), ModesOption((1, 3)), ModesOption((2, 3)))

    # With only the Scout, the one legal choice is (tap, draw): it isn't asked (the casting
    # decisions skip a choice with one answer), and it is the spell's modes.
    scenario = Scenario(2)
    (cryptic,) = scenario.hand(P0, [NAME])
    scenario.battlefield(P1, ["Gladecover Scout"])
    scenario.mana(P0, U, U, U, U)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(cryptic, P0))
    (chosen,) = records(state, ModesChosen)
    assert chosen.modes == (2, 3) and answered(state, DecisionKind.CHOOSE_MODES) == 0


def test_cryptic_command_counter_and_bounce() -> None:
    """P0's Cryptic Command (counter target spell: P1's Grizzly Bears; return target permanent:
    P1's Savannah Lions). In response P0's Cancel counters the Bears. Cryptic Command's first
    target is gone, its second still legal, so it resolves (608.2b): the Lions return to P1's
    hand, and nothing else is countered."""
    scenario = Scenario(2)
    (bears,) = scenario.stack(P1, ["Grizzly Bears"])
    (cryptic,) = scenario.stack(P0, [NAME])
    (cancel,) = scenario.stack(P0, ["Cancel"])
    (lions,) = scenario.battlefield(P1, ["Savannah Lions"])
    scenario.modes(cryptic, 0, 1).targets(cryptic, [TargetObject(bears)], [TargetObject(lions)])
    scenario.targets(cancel, [TargetObject(bears)])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    assert state.stack == [bears, cryptic, cancel]
    _resolve_all(state)
    assert [c.spell for c in records(state, SpellCountered)] == [bears]
    assert [r.spell for r in records(state, SpellResolved)] == [cancel, cryptic]
    assert state.battlefield == [] and names(state, Zone.hand(P1)) == ["Savannah Lions"]
    assert names(state, Zone.graveyard(P0)) == ["Cancel", NAME]


def test_cryptic_command_both_targets_illegal_draws_nothing() -> None:
    """Ruling 2's example: modes "return target permanent" (P1's Sol Ring) and "draw a card". P1's
    Test Shatter destroys the Sol Ring in response; Cryptic Command's only target is illegal, so
    it doesn't resolve and P0 draws no card (608.2b). The same with counter and bounce, both
    targets gone: nothing happens."""
    scenario = Scenario(2)
    (cryptic,) = scenario.stack(P0, [NAME])
    (shatter,) = scenario.stack(P1, ["Test Shatter"])
    (ring,) = scenario.battlefield(P1, ["Sol Ring"])
    scenario.library(P0, ["Forest", "Forest"])
    scenario.modes(cryptic, 1, 3).targets(cryptic, [TargetObject(ring)])
    scenario.targets(shatter, [TargetObject(ring)])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    _resolve_all(state)
    (failed,) = records(state, SpellDidNotResolve)
    assert failed.spell == cryptic
    assert records(state, CardDrawn) == [] and state.player(P0).hand == []

    scenario = Scenario(2)
    (bears,) = scenario.stack(P1, ["Grizzly Bears"])
    (cryptic,) = scenario.stack(P0, [NAME])
    (shatter,) = scenario.stack(P1, ["Test Shatter"])
    (cancel,) = scenario.stack(P1, ["Cancel"])
    (ring,) = scenario.battlefield(P1, ["Sol Ring"])
    scenario.modes(cryptic, 0, 1).targets(cryptic, [TargetObject(bears)], [TargetObject(ring)])
    scenario.targets(shatter, [TargetObject(ring)]).targets(cancel, [TargetObject(bears)])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    _resolve_all(state)
    assert [f.spell for f in records(state, SpellDidNotResolve)] == [cryptic]
    assert [c.spell for c in records(state, SpellCountered)] == [bears]  # by Cancel alone


def test_cryptic_command_tap_and_draw_has_no_targets() -> None:
    """In three players, P0 casts Cryptic Command choosing "tap all creatures your opponents
    control" and "draw a card": no target is chosen (115.10: not targeted, 115.6), so it isn't
    asked. On resolution every untapped creature P1 and P2 control becomes tapped, P1's
    hexproof Gladecover Scout too (untargeted); P2's already tapped Hill Giant stays tapped
    without a new event (701.26a); P1's Sol Ring (not a creature) and P0's Grizzly Bears stay
    untapped; P0 draws a card."""
    scenario = Scenario(3)
    (cryptic,) = scenario.hand(P0, [NAME])
    (bears,) = scenario.battlefield(P0, ["Grizzly Bears"])
    lions, scout, ring = scenario.battlefield(
        P1, ["Savannah Lions", "Gladecover Scout", "Sol Ring"]
    )
    giant, budoka = scenario.battlefield(P2, ["Hill Giant", "Humble Budoka"])
    scenario.tap(giant)
    scenario.library(P0, ["Forest"])
    scenario.mana(P0, U, U, U, U)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(cryptic, P0), choose_modes(2, 3))
    (spell,) = state.stack
    record = state.objects[spell].spell
    assert record is not None and record.targets == () and not record.targeted
    run_script(state, pass_(P0), pass_(P1), pass_(P2))
    assert sorted(e.obj for e in records(state, PermanentTapped)) == sorted([lions, scout, budoka])
    assert all(state.objects[o].tapped for o in (lions, scout, budoka, giant))
    assert not state.objects[bears].tapped and not state.objects[ring].tapped
    assert names(state, Zone.hand(P0)) == ["Forest"]


def test_cryptic_command_bounce_goes_to_the_owners_hand() -> None:
    """In three players, P1 controls a Savannah Lions P2 owns. P0's Cryptic Command returns it to
    its owner's hand, P2's (400.3), as a new object (400.7); P0 draws a card."""
    scenario = Scenario(3)
    (cryptic,) = scenario.stack(P0, [NAME])
    (lions,) = scenario.battlefield(P1, ["Savannah Lions"], owner=P2)
    scenario.library(P0, ["Forest"])
    scenario.modes(cryptic, 1, 3).targets(cryptic, [TargetObject(lions)])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    _resolve_all(state, players=3)
    assert lions not in state.objects
    assert names(state, Zone.hand(P2)) == ["Savannah Lions"]
    assert state.player(P1).hand == [] and names(state, Zone.hand(P0)) == ["Forest"]


def test_cryptic_command_the_counter_mode_is_offered_with_a_spell_to_counter() -> None:
    """P1's Grizzly Bears is on the stack and P0 has a Test Totem (an enchantment): every mode has
    a legal target, so all six pairs of different modes are offered (ruling 1, 700.2a). Choosing
    counter and draw, the counter's only legal target is the Bears (115.2: not a permanent or
    player; 115.5: not Cryptic Command itself), so it is chosen without asking."""
    scenario = Scenario(2)
    (bears,) = scenario.stack(P1, ["Grizzly Bears"])
    (cryptic,) = scenario.hand(P0, [NAME])
    scenario.battlefield(P0, ["Test Totem"])
    scenario.mana(P0, U, U, U, U)
    scenario.at(Phase.PRECOMBAT_MAIN, priority=P0, passed=[P1])
    state = scenario.build()
    run_script(state, cast(cryptic, P0))
    space = request_of(state).space
    assert isinstance(space, ChooseOne)
    pairs = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
    assert space.options == tuple(ModesOption(pair) for pair in pairs)
    run_script(state, choose_modes(0, 3))
    assert target_choices(state) == (ObjectOption(bears),)
    _resolve_all(state)
    assert [c.spell for c in records(state, SpellCountered)] == [bears]


def test_cryptic_command_counter_and_tap_with_the_spell_gone_does_nothing() -> None:
    """Modes counter (P1's Grizzly Bears) and tap all creatures P0's opponents control. P0's
    Cancel counters the Bears first; Cryptic Command's only target is illegal, so it doesn't
    resolve and nothing is tapped (ruling 2, 608.2b), though tapping has no target."""
    scenario = Scenario(2)
    (bears,) = scenario.stack(P1, ["Grizzly Bears"])
    (cryptic,) = scenario.stack(P0, [NAME])
    (cancel,) = scenario.stack(P0, ["Cancel"])
    (lions,) = scenario.battlefield(P1, ["Savannah Lions"])
    scenario.modes(cryptic, 0, 2).targets(cryptic, [TargetObject(bears)])
    scenario.targets(cancel, [TargetObject(bears)])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    _resolve_all(state)
    assert [f.spell for f in records(state, SpellDidNotResolve)] == [cryptic]
    assert records(state, PermanentTapped) == [] and not state.objects[lions].tapped


def test_cryptic_command_bounce_target_gone_still_counters() -> None:
    """Modes counter (P1's Grizzly Bears) and return target permanent (P1's Sol Ring). P1's Test
    Shatter destroys the Sol Ring in response; the counter's target is still legal, so Cryptic
    Command resolves and counters the Bears (608.2b)."""
    scenario = Scenario(2)
    (bears,) = scenario.stack(P1, ["Grizzly Bears"])
    (cryptic,) = scenario.stack(P0, [NAME])
    (shatter,) = scenario.stack(P1, ["Test Shatter"])
    (ring,) = scenario.battlefield(P1, ["Sol Ring"])
    scenario.modes(cryptic, 0, 1).targets(cryptic, [TargetObject(bears)], [TargetObject(ring)])
    scenario.targets(shatter, [TargetObject(ring)])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    _resolve_all(state)
    assert [c.spell for c in records(state, SpellCountered)] == [bears]
    assert cryptic in [r.spell for r in records(state, SpellResolved)]
    assert state.battlefield == [] and names(state, Zone.graveyard(P1)) == [
        "Sol Ring", "Test Shatter", "Grizzly Bears"
    ]  # fmt: skip


def test_cryptic_command_taps_by_controller_not_owner() -> None:
    """ "Creatures your opponents control" is judged by control (108.4): a Grizzly Bears P0
    controls but P1 owns stays untapped; a Savannah Lions P1 controls but P0 owns is tapped."""
    scenario = Scenario(2)
    (cryptic,) = scenario.stack(P0, [NAME])
    (bears,) = scenario.battlefield(P0, ["Grizzly Bears"], owner=P1)
    (lions,) = scenario.battlefield(P1, ["Savannah Lions"], owner=P0)
    scenario.library(P0, ["Forest"])
    scenario.modes(cryptic, 2, 3)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    _resolve_all(state)
    assert [e.obj for e in records(state, PermanentTapped)] == [lions]
    assert state.objects[lions].tapped and not state.objects[bears].tapped
