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

from resolve.cards.keywords import ColorQuality, Protection, keywords
from resolve.cards.primitives.targets import ANY_TARGET
from resolve.cards.primitives.words import ColorWord
from resolve.data.types import Color
from resolve.decisions.spaces import ObjectOption, PlayerOption
from resolve.effects.characteristics import characteristics
from resolve.errors import NotImplementedRule
from resolve.events.damage import DamageDealt
from resolve.rules import defaults, targeting
from resolve.rules.legality import Targeter
from resolve.state.game import GameState
from resolve.state.ids import PlayerId
from resolve.state.mana import ManaType
from resolve.state.spell import TargetObject
from resolve.state.turn import Phase
from tests.casting_support import cast, pass_, records, target_choices
from tests.scenario import Scenario, run_script

P0, P1 = PlayerId(0), PlayerId(1)
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
    monkeypatch.setattr(
        defaults, "player_abilities", lambda state, who: (red,) if who == P1 else ()
    )
    scenario = Scenario(2)
    (shock,) = scenario.hand(P0, ["Test Shock"])
    scenario.mana(P0, R)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(shock, P0))
    assert target_choices(state) == (PlayerOption(P0),)
