"""702.16: protection, its targeting part (M2), and its damage part as a gap until M6.

From the pinned CR:

- 702.16a: "protection from [quality]"; a card-type quality applies to sources that are
  permanents with that type and to sources not on the battlefield of that type.
- 702.16b: a permanent or player with protection can't be targeted by spells with the stated
  quality, nor by abilities from a source with it. Whoever controls them: unlike hexproof, its
  controller's spells are stopped too.
- 702.16e: damage that would be dealt by sources with the quality is prevented. Prevention is the
  replacement stage's (M6), so until then it raises ``NotImplementedRule("702.16e")``; damage
  from a source without the quality is dealt as normal.
- 702.16h: "protection from each color" is five protection abilities.
- 702.16j: "protection from everything": no spell or ability can target it.
- 105.2c: a multicolored object has two or more colors.

Abilities don't exist on the stack until M4, so "abilities from a source" is checked at predicate
level: ``target_problem`` with a ``Targeter`` whose characteristics are the source's (113.7a).
"""

from __future__ import annotations

import pytest

from resolve.cards.keywords import ColorQuality, PlayerQuality, Protection, keywords
from resolve.cards.primitives.targets import ANY_TARGET
from resolve.cards.primitives.words import ColorWord
from resolve.cards.registry import CardDefinition, CardRegistry
from resolve.data.cards import CardDatabase, parse_oracle_cards
from resolve.data.types import Color
from resolve.decisions.spaces import ObjectOption, PlayerOption
from resolve.effects.characteristics import Characteristics, characteristics
from resolve.errors import EngineError, NotImplementedRule
from resolve.events.damage import DamageDealt
from resolve.rules import legality, targeting
from resolve.rules.legality import Targeter
from resolve.state.game import GameState
from resolve.state.ids import PlayerId
from resolve.state.mana import ManaType
from resolve.state.spell import TargetObject
from resolve.state.turn import Phase, Step
from tests import scryfall_fixtures as fx
from tests.casting_support import cast, pass_, records, target_choices
from tests.game_fixtures import scenario_database, scenario_registry
from tests.scenario import Scenario, run_script
from tests.seams import patch

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)
W, R = ManaType.WHITE, ManaType.RED


def offered(caster: PlayerId, spell: str, protected: str, mana: tuple[ManaType, ...]) -> bool:
    """Whether ``caster``'s ``spell`` offers P0's creature ``protected`` as a target (601.2c)."""
    scenario = Scenario(2)
    (creature,) = scenario.battlefield(P0, [protected])
    (card,) = scenario.hand(caster, [spell])
    scenario.battlefield(P1, ["Grizzly Bears"])  # so a creature-only spell always has a target
    scenario.mana(caster, *mana)
    scenario.at(Phase.PRECOMBAT_MAIN, active=caster)
    state = scenario.build()
    run_script(state, cast(card, caster))
    return ObjectOption(creature) in target_choices(state)


def source_problem(protected: str, source: str, *, on_stack: bool = False) -> list[str] | None:
    """The rules forbidding an ability (M4) from ``source`` (on the battlefield, or a spell on
    the stack) controlled by P1 to target P0's ``protected``, or ``None`` if it may."""
    scenario = Scenario(2)
    (creature,) = scenario.battlefield(P0, [protected])
    if on_stack:
        (obj,) = scenario.stack(P1, [source])
    else:
        (obj,) = scenario.battlefield(P1, [source])
    state = scenario.build()
    targeter = Targeter(P1, obj, characteristics(state, obj))
    verdict = targeting.target_problem(state, targeter, ANY_TARGET, TargetObject(creature))
    return None if verdict is None else list(verdict.rules)


def test_702_16b_spells_with_the_quality_cant_target_it() -> None:
    """Repentant Blacksmith (protection from red), P0's: P1's Test Shock (red) can't target it;
    P1's Swords to Plowshares (white) can."""
    assert not offered(P1, "Test Shock", "Repentant Blacksmith", (R,))
    assert offered(P1, "Swords to Plowshares", "Repentant Blacksmith", (W,))
    assert source_problem("Repentant Blacksmith", "Test Shock", on_stack=True) == [
        "101.2",
        "702.16b",
    ]


