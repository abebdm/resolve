"""The keyword example cards (docs/primitives.md): Ashcoat Bear (flash), Gladecover Scout
(hexproof), Humble Budoka (shroud), Darksteel Relic and Darksteel Myr (indestructible),
Repentant Blacksmith (protection from red), Nacatl Savage (protection from artifacts), Cancel
("Counter target spell."), M3.2's Raging Goblin (haste), Alaborn Grenadier (vigilance) and
Wall of Stone (defender), and M3.4's Wind Drake (flying), Giant Spider (reach), Deranged Whelp
(menace), Highborn Ghoul (intimidate), Severed Legion (fear) and Bog Raiders (swampwalk).

Oracle text and rulings checked against the Scryfall snapshot of 2026-10-26 (M3.2's cards:
2026-10-30; M3.4's: 2026-10-31, ``tools/excerpts/cards.json``). Their behavior is tested with
the keyword's rules: tests/rules/test_702_8_flash.py, test_702_11_hexproof.py,
test_702_18_shroud.py, test_702_12_indestructible.py, test_702_16_protection.py and
test_701_6_counter.py; haste (702.10b) in test_302_6_summoning_sickness.py, vigilance
(702.20b) and defender (702.3b) in
test_508_declare_attackers.py; M3.4's evasion in test_702_9_flying_and_reach.py,
test_702_111_menace.py and test_702_13_14_36_retired_evasion.py. M3.2's three cards have no
rulings; of M3.4's, only Giant Spider has one (2008-04-01: it uses reach to block flyers,
"because a creature with flying can only be blocked by creatures with flying or reach":
``test_702_9b_a_flyer_can_be_blocked_by_giant_spider_and_by_another_flyer``).

Only Nacatl Savage has a ruling (2009-02-01), "Protection from artifacts" means:

- "can't be blocked by artifact creatures": 702.16f, ``test_702_16f_protection_from_artifacts_
  cant_be_blocked_by_an_artifact_creature`` (tests/rules/test_509_declare_blockers.py, M3.3);
- "can't be equipped ... can't be enchanted by Auras that have somehow become artifacts": 702.16c-d,
  M4;
- "can't be targeted by abilities from artifact sources": ``test_702_16a_card_type_quality``;
- "All damage that would be dealt to Nacatl Savage by artifact sources is prevented": 702.16e,
  a gap until M6 (``test_702_16e_..._gap_until_m6`` shows the gap for a red source).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from resolve.cards.definitions import keyword_examples
from resolve.cards.keywords import (
    Defender,
    Fear,
    Flash,
    Flying,
    Haste,
    Hexproof,
    Indestructible,
    Intimidate,
    LandTypeQuality,
    Landwalk,
    Menace,
    Protection,
    Reach,
    Shroud,
    Vigilance,
    has_keyword,
)
from resolve.cards.primitives.base import Ability
from resolve.cards.primitives.words import LandTypeWord
from resolve.cards.registry import default_registry
from resolve.data.cards import load_card_excerpt
from resolve.effects.characteristics import characteristics
from resolve.state.ids import PlayerId
from tests.scenario import Scenario

EXCERPT = Path(__file__).resolve().parents[2] / "tools" / "excerpts" / "cards.json"
P0 = PlayerId(0)

KEYWORDS: dict[str, type[Ability]] = {
    "Ashcoat Bear": Flash,
    "Gladecover Scout": Hexproof,
    "Humble Budoka": Shroud,
    "Darksteel Relic": Indestructible,
    "Darksteel Myr": Indestructible,
    "Repentant Blacksmith": Protection,
    "Nacatl Savage": Protection,
    "Raging Goblin": Haste,
    "Alaborn Grenadier": Vigilance,
    "Wall of Stone": Defender,
    "Wind Drake": Flying,
    "Giant Spider": Reach,
    "Deranged Whelp": Menace,
    "Highborn Ghoul": Intimidate,
    "Severed Legion": Fear,
    "Bog Raiders": Landwalk,
}

# M3.4's cards as the M3 plan lists them (section 7): cost, type line, power and toughness.
M3_4_CARDS = {
    "Wind Drake": ("{2}{U}", "Creature — Drake", "2", "2"),
    "Giant Spider": ("{3}{G}", "Creature — Spider", "2", "4"),
    "Deranged Whelp": ("{1}{R}", "Creature — Wolf", "2", "1"),
    "Highborn Ghoul": ("{B}{B}", "Creature — Zombie", "2", "1"),
    "Severed Legion": ("{1}{B}{B}", "Creature — Zombie", "2", "2"),
    "Bog Raiders": ("{2}{B}", "Creature — Zombie", "2", "2"),
}


def _without_reminder(text: str) -> str:
    """The Oracle text without its reminder text (parenthesized; it isn't rules text, 207.2)."""
    return re.sub(r"\s*\([^)]*\)", "", text).strip()


@pytest.mark.parametrize("name", list(KEYWORDS))
def test_its_definition_is_its_oracle_text(name: str) -> None:
    """The definition is registered, its one ability is the keyword, and the ability's text is
    the Oracle text without reminder text."""
    definition = default_registry().get(name)
    assert definition in keyword_examples.DEFINITIONS
    card = load_card_excerpt(EXCERPT).get(name)
    (ability,) = definition.abilities
    assert isinstance(ability, KEYWORDS[name])
    assert ability.text == _without_reminder(card.faces[0].oracle_text)
    assert definition.spell is None


def test_cancel_definition_is_its_oracle_text() -> None:
    definition = default_registry().get("Cancel")
    card = load_card_excerpt(EXCERPT).get("Cancel")
    assert definition.spell is not None
    assert definition.spell.text == card.faces[0].oracle_text == "Counter target spell."
    assert (card.faces[0].mana_cost, card.type_line) == ("{1}{U}{U}", "Instant")


@pytest.mark.parametrize("name", list(KEYWORDS))
def test_the_keyword_is_read_through_characteristics(name: str) -> None:
    """``has_keyword`` reads the computed characteristics (so M5's grants and removals need no
    change): each card on the battlefield has its keyword, and none of the others."""
    scenario = Scenario(2)
    (obj,) = scenario.battlefield(P0, [name])
    state = scenario.build()
    chars = characteristics(state, obj)
    for kind in dict.fromkeys(KEYWORDS.values()):
        assert has_keyword(chars, kind) == (kind is KEYWORDS[name])


@pytest.mark.parametrize("name", list(M3_4_CARDS))
def test_m3_4_card_data_matches_the_plan(name: str) -> None:
    """The excerpt (copied from the snapshot) has the cost, type line, power and toughness the
    M3 plan lists for the card (approval note 4)."""
    card = load_card_excerpt(EXCERPT).get(name)
    face = card.faces[0]
    assert (face.mana_cost, card.type_line, face.power, face.toughness) == M3_4_CARDS[name]


def test_bog_raiders_walks_swamps() -> None:
    """Swampwalk is landwalk whose quality is the land type Swamp (702.14a), a typed word
    (612.2)."""
    (ability,) = default_registry().get("Bog Raiders").abilities
    assert ability == Landwalk(LandTypeQuality(LandTypeWord("Swamp")))
    assert ability.text == "Swampwalk"
