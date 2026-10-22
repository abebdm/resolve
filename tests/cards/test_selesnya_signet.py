"""Selesnya Signet: {2}, Artifact. "{1}, {T}: Add {G}{W}."

Oracle text checked against the Scryfall snapshot of 2026-10-21 (``tools/excerpts/cards.json``),
which has no rulings for it.

From the pinned CR:

- 605.1a: an ability with a mana cost is still a mana ability. 602.2b, 601.2g-h: its cost is
  paid like a spell's: the player may first activate mana abilities (605.3a), then pays; the
  {1} takes any mana (107.4b).
- 605.3c: once a player begins to activate a mana ability, that ability can't be activated again
  until it has resolved, so the Signet isn't offered to pay for itself.
- 118.3, 733.1: a cost that can't be paid makes the activation illegal; it is reversed, and the
  player may reverse the mana abilities they activated while making it. 733.2: they keep
  priority, and earlier passes still count.
- 733.1: a mana ability can't be reversed while one whose cost its mana paid is kept ("unless
  mana from those abilities ... was spent on another mana ability that wasn't reversed").
"""

from __future__ import annotations

from pathlib import Path

import pytest

from resolve.cards.definitions.mana_rocks import SELESNYA_SIGNET
from resolve.cards.registry import default_registry
from resolve.data.cards import load_card_excerpt
from resolve.data.types import Color
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import (
    ActivateAbilityOption,
    ChooseOne,
    ChooseSubset,
    ManaActivationOption,
    PickMany,
)
from resolve.engine.api import submit
from resolve.engine.payment import PAY
from resolve.errors import InvalidAnswer
from resolve.events.mana import ManaSpent
from resolve.events.spells import ActionReversed, SpellCast
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import Mana, ManaType
from resolve.state.turn import Phase
from resolve.state.zones import Zone
from tests.casting_support import (
    activate,
    activate_with_priority,
    answered,
    cast,
    choose_color,
    counts,
    options,
    pass_,
    pay,
    records,
    reverse,
)
from tests.game_fixtures import answer, request_of
from tests.scenario import Scenario, run_script

P0, P1 = PlayerId(0), PlayerId(1)
G, W, C = ManaType.GREEN, ManaType.WHITE, ManaType.COLORLESS
EXCERPT = Path(__file__).resolve().parents[2] / "tools" / "excerpts" / "cards.json"


def test_its_definition_is_its_oracle_text() -> None:
    assert default_registry().get("Selesnya Signet") is SELESNYA_SIGNET
    (ability,) = SELESNYA_SIGNET.abilities
    assert ability.text == "{1}, {T}: Add {G}{W}."
    card = load_card_excerpt(EXCERPT).get("Selesnya Signet")
    assert card.faces[0].oracle_text == "{1}, {T}: Add {G}{W}."
    assert card.faces[0].mana_cost == "{2}"


def signet_and_forest() -> tuple[Scenario, ObjectId, ObjectId]:
    scenario = Scenario(2)
    signet, forest = scenario.battlefield(P0, ["Selesnya Signet", "Forest"])
    return scenario, signet, forest


def test_605_3a_signets_cost_can_be_paid_by_tapping_a_land_during_its_activation() -> None:
    """With priority: activating the Signet asks for mana abilities to pay its {1}; the Forest is
    offered and the Signet isn't (605.3c). The Forest's {G} pays {1} (the only way: not asked),
    then the Signet taps and adds {G}{W}."""
    scenario, signet, forest = signet_and_forest()
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, activate_with_priority(signet))
    request = request_of(state)
    assert request.kind is DecisionKind.ACTIVATE_MANA_ABILITIES
    assert request.source == signet
    assert request.space == ChooseOne((PAY, ActivateAbilityOption(forest, 0)))
    run_script(state, activate(forest))
    assert answered(state, DecisionKind.PAY_COSTS) == 0
    (spent,) = records(state, ManaSpent)
    assert spent.mana == (Mana(G, forest),)
    assert state.objects[signet].tapped and state.objects[forest].tapped
    assert state.player(P0).mana_pool == [Mana(G, signet), Mana(W, signet)]
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION


def test_605_3a_floating_mana_pays_the_signet_without_a_question() -> None:
    """{G} already in the pool and no other mana ability: nothing to ask; {G} pays {1}."""
    scenario = Scenario(2)
    (signet,) = scenario.battlefield(P0, ["Selesnya Signet"])
    scenario.mana(P0, G)
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, activate_with_priority(signet))
    assert state.player(P0).mana_pool == [Mana(G, signet), Mana(W, signet)]