def test_702_16b_even_its_controllers_spells() -> None:
    """P0's own Test Shock can't target P0's Repentant Blacksmith: protection stops spells with
    the quality whoever controls them (702.16b)."""
    assert not offered(P0, "Test Shock", "Repentant Blacksmith", (R,))
    assert offered(P0, "Swords to Plowshares", "Repentant Blacksmith", (W,))


def test_702_16b_multicolored() -> None:
    """Test Multiproof Knight (protection from multicolored): Test Gold Shock ({R}{W}, red and
    white: multicolored, 105.2c) can't target it; Test Shock (red only) can."""
    assert not offered(P1, "Test Gold Shock", "Test Multiproof Knight", (R, W))
    assert offered(P1, "Test Shock", "Test Multiproof Knight", (R,))


def test_702_16h_each_color_is_five_abilities() -> None:
    """Test Prismatic Knight (protection from each color) has five protection abilities, one per
    color (702.16h): neither Test Shock (red) nor Swords to Plowshares (white) can target it,
    but an ability from a colorless source (Sol Ring) could."""
    scenario = Scenario(2)
    (knight,) = scenario.battlefield(P0, ["Test Prismatic Knight"])
    state = scenario.build()
    found = keywords(characteristics(state, knight), Protection)
    assert [p.text for p in found] == [
        "Protection from white",
        "Protection from blue",
        "Protection from black",
        "Protection from red",
        "Protection from green",
    ]
    assert not offered(P1, "Test Shock", "Test Prismatic Knight", (R,))
    assert not offered(P1, "Swords to Plowshares", "Test Prismatic Knight", (W,))
    assert source_problem("Test Prismatic Knight", "Sol Ring") is None


def test_702_16j_everything() -> None:
    """Test Untouchable (protection from everything): no spell can target it, white, red or its
    controller's own, nor an ability from a colorless artifact (702.16j)."""
    assert not offered(P1, "Test Shock", "Test Untouchable", (R,))
    assert not offered(P1, "Swords to Plowshares", "Test Untouchable", (W,))
    assert not offered(P0, "Swords to Plowshares", "Test Untouchable", (W,))
    assert source_problem("Test Untouchable", "Sol Ring") == ["101.2", "702.16j"]


def test_702_16a_card_type_quality() -> None:
    """Nacatl Savage (protection from artifacts): an ability from an artifact source (Sol Ring on
    the battlefield, 702.16a: a permanent with the type) can't target it, nor could an artifact
    source not on the battlefield (Sol Ring as a spell); a red instant, Test Shock, may."""
    assert source_problem("Nacatl Savage", "Sol Ring") == ["101.2", "702.16b"]
    assert source_problem("Nacatl Savage", "Sol Ring", on_stack=True) == ["101.2", "702.16b"]
    assert source_problem("Nacatl Savage", "Test Shock", on_stack=True) is None
    assert offered(P1, "Test Shock", "Nacatl Savage", (R,))


def _burn(state: GameState) -> None:
    run_script(state, pass_(P1), pass_(P0))


def test_702_16e_damage_from_a_red_source_is_a_gap_until_m6() -> None:
    """P1's Fiery Confluence (red) would deal 1 damage to each creature, P0's Repentant Blacksmith
    included: preventing it is protection's 702.16e, a gap until M6's prevention stage. Damage
    from a source without the quality is dealt: P1's Chandra's Ignition targeting P1's Grizzly
    Bears (green) deals 2 damage to the Blacksmith."""
    scenario = Scenario(2)
    (confluence,) = scenario.stack(P1, ["Fiery Confluence"])
    scenario.modes(confluence, 0, 0, 0)
    scenario.battlefield(P0, ["Repentant Blacksmith"])
    scenario.at(Phase.PRECOMBAT_MAIN, active=P1)
    state = scenario.build()
    with pytest.raises(NotImplementedRule) as gap:
        _burn(state)
    assert gap.value.rule == "702.16e"

    scenario = Scenario(2)
    (ignition,) = scenario.stack(P1, ["Chandra's Ignition"])
    (bears,) = scenario.battlefield(P1, ["Grizzly Bears"])
    (smith,) = scenario.battlefield(P0, ["Repentant Blacksmith"])
    scenario.targets(ignition, [TargetObject(bears)])
    scenario.at(Phase.PRECOMBAT_MAIN, active=P1)
    state = scenario.build()
    _burn(state)
    (damage,) = records(state, DamageDealt)
    assert damage.to_objects == ((smith, 2),)
    assert smith not in state.objects  # 1/2 with 2 damage: destroyed (704.5g)


