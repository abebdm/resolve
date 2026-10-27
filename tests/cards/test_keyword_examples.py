"""The keyword example cards (docs/plans/m2.md §7): Ashcoat Bear (flash), Gladecover Scout
(hexproof), Humble Budoka (shroud), Darksteel Relic and Darksteel Myr (indestructible),
Repentant Blacksmith (protection from red), Nacatl Savage (protection from artifacts) and Cancel
("Counter target spell.").

Oracle text and rulings checked against the Scryfall snapshot of 2026-10-26
(``tools/excerpts/cards.json``). Their behavior is tested with the keyword's rules:
tests/rules/test_702_8_flash.py, test_702_11_hexproof.py, test_702_18_shroud.py,
test_702_12_indestructible.py, test_702_16_protection.py and test_701_6_counter.py.

Only Nacatl Savage has a ruling (2009-02-01), "Protection from artifacts" means:

- "can't be blocked by artifact creatures": 702.16f, blocking, M3;
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
    Flash,
    Hexproof,
    Indestructible,
    Protection,
    Shroud,
    has_keyword,
)
from resolve.cards.primitives.base import Ability
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