def test_605_3a_the_signet_pays_for_a_spell_after_a_land_pays_for_the_signet() -> None:
    """Casting Grizzly Bears ({1}{G}): activate the Signet, pay its {1} with the Forest, then the
    Signet's {G}{W} pays {1}{G} (one way only)."""
    scenario, signet, forest = signet_and_forest()
    (bears,) = scenario.hand(P0, ["Grizzly Bears"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(bears, P0), activate(signet), activate(forest))
    (cast_event,) = records(state, SpellCast)
    assert sorted(cast_event.mana_spent, key=repr) == sorted(
        (Mana(G, signet), Mana(W, signet)), key=repr
    )
    assert state.player(P0).mana_pool == []


def test_605_3c_the_signet_cant_be_activated_again_while_it_is_being_activated() -> None:
    """Two Signets and a Forest: activating the first offers the second and the Forest, never the
    first itself."""
    scenario = Scenario(2)
    first, second, forest = scenario.battlefield(
        P0, ["Selesnya Signet", "Selesnya Signet", "Forest"]
    )
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, activate_with_priority(first))
    assert options(state) == (
        PAY,
        ActivateAbilityOption(second, 0),
        ActivateAbilityOption(forest, 0),
    )
    # The second Signet's own payment offers the Forest but neither Signet (605.3c).
    run_script(state, activate(second))
    assert options(state) == (PAY, ActivateAbilityOption(forest, 0))
    run_script(state, activate(forest))
    # The second Signet's {G}{W} is in the pool; one unit pays the first's {1} (asked: G or W).
    assert request_of(state).kind is DecisionKind.PAY_COSTS


def test_733_1_a_signet_with_no_mana_for_its_cost_is_reversed() -> None:
    """No mana and no other mana ability: the {1} can't be paid (118.3), nothing was activated
    meanwhile, so nothing is asked. The Signet is untapped, nothing is added, a public
    ActionReversed is logged, P0 keeps priority (733.2) and P1's earlier pass still counts: P0's
    pass ends the step."""
    scenario = Scenario(2)
    (signet,) = scenario.battlefield(P0, ["Selesnya Signet"])
    scenario.at(Phase.PRECOMBAT_MAIN, passed=[P1], priority=P0)
    state = scenario.build()
    run_script(state, activate_with_priority(signet))
    assert answered(state, DecisionKind.REVERSE_MANA_ABILITIES) == 0
    assert not state.objects[signet].tapped
    assert state.player(P0).mana_pool == []
    (reversed_,) = records(state, ActionReversed)
    assert reversed_.player == P0 and reversed_.kept == ()
    request = request_of(state)
    assert request.kind is DecisionKind.PRIORITY_ACTION and request.player == P0
    assert state.turn is not None and state.turn.passed == [P1]
    run_script(state, pass_(P0))
    assert state.turn.phase is not Phase.PRECOMBAT_MAIN