def test_702_16b_a_player_with_protection(monkeypatch: pytest.MonkeyPatch) -> None:
    """With ``defaults.player_abilities`` giving P1 protection from red, P0's Test Shock can't
    target P1 (702.16b: a permanent or player); P0 still can be."""
    red = Protection(ColorQuality(ColorWord(Color.RED)))
    patch(monkeypatch, "player_abilities", lambda state, who: (red,) if who == P1 else ())
    scenario = Scenario(2)
    (shock,) = scenario.hand(P0, ["Test Shock"])
    scenario.mana(P0, R)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(shock, P0))
    assert target_choices(state) == (PlayerOption(P0),)


def test_702_16b_a_multicolored_spell_with_the_color() -> None:
    """Test Gold Shock is red and white (105.2c), so it has the quality "red": it can't target
    Repentant Blacksmith (protection from red), whoever casts it (702.16b)."""
    assert not offered(P1, "Test Gold Shock", "Repentant Blacksmith", (R, W))
    assert not offered(P0, "Test Gold Shock", "Repentant Blacksmith", (R, W))


def test_702_16j_damage_from_any_source_is_a_gap_until_m6() -> None:
    """Test Untouchable has protection from everything: all damage to it would be prevented
    (702.16j), even from a green source. P1's Chandra's Ignition targeting
    P1's Grizzly Bears (green) would deal 2 damage to it: the 702.16e gap."""
    scenario = Scenario(2)
    (ignition,) = scenario.stack(P1, ["Chandra's Ignition"])
    (bears,) = scenario.battlefield(P1, ["Grizzly Bears"])
    scenario.battlefield(P0, ["Test Untouchable"])
    scenario.targets(ignition, [TargetObject(bears)])
    scenario.at(Phase.PRECOMBAT_MAIN, active=P1)
    state = scenario.build()
    with pytest.raises(NotImplementedRule) as gap:
        _burn(state)
    assert gap.value.rule == "702.16e"


def test_702_16e_damage_to_a_player_with_protection_is_a_gap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With ``defaults.player_abilities`` giving P0 protection from red, P1's Fiery Confluence
    (red; 2 damage to each opponent, three times) would deal damage protection prevents: the
    702.16e gap. This is the damage seam of ``player_abilities`` (the targeting seam is in
    test_702_11_hexproof.py). Without the patch the same spell deals P0 6 damage."""
    red = Protection(ColorQuality(ColorWord(Color.RED)))

    def build() -> GameState:
        scenario = Scenario(2)
        (confluence,) = scenario.stack(P1, ["Fiery Confluence"])
        scenario.modes(confluence, 1, 1, 1)
        scenario.at(Phase.PRECOMBAT_MAIN, active=P1)
        return scenario.build()

    state = build()
    life = state.player(P0).life
    _burn(state)
    assert state.player(P0).life == life - 6

    patch(monkeypatch, "player_abilities", lambda state, who: (red,) if who == P0 else ())
    state = build()
    with pytest.raises(NotImplementedRule) as gap:
        _burn(state)
    assert gap.value.rule == "702.16e"


# --- 702.16k: protection from a player (M3.4) ---------------------------------------------------
#
# 702.16k: "A permanent or player with protection from a specific player has protection from each
# object that player controls and protection from each object that player owns not controlled by
# another player, regardless of that object's characteristic values. Such a permanent or player
# can't be targeted by spells or abilities the specified player controls ... Such a permanent
# can't be ... blocked by creatures that player controls. All damage that would be dealt to such
# a permanent or player by sources controlled by the specified player ... is prevented."
#
# No card in scope has it (True-Name Nemesis chooses the player as it enters, a choice stored on
# the permanent: M4), so a fixture knight has protection from P1, a ``PlayerQuality``. Its
# targeting and blocking parts are checked at predicate level (``target_problem``,
# ``legality.allowed(BlockAction)``); its damage part reaches the 702.16e gap.

WARDED_KNIGHT = fx.keyword_creature(
    "Test Warded Knight", "{1}{W}", 2.0, "Knight", ("2", "2"), "W", "Protection from player 1"
)


def warded_scenario(players: int) -> Scenario:
    """A scenario whose cards include Test Warded Knight, with protection from P1."""
    registry = scenario_registry()
    knight = CardDefinition("Test Warded Knight", abilities=(Protection(PlayerQuality(P1)),))
    return Scenario(
        players,
        database=CardDatabase([*scenario_database().cards(), *parse_oracle_cards([WARDED_KNIGHT])]),
        registry=CardRegistry([*(registry.get(n) for n in registry.names()), knight]),
    )


def test_702_16k_protection_from_a_player_cant_be_blocked_by_their_creatures() -> None:
    """Three players: two Warded Knights (protection from P1) attack P1 and P2. P1's Grizzly
    Bears (green, but "regardless of characteristic values") can't block the one attacking
    them; P2's Grizzly Bears may block the other, protection from P1 being nothing to P2."""
    scenario = warded_scenario(3)
    knight_1, knight_2 = scenario.battlefield(P0, ["Test Warded Knight", "Test Warded Knight"])
    (bears_1,) = scenario.battlefield(P1, ["Grizzly Bears"])
    (bears_2,) = scenario.battlefield(P2, ["Grizzly Bears"])
    scenario.at(Step.DECLARE_BLOCKERS, begin=True)
    scenario.attacking(P1, knight_1)
    scenario.attacking(P2, knight_2)
    state = scenario.build()
    refused = legality.allowed(state, legality.BlockAction(P1, bears_1, knight_1))
    assert not refused.allowed and "702.16k" in refused.rules
    assert legality.allowed(state, legality.BlockAction(P2, bears_2, knight_2)).allowed


