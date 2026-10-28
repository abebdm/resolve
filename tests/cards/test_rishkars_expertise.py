"""Rishkar's Expertise: {4}{G}{G}, Sorcery. "Draw cards equal to the greatest power among
creatures you control. / You may cast a spell with mana value 5 or less from your hand without
paying its mana cost."

Oracle text and rulings checked against the Scryfall snapshot of 2026-10-27
(``tools/excerpts/cards.json``). The rulings (2017-02-09 unless noted), and where each is tested:

- "without paying its mana cost": no other alternative cost; additional costs may be paid and
  mandatory ones must be. No implemented card has an additional cost (601.2b raises for one,
  M4), so this is untested until one exists.
- casting doesn't allow playing a land: ``test_608_2g_offers_only_spells_of_mana_value_5_or_less``
  (tests/rules/test_608_2g_casting_during_resolution.py);
- a card drawn by the first effect may be cast: ``test_it_may_cast_a_card_it_drew``;
- mana value is the printed cost's (ignoring cost changes; no mana cost is 0):
  ``test_608_2g_mana_value_is_the_printed_cost_not_what_is_paid``,
  ``test_118_6a_a_card_with_no_mana_cost_can_be_cast_without_paying_it``;
- with no creature of power above 0 it draws nothing but may still cast:
  ``test_with_no_creatures_draws_nothing_but_may_still_cast``,
  ``test_a_creature_with_0_power_draws_nothing``;
- X must be 0: ``test_107_3b_x_must_be_0``;
- triggered abilities wait until the free spell is cast: no triggered abilities exist until M4;
- the Expertise stays on the stack during the free cast, goes to the graveyard after, and may be
  targeted by the free spell: ``test_608_2g_a_sorcery_can_be_cast_while_the_expertise_resolves``,
  ``test_608_2g_no_priority_after_the_free_spell_is_cast``,
  ``test_608_2g_the_free_spell_may_target_the_resolving_expertise``;
- the greatest power is determined as it resolves: ``test_the_power_is_read_as_it_resolves``
  (until effects can change power, M5, that can only be seen as the creatures it has then);
- (2017-04-18) a split card's mana value is that of both halves, and either half may be cast:
  superseded by 709.3a and 601.3e in the pinned CR (only the half cast is considered), and
  casting a half is still the 709.3 gap
  (``test_608_2g_the_permission_ignores_timing_but_not_variants``,
  ``test_709_3a_a_split_card_is_judged_by_the_half_cast``; docs/decisions.md, 2026-10-28).
"""

from __future__ import annotations

from pathlib import Path

from resolve.cards.definitions.card_draw import RISHKARS_EXPERTISE
from resolve.cards.registry import default_registry
from resolve.data.cards import load_card_excerpt
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import CastSpellOption
from resolve.events.cards import CardDrawn
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.spell import NORMAL
from resolve.state.turn import Phase
from resolve.state.zones import BATTLEFIELD, STACK, Zone
from tests.casting_support import (
    activate,
    answered,
    cast,
    cast_during_resolution,
    decline,
    options,
    pass_,
    records,
)
from tests.game_fixtures import request_of
from tests.rules.test_608_2g_casting_during_resolution import free
from tests.scenario import Scenario, names, run_script

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)
EXCERPT = Path(__file__).resolve().parents[2] / "tools" / "excerpts" / "cards.json"
ORACLE = (
    "Draw cards equal to the greatest power among creatures you control.\n"
    "You may cast a spell with mana value 5 or less from your hand without paying its mana cost."
)
LIBRARY = ["Grizzly Bears", "Forest", "Forest", "Forest", "Forest", "Forest"]


def expertise_on_stack(scenario: Scenario) -> ObjectId:
    """P0's Rishkar's Expertise on the stack in P0's main phase, P0's library from ``LIBRARY``."""
    (expertise,) = scenario.stack(P0, ["Rishkar's Expertise"])
    scenario.library(P0, LIBRARY)
    scenario.at(Phase.PRECOMBAT_MAIN)
    return expertise


def test_its_definition_is_its_oracle_text() -> None:
    assert default_registry().get("Rishkar's Expertise") is RISHKARS_EXPERTISE
    assert RISHKARS_EXPERTISE.spell is not None and RISHKARS_EXPERTISE.spell.text == ORACLE
    card = load_card_excerpt(EXCERPT).get("Rishkar's Expertise")
    assert card.faces[0].oracle_text == ORACLE
    assert (card.faces[0].mana_cost, card.type_line) == ("{4}{G}{G}", "Sorcery")