def test_733_1_an_ability_activated_for_a_failed_signet_may_be_reversed_with_it() -> None:
    """P0 activates the Signet with priority and taps Ixalli's Lorekeeper to pay its {1}, but the
    Lorekeeper's mana can't be spent on a non-Dinosaur's ability (106.6): the {1} can't be paid.
    P0 is asked which of the abilities activated meanwhile to reverse; reversing the Lorekeeper's
    leaves everything as it was. (Keeping it: see ``test_ixallis_lorekeeper.py``.)"""
    scenario = Scenario(2)
    signet, lorekeeper = scenario.battlefield(P0, ["Selesnya Signet", "Ixalli's Lorekeeper"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, activate_with_priority(signet), activate(lorekeeper), choose_color(Color.RED))
    request = request_of(state)
    assert request.kind is DecisionKind.REVERSE_MANA_ABILITIES
    assert request.source == signet
    assert request.space == ChooseSubset((ManaActivationOption(0, lorekeeper, 0),), 0, 1)
    run_script(state, reverse(ManaActivationOption(0, lorekeeper, 0)))
    assert not state.objects[signet].tapped and not state.objects[lorekeeper].tapped
    assert state.player(P0).mana_pool == []
    assert request_of(state).kind is DecisionKind.PRIORITY_ACTION


def failed_giant() -> tuple[GameState, ObjectId, ObjectId, ObjectId]:
    """P0 tries to cast Hill Giant ({3}{R}): activates the Signet and taps the Forest to pay its
    {1}; no mana ability is left, so the payment is made at once: {G}{W} can't pay {3}{R}. The
    reversal decision is pending."""
    scenario, signet, forest = signet_and_forest()
    (giant,) = scenario.hand(P0, ["Hill Giant"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(giant, P0), activate(signet), activate(forest))
    return state, giant, signet, forest


def test_733_1_a_kept_ability_must_keep_what_paid_for_it() -> None:
    """The activations are listed in the order they began: the Signet, then the Forest (activated
    while paying for the Signet). Reversing the Forest but keeping the Signet is refused (its {1}
    was paid with the Forest's mana); reversing both, neither, or only the Signet is accepted."""
    state, giant, signet, forest = failed_giant()
    request = request_of(state)
    assert request.kind is DecisionKind.REVERSE_MANA_ABILITIES
    signet_option = ManaActivationOption(0, signet, 0)
    forest_option = ManaActivationOption(1, forest, 0)
    assert request.space == ChooseSubset((signet_option, forest_option), 0, 2)
    with pytest.raises(InvalidAnswer, match=r"733\.1"):
        submit(state, answer(state, PickMany((1,))))
    assert request_of(state) == request

    # Reverse both: as if nothing happened.
    run_script(state, reverse(signet_option, forest_option))
    assert not state.objects[signet].tapped and not state.objects[forest].tapped
    assert state.player(P0).mana_pool == []
    assert giant in state.player(P0).hand

    # Keep both: both stay tapped, the Signet's {G}{W} stays.
    state, giant, signet, forest = failed_giant()
    run_script(state, reverse())
    assert state.objects[signet].tapped and state.objects[forest].tapped
    assert state.player(P0).mana_pool == [Mana(G, signet), Mana(W, signet)]
    assert state.objects[giant].zone == Zone.hand(P0)

    # Reverse only the Signet: the Forest stays tapped and its {G} is back in the pool.
    state, giant, signet, forest = failed_giant()
    run_script(state, reverse(signet_option))
    assert not state.objects[signet].tapped and state.objects[forest].tapped
    assert state.player(P0).mana_pool == [Mana(G, forest)]
    (reversed_,) = records(state, ActionReversed)
    assert reversed_.kept == (forest,)


def test_733_1_an_ability_kept_from_a_failed_signet_in_a_cast_is_listed_without_it() -> None:
    """P0 casts Grizzly Bears, activates the Signet and taps Ixalli's Lorekeeper for its {1}; the
    Lorekeeper's mana can't pay a non-Dinosaur's ability (106.6), so the Signet's activation is
    reversed and P0 keeps the Lorekeeper's. P0 then taps the Forest, but the cast still fails
    (the Lorekeeper's mana can't pay for Bears either). The cast's reversal lists the Lorekeeper
    and the Forest, in the order they began, and not the reversed Signet."""
    scenario = Scenario(2)
    (bears,) = scenario.hand(P0, ["Grizzly Bears"])
    signet, lorekeeper, forest = scenario.battlefield(
        P0, ["Selesnya Signet", "Ixalli's Lorekeeper", "Forest"]
    )
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(bears, P0), activate(signet), activate(lorekeeper))
    run_script(state, choose_color(Color.GREEN), pay())
    request = request_of(state)
    assert request.kind is DecisionKind.REVERSE_MANA_ABILITIES and request.source == signet
    run_script(state, reverse())  # keep the Lorekeeper's ability
    assert not state.objects[signet].tapped and state.objects[lorekeeper].tapped
    assert options(state) == (
        PAY,
        ActivateAbilityOption(signet, 0),
        ActivateAbilityOption(forest, 0),
    )
    run_script(state, activate(forest), pay())
    request = request_of(state)
    # The spell on the stack (a new object, 400.7) is the decision's source.
    assert request.kind is DecisionKind.REVERSE_MANA_ABILITIES
    assert request.source == state.stack[-1]
    lore_option = ManaActivationOption(0, lorekeeper, 0)
    forest_option = ManaActivationOption(1, forest, 0)
    assert request.space == ChooseSubset((lore_option, forest_option), 0, 2)
    run_script(state, reverse(forest_option))
    assert state.objects[lorekeeper].tapped and not state.objects[forest].tapped
    assert not state.objects[signet].tapped
    assert len(state.player(P0).mana_pool) == 1
    assert state.player(P0).mana_pool[0].source == lorekeeper
    assert bears in state.player(P0).hand


def two_signets_for_a_giant() -> tuple[GameState, ObjectId, ObjectId, ObjectId]:
    """P0 tries to cast Hill Giant: activates Signet 1; to pay its {1}, activates Signet 2, whose
    {1} the Forest pays; Signet 2's {G} pays Signet 1's {1} (asked: G or W). {W}{G}{W} can't pay
    {3}{R}: the reversal is pending, listing Signet 1, Signet 2, the Forest."""
    scenario = Scenario(2)
    first, second, forest = scenario.battlefield(
        P0, ["Selesnya Signet", "Selesnya Signet", "Forest"]
    )
    (giant,) = scenario.hand(P0, ["Hill Giant"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, cast(giant, P0), activate(first), activate(second), activate(forest))
    run_script(state, counts(1, 0))
    return state, first, second, forest


def test_733_1_the_dependency_reaches_through_two_nested_activations() -> None:
    state, first, second, forest = two_signets_for_a_giant()
    request = request_of(state)
    assert request.space == ChooseSubset(
        (
            ManaActivationOption(0, first, 0),
            ManaActivationOption(1, second, 0),
            ManaActivationOption(2, forest, 0),
        ),
        0,
        3,
    )
    # Keeping Signet 1 while reversing Signet 2, whose {G} paid it: refused.
    with pytest.raises(InvalidAnswer, match=r"733\.1"):
        submit(state, answer(state, PickMany((1,))))
    # Keeping both Signets while reversing the Forest, whose {G} paid Signet 2: refused.
    with pytest.raises(InvalidAnswer, match=r"733\.1"):
        submit(state, answer(state, PickMany((2,))))
    # Reversing only Signet 1: Signet 2 and the Forest stay tapped; Signet 2's {G}{W} is back.
    submit(state, answer(state, PickMany((0,))))
    assert not state.objects[first].tapped
    assert state.objects[second].tapped and state.objects[forest].tapped
    assert state.player(P0).mana_pool == [Mana(G, second), Mana(W, second)]


def test_733_1_identical_mana_from_before_the_action_counts_as_what_was_spent() -> None:
    """{C} from Sol Ring was already in P0's pool. P0 taps Sol Ring again while casting Hill
    Giant and pays the Signet's {1} with {C}: that unit and the Ring's new ones are identical, so
    the payment can't tell them apart. Reversing the Ring while keeping the Signet is accepted
    (the {C} spent counts as the one that was there before, docs/decisions.md); afterwards that
    {C} is gone and the Signet's {G}{W} stays."""
    scenario = Scenario(2)
    ring, signet = scenario.battlefield(P0, ["Sol Ring", "Selesnya Signet"])
    (giant,) = scenario.hand(P0, ["Hill Giant"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    state.player(P0).mana_pool.append(Mana(C, ring))
    run_script(state, cast(giant, P0), activate(ring), activate(signet))
    request = request_of(state)
    assert request.space == ChooseSubset(
        (ManaActivationOption(0, ring, 0), ManaActivationOption(1, signet, 0)), 0, 2
    )
    run_script(state, reverse(ManaActivationOption(0, ring, 0)))
    assert not state.objects[ring].tapped and state.objects[signet].tapped
    assert state.player(P0).mana_pool == [Mana(G, signet), Mana(W, signet)]


def test_733_1_identical_mana_already_spent_elsewhere_is_no_excuse() -> None:
    """The {C} that was there before paid Signet 1; Signet 2's {1} was then paid with {C} the
    Ring made during the cast. Keeping both Signets while reversing the Ring is refused."""
    scenario = Scenario(2)
    ring, first, second = scenario.battlefield(
        P0, ["Sol Ring", "Selesnya Signet", "Selesnya Signet"]
    )
    (giant,) = scenario.hand(P0, ["Hill Giant"])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    state.player(P0).mana_pool.append(Mana(C, ring))
    run_script(state, cast(giant, P0), activate(first), pay())  # the old {C} pays Signet 1
    run_script(state, activate(ring), activate(second), counts(0, 0, 1))  # a new {C} pays 2
    request = request_of(state)
    assert request.kind is DecisionKind.REVERSE_MANA_ABILITIES
    assert request.space == ChooseSubset(
        (
            ManaActivationOption(0, first, 0),
            ManaActivationOption(1, ring, 0),
            ManaActivationOption(2, second, 0),
        ),
        0,
        3,
    )
    with pytest.raises(InvalidAnswer, match=r"733\.1"):
        submit(state, answer(state, PickMany((1,))))
    submit(state, answer(state, PickMany((1, 2))))  # reverse the Ring and Signet 2: accepted
    assert state.objects[first].tapped and not state.objects[second].tapped
    assert state.player(P0).mana_pool == [Mana(G, first), Mana(W, first)]


def test_117_4_a_completed_activation_starts_passing_over() -> None:
    """P1 had passed; P0 activates the Signet and pays with a Forest. It completes, so it was an
    action: P1's pass no longer counts (contrast with the reversed Signet, 733.2)."""
    scenario, signet, forest = signet_and_forest()
    scenario.at(Phase.PRECOMBAT_MAIN, passed=[P1], priority=P0)
    state = scenario.build()
    run_script(state, activate_with_priority(signet), activate(forest))
    assert state.turn is not None and state.turn.passed == []
    run_script(state, pass_(P0))
    assert request_of(state).player == P1 and state.turn.phase is Phase.PRECOMBAT_MAIN