def test_702_16k_protection_from_a_player_cant_be_targeted_by_what_they_control() -> None:
    """P1's Grizzly Bears as the source of an ability (or P1's Test Shock on the stack) can't
    target P0's Warded Knight (702.16k); the same objects controlled by P0 can, whatever their
    characteristics: protection from a player isn't protection from a color."""
    scenario = warded_scenario(2)
    (knight,) = scenario.battlefield(P0, ["Test Warded Knight"])
    (theirs,) = scenario.battlefield(P1, ["Grizzly Bears"])
    (mine,) = scenario.battlefield(P0, ["Grizzly Bears"])
    (shock,) = scenario.stack(P1, ["Test Shock"])
    state = scenario.build()
    for obj, controller in ((theirs, P1), (shock, P1)):
        targeter = Targeter(controller, obj, characteristics(state, obj))
        problem = targeting.target_problem(state, targeter, ANY_TARGET, TargetObject(knight))
        assert problem is not None and "702.16k" in problem.rules
    targeter = Targeter(P0, mine, characteristics(state, mine))
    assert targeting.target_problem(state, targeter, ANY_TARGET, TargetObject(knight)) is None


def test_702_16k_damage_from_a_source_they_control_is_a_gap_until_m6() -> None:
    """Damage from a source P1 controls to the Warded Knight would be prevented (702.16k): the
    702.16e gap, raised before anything changes. P0's own source deals its damage."""
    scenario = warded_scenario(2)
    (knight,) = scenario.battlefield(P0, ["Test Warded Knight"])
    (theirs,) = scenario.battlefield(P1, ["Grizzly Bears"])
    (mine,) = scenario.battlefield(P0, ["Grizzly Bears"])
    state = scenario.build()
    with pytest.raises(NotImplementedRule) as gap:
        DamageDealt(source=theirs, to_objects=((knight, 2),), rules=("120.3e",)).apply(state)
    assert gap.value.rule == "702.16e"
    assert state.objects[knight].damage == 0
    DamageDealt(source=mine, to_objects=((knight, 1),), rules=("120.3e",)).apply(state)
    assert state.objects[knight].damage == 1


def test_702_16k_player_quality_is_judged_by_control_and_ownership() -> None:
    """The quality itself: an object P1 controls has it, one P0 controls that P1 owns doesn't
    (it is controlled by another player), one with no controller (a card in a hidden zone,
    108.4a) has it if P1 owns it. It can't be judged from characteristics alone."""
    quality = PlayerQuality(P1)
    chars = Characteristics("Test", (), (), ())
    assert quality.matches_source(chars, controller=P1, owner=P0)
    assert not quality.matches_source(chars, controller=P0, owner=P1)
    assert quality.matches_source(chars, controller=None, owner=P1)
    assert not quality.matches_source(chars, controller=None, owner=P0)
    assert Protection(quality).text == "Protection from player 1"
    with pytest.raises(EngineError):
        quality.matches(chars)