def test_rishkars_expertise_draws_the_greatest_power() -> None:
    """Hill Giant (3) and Grizzly Bears (2): P0 draws 3 cards (121.1), one at a time (121.2).
    The drawn Grizzly Bears can then be cast; nothing else could."""
    scenario = Scenario(2)
    expertise = expertise_on_stack(scenario)
    scenario.battlefield(P0, ["Hill Giant", "Grizzly Bears"])
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1))
    drawn = records(state, CardDrawn)
    assert len(drawn) == 3 and all(d.player == P0 for d in drawn)
    assert names(state, Zone.hand(P0)) == ["Grizzly Bears", "Forest", "Forest"]
    assert request_of(state).kind is DecisionKind.CAST_DURING_RESOLUTION
    assert state.stack == [expertise]


def test_only_creatures_you_control_count() -> None:
    """Three players: P0's Grizzly Bears (2) counts; P1's Hill Giant (3) and P2's Hill Giant
    don't (108.4: "you control"). P0 draws 2."""
    scenario = Scenario(3)
    expertise_on_stack(scenario)
    scenario.battlefield(P0, ["Grizzly Bears"])
    scenario.battlefield(P1, ["Hill Giant"])
    scenario.battlefield(P2, ["Hill Giant"])
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1), pass_(P2))
    assert len(records(state, CardDrawn)) == 2


def test_with_no_creatures_draws_nothing_but_may_still_cast() -> None:
    """The ruling: with no creature of power above 0, P0 draws no cards but may still cast a
    spell. P0 controls no creature; their Hill Giant in hand is offered."""
    scenario = Scenario(2)
    expertise = expertise_on_stack(scenario)
    (giant,) = scenario.hand(P0, ["Hill Giant"])
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1))
    assert records(state, CardDrawn) == []
    assert CastSpellOption(giant, NORMAL, free(expertise)) in options(state)
    run_script(state, cast_during_resolution(giant, free(expertise)))
    assert names(state, STACK) == ["Hill Giant"]


def test_a_creature_with_0_power_draws_nothing() -> None:
    """Test Wall (0/4) is the greatest power, 0: no cards are drawn (121.1)."""
    scenario = Scenario(2)
    expertise_on_stack(scenario)
    scenario.battlefield(P0, ["Test Wall"])
    scenario.hand(P0, ["Hill Giant"])
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1))
    assert records(state, CardDrawn) == []
    assert request_of(state).kind is DecisionKind.CAST_DURING_RESOLUTION


def test_it_may_cast_a_card_it_drew() -> None:
    """The ruling: a card drawn by the first effect may be cast while performing the second.
    Grizzly Bears (2) draws the library's top two, the Bears among them; it is cast."""
    scenario = Scenario(2)
    expertise = expertise_on_stack(scenario)
    scenario.battlefield(P0, ["Grizzly Bears"])
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1))
    first, _ = (d.drawn for d in records(state, CardDrawn))
    assert first is not None
    assert options(state)[1] == CastSpellOption(first, NORMAL, free(expertise))
    run_script(state, cast_during_resolution(first, free(expertise)))
    assert names(state, STACK) == ["Grizzly Bears"]
    assert names(state, Zone.graveyard(P0)) == ["Rishkar's Expertise"]


def test_the_power_is_read_as_it_resolves() -> None:
    """The ruling: the greatest power is determined as it resolves (608.2h). With the Expertise
    on the stack, P0 controls only Test Wall (power 0); holding priority, P0 casts Ashcoat Bear
    (flash, 2/2), which resolves first. As the Expertise resolves the greatest power is 2: P0
    draws 2."""
    scenario = Scenario(2)
    expertise_on_stack(scenario)
    _, first, second = scenario.battlefield(P0, ["Test Wall", "Forest", "Forest"])
    (bear,) = scenario.hand(P0, ["Ashcoat Bear"])
    state = scenario.build()
    run_script(state, cast(bear), activate(first), activate(second), pass_(P0), pass_(P1))
    assert names(state, BATTLEFIELD) == ["Test Wall", "Forest", "Forest", "Ashcoat Bear"]
    assert records(state, CardDrawn) == []
    run_script(state, pass_(P0), pass_(P1))
    assert len(records(state, CardDrawn)) == 2


def test_it_goes_to_its_owners_graveyard_after_resolving() -> None:
    """608.2n: once both effects are done (nothing castable is in hand: P0 can only decline), it
    is put into its owner's graveyard and P0 receives priority (117.3b)."""
    scenario = Scenario(2)
    expertise_on_stack(scenario)
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1), decline())
    assert answered(state, DecisionKind.CAST_DURING_RESOLUTION) == 1
    assert names(state, Zone.graveyard(P0)) == ["Rishkar's Expertise"]
    request = request_of(state)
    assert (request.kind, request.player) == (DecisionKind.PRIORITY_ACTION, P0)
