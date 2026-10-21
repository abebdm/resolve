"""Command Tower (Land) and Arcane Signet ({2} Artifact): "{T}: Add one mana of any color in your
commander's color identity."

Oracle text and rulings checked against the Scryfall snapshot of 2026-10-21
(``tools/excerpts/cards.json``). The rulings, the same for both cards:

- with two commanders, the ability adds one mana of any color in their combined color
  identities;
- a commander whose color identity has no colors: no mana (not even {C});
- no commander: no mana.

From the pinned CR:

- 903.4: color identity; 903.4a: established before the game, from the card. "Your commander"
  is the commander of the ability's controller, not an opponent's (903.3).
- 903.4f: with no commander the quality is undefined and that part of the ability does nothing;
  106.5: mana of an undefined type isn't produced. The ability is still activated: {T} is paid
  (602.2b) and it resolves (605.3b), adding nothing.
- 106.1a, 605.3b: the color is chosen as the ability resolves. With one color there is nothing to
  choose, so nothing is asked.
- 733.1: a kept mana ability's result stands after a reversal, the chosen color included.
- Arcane Signet is an artifact spell (301.1); 302.6 doesn't apply to it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from resolve.cards.definitions.mana_rocks import ARCANE_SIGNET
from resolve.cards.definitions.nonbasic_lands import COMMAND_TOWER
from resolve.cards.registry import default_registry
from resolve.data.cards import load_card_excerpt
from resolve.data.types import Color
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import ActivateAbilityOption, ChooseOne, ColorOption
from resolve.events.mana import ManaAdded
from resolve.events.permanents import PermanentTapped
from resolve.events.spells import SpellCast
from resolve.rules.commander import commander_color_identity
from resolve.state.config import GameConfig
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import Mana, ManaType
from resolve.state.turn import Phase
from resolve.state.zones import BATTLEFIELD, Zone
from tests.casting_support import (
    activate,
    activate_with_priority,
    answered,
    cast,
    choose_color,
    options,
    pass_,
    records,
    reverse,
)
from tests.game_fixtures import request_of
from tests.scenario import Scenario, run_script

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)
W, G = ManaType.WHITE, ManaType.GREEN
EXCERPT = Path(__file__).resolve().parents[2] / "tools" / "excerpts" / "cards.json"
TEXT = "{T}: Add one mana of any color in your commander's color identity."
SOURCES = ["Command Tower", "Arcane Signet"]


def board(
    source: str,
    commanders: dict[PlayerId, list[str]],
    *,
    players: int = 2,
    config: GameConfig | None = None,
) -> tuple[GameState, ObjectId]:
    """P0's main phase with ``source`` on P0's battlefield and the given commanders (in the command
    zone)."""
    scenario = Scenario(players, config=config or GameConfig.commander_game())
    for player, names in commanders.items():
        for name in names:
            scenario.commander(player, name)
    (obj,) = scenario.battlefield(P0, [source])
    scenario.at(Phase.PRECOMBAT_MAIN)
    return scenario.build(), obj


def test_their_definitions_are_their_oracle_text() -> None:
    excerpt = load_card_excerpt(EXCERPT)
    for definition in (COMMAND_TOWER, ARCANE_SIGNET):
        assert default_registry().get(definition.name) is definition
        (ability,) = definition.abilities
        assert ability.text == TEXT
        assert excerpt.get(definition.name).faces[0].oracle_text == TEXT
    assert excerpt.get("Arcane Signet").faces[0].mana_cost == "{2}"
    assert excerpt.get("Command Tower").faces[0].mana_cost == ""


@pytest.mark.parametrize("source", SOURCES)
def test_903_4_command_tower_adds_a_color_of_the_commanders_identity(source: str) -> None:
    """Avacyn's Pilgrim's identity is green and white: the choice is W or G only (WUBRG order)."""
    state, obj = board(source, {P0: ["Avacyn's Pilgrim"]})
    run_script(state, activate_with_priority(obj))
    request = request_of(state)
    assert request.kind is DecisionKind.CHOOSE_COLOR
    assert request.player == P0 and request.source == obj
    assert request.space == ChooseOne((ColorOption(Color.WHITE), ColorOption(Color.GREEN)))
    run_script(state, choose_color(Color.GREEN))
    assert state.player(P0).mana_pool == [Mana(G, obj)]
    assert state.objects[obj].tapped
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION


@pytest.mark.parametrize("source", SOURCES)
def test_903_4_one_color_isnt_asked(source: str) -> None:
    state, obj = board(source, {P0: ["Llanowar Elves"]})
    run_script(state, activate_with_priority(obj))
    assert answered(state, DecisionKind.CHOOSE_COLOR) == 0
    assert state.player(P0).mana_pool == [Mana(G, obj)]


@pytest.mark.parametrize("source", SOURCES)
def test_903_4f_no_commander_no_mana(source: str) -> None:
    """A standard game, and a Commander game where P0 has no commander: the ability is offered and
    activated (605.2: still a mana ability; its cost is paid), but adds no mana (106.5)."""
    for config in (GameConfig.standard(), GameConfig.commander_game()):
        state, obj = board(source, {} if config.commander is None else {P1: ["Llanowar Elves"]},
                           config=config)  # fmt: skip
        assert commander_color_identity(state, P0) is None
        assert ActivateAbilityOption(obj, 0) in options(state)
        run_script(state, activate_with_priority(obj))
        assert state.objects[obj].tapped
        assert [e.obj for e in records(state, PermanentTapped)] == [obj]
        assert records(state, ManaAdded) == []
        assert state.player(P0).mana_pool == []
        assert answered(state, DecisionKind.CHOOSE_COLOR) == 0
        assert request_of(state).kind is DecisionKind.PRIORITY_ACTION


@pytest.mark.parametrize("source", SOURCES)
def test_903_4f_a_colorless_commander_gives_no_mana(source: str) -> None:
    """Sol Ring's identity has no colors (the builder doesn't check that it may be a commander):
    no mana, not even {C}."""
    state, obj = board(source, {P0: ["Sol Ring"]})
    assert commander_color_identity(state, P0) == ()
    run_script(state, activate_with_priority(obj))
    assert state.objects[obj].tapped
    assert records(state, ManaAdded) == []
    assert state.player(P0).mana_pool == []


@pytest.mark.parametrize("source", SOURCES)
def test_903_4_two_commanders_combine(source: str) -> None:
    """Savannah Lions (white) and Grizzly Bears (green): W or G."""
    state, obj = board(source, {P0: ["Grizzly Bears", "Savannah Lions"]})
    assert commander_color_identity(state, P0) == (Color.WHITE, Color.GREEN)
    run_script(state, activate_with_priority(obj))
    assert request_of(state).space == ChooseOne(
        (ColorOption(Color.WHITE), ColorOption(Color.GREEN))
    )
    run_script(state, choose_color(Color.WHITE))
    assert state.player(P0).mana_pool == [Mana(W, obj)]


@pytest.mark.parametrize("source", SOURCES)
def test_903_4_it_is_your_commander_not_an_opponents(source: str) -> None:
    """Three players: P0's commander is white, P1's red, P2's green. P0's source adds {W} only;
    a source P1 controls adds {R} only."""
    scenario = Scenario(3, config=GameConfig.commander_game())
    scenario.commander(P0, "Savannah Lions")
    scenario.commander(P1, "Hill Giant")
    scenario.commander(P2, "Grizzly Bears")
    (mine,) = scenario.battlefield(P0, [source])
    (theirs,) = scenario.battlefield(P1, [source], owner=P0)
    scenario.at(Phase.PRECOMBAT_MAIN, passed=[P0], priority=P1)
    state = scenario.build()
    assert commander_color_identity(state, P1) == (Color.RED,)
    run_script(state, activate_with_priority(theirs))
    assert state.player(P1).mana_pool == [Mana(ManaType.RED, theirs)]
    run_script(state, pass_(P1), pass_(P2), activate_with_priority(mine))
    assert state.player(P0).mana_pool == [Mana(W, mine)]
    assert answered(state, DecisionKind.CHOOSE_COLOR) == 0


def test_903_4_command_tower_pays_a_spell_with_the_chosen_color() -> None:
    """Casting Savannah Lions ({W}) with Command Tower under a green-white commander: W is chosen
    while paying (605.3a) and pays {W}."""
    scenario = Scenario(2, config=GameConfig.commander_game())
    scenario.commander(P0, "Avacyn's Pilgrim")
    (lions,) = scenario.hand(P0, ["Savannah Lions"])
    (tower,) = scenario.battlefield(P0, ["Command Tower"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(lions, P0), activate(tower), choose_color(Color.WHITE))
    (cast_event,) = records(state, SpellCast)
    assert cast_event.mana_spent == (Mana(W, tower),)


def test_733_1_a_kept_command_tower_keeps_the_color_it_added() -> None:
    """Command Tower makes {G} while P0 tries to cast Savannah Lions ({W}); the cast fails. P0
    keeps the Tower's ability: it stays tapped and the {G} it added stays, without asking for a
    color again."""
    scenario = Scenario(2, config=GameConfig.commander_game())
    scenario.commander(P0, "Avacyn's Pilgrim")
    (lions,) = scenario.hand(P0, ["Savannah Lions"])
    (tower,) = scenario.battlefield(P0, ["Command Tower"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(lions, P0), activate(tower), choose_color(Color.GREEN))
    assert request_of(state).kind is DecisionKind.REVERSE_MANA_ABILITIES
    run_script(state, reverse())
    assert answered(state, DecisionKind.CHOOSE_COLOR) == 1
    assert state.objects[tower].tapped
    assert state.player(P0).mana_pool == [Mana(G, tower)]
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION


def test_301_1_arcane_signet_is_cast_for_2_and_taps_at_once() -> None:
    """An artifact spell (sorcery timing); not a creature, so it taps the turn it enters (302.6)."""
    scenario = Scenario(2, config=GameConfig.commander_game())
    scenario.commander(P0, "Llanowar Elves")
    (signet,) = scenario.hand(P0, ["Arcane Signet"])
    first, second = scenario.battlefield(P0, ["Forest", "Forest"])
    scenario.at(Phase.PRECOMBAT_MAIN, number=1)
    state = scenario.build()
    run_script(state, cast(signet, P0), activate(first), activate(second), pass_(P0), pass_(P1))
    (permanent,) = [o for o in state.battlefield if o not in (first, second)]
    run_script(state, activate_with_priority(permanent))
    assert state.player(P0).mana_pool == [Mana(G, permanent)]


@pytest.mark.parametrize("zone", [BATTLEFIELD, Zone.graveyard(P0)])
def test_903_4a_the_commanders_identity_counts_wherever_the_commander_is(zone: Zone) -> None:
    """A commander on the battlefield or in a graveyard is still the player's commander (903.3),
    and its color identity was fixed before the game (903.4a)."""
    scenario = Scenario(2, config=GameConfig.commander_game())
    scenario.commander(P0, "Avacyn's Pilgrim", zone=zone)
    (tower,) = scenario.battlefield(P0, ["Command Tower"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, activate_with_priority(tower))
    assert request_of(state).space == ChooseOne(
        (ColorOption(Color.WHITE), ColorOption(Color.GREEN))
    )
