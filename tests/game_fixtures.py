"""Decks and games for engine tests, built from ``tests/scryfall_fixtures.py``.

Forests and Llanowar Elves use their real definitions (``resolve.cards.definitions``); the
other fixture cards use test-only definitions without abilities. Use these for tests that start a
game with ``new_game``; to set up a board state directly, use the scenario builder
(``tests/scenario.py``), which looks cards up in ``scenario_database()`` and
``scenario_registry()`` by default.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from resolve.cards.definitions import (
    basic_lands,
    mana_creatures,
    mana_rocks,
    nonbasic_lands,
    removal,
    vanilla_creatures,
)
from resolve.cards.primitives.effects import DealDamage, Destroy, DrawCards
from resolve.cards.primitives.refs import TargetRef
from resolve.cards.primitives.spells import Mode, SpellAbility
from resolve.cards.primitives.targets import ANY_TARGET, target
from resolve.cards.primitives.values import Fixed
from resolve.cards.registry import CardDefinition, CardRegistry
from resolve.data.cards import CardDatabase, parse_card, parse_oracle_cards
from resolve.data.types import CardType
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.request import DecisionAnswer, DecisionRequest
from resolve.decisions.spaces import (
    AnswerValue,
    ChooseOne,
    ChooseOrder,
    ChooseSubset,
    Order,
    PassOption,
    Pick,
    PickMany,
)
from resolve.engine.api import new_game, pending_decision, submit, view_for
from resolve.engine.deck import Deck, DeckCard
from resolve.engine.mulligans import KEEP
from resolve.engine.view import PlayerView
from resolve.errors import NotImplementedRule
from resolve.state.config import GameConfig
from resolve.state.game import GameState
from resolve.state.turn import Phase, Step
from tests import scryfall_fixtures as fx

FOREST = DeckCard(parse_card(fx.FOREST), (basic_lands.FOREST,))
ELVES = DeckCard(parse_card(fx.LLANOWAR_ELVES), (mana_creatures.LLANOWAR_ELVES,))
DAYBREAKER = DeckCard(
    parse_card(fx.TRANSFORM_CARD),
    (CardDefinition("Test Daybreaker"), CardDefinition("Test Nightfall")),
)


# The fixture spells' definitions (tests only).
# Test Shock deals 2 damage to any target.
TEST_SHOCK = CardDefinition(
    "Test Shock",
    spell=SpellAbility((Mode((ANY_TARGET,), (DealDamage(Fixed(2), (TargetRef(0),)),)),)),
)
# Draw a card.
TEST_PONDER = CardDefinition("Test Ponder", spell=SpellAbility((Mode((), (DrawCards(),)),)))
# Destroy target artifact.
TEST_SHATTER = CardDefinition(
    "Test Shatter",
    spell=SpellAbility((Mode((target(CardType.ARTIFACT),), (Destroy((TargetRef(0),)),)),)),
)


def registry() -> CardRegistry:
    """A registry implementing the fixture cards used by these decks."""
    return CardRegistry(
        [
            basic_lands.FOREST,
            mana_creatures.LLANOWAR_ELVES,
            CardDefinition("Test Daybreaker"),
            CardDefinition("Test Nightfall"),
        ]
    )


def database() -> CardDatabase:
    """The default fixture cards."""
    return CardDatabase(parse_oracle_cards(fx.default_cards()))


def scenario_registry() -> CardRegistry:
    """``registry()`` plus the other basic lands, the vanilla creatures, the mana rocks, mana
    creatures and nonbasic lands, the removal spells, the fixture instants (Test Shock, Test
    Shatter), sorcery (Test Ponder), split card, nonbasic Forest, Test Raptor, Test Mox ({0}),
    Test Ember ({1}{C}), Test Wall (0/4), Test Totem (an enchantment) and Test Artifact Land
    Creature: the scenario builder's default."""
    extra = (
        "Test Spark",
        "Test Frost",
        "Test Nonbasic Forest",
        "Test Land Creature",
        "Test Dual",
        "Test Wisp",
        "Test Star",
        "Test Wagon",
        "Test Raptor",
        "Test Mox",
        "Test Ember",
        "Test Wall",
        "Test Totem",
        "Test Artifact Land Creature",
    )
    lands = (basic_lands.PLAINS, basic_lands.ISLAND, basic_lands.SWAMP, basic_lands.MOUNTAIN)
    creatures = vanilla_creatures.DEFINITIONS
    return CardRegistry(
        [
            *(registry().get(n) for n in registry().names()),
            *lands,
            *creatures,
            *mana_rocks.DEFINITIONS,
            *(d for d in mana_creatures.DEFINITIONS if d is not mana_creatures.LLANOWAR_ELVES),
            *nonbasic_lands.DEFINITIONS,
            *removal.DEFINITIONS,
            TEST_SHOCK,
            TEST_PONDER,
            TEST_SHATTER,
            *map(CardDefinition, extra),
        ]
    )


def scenario_database() -> CardDatabase:
    """``database()`` plus the cards of ``scenario_registry()``: the scenario builder's default."""
    extra = [fx.INSTANT_CARD, fx.SORCERY_CARD, fx.NONBASIC_FOREST, fx.LAND_CREATURE, fx.DUAL_LAND]
    extra += [fx.GRIZZLY_BEARS, fx.SAVANNAH_LIONS, fx.HILL_GIANT, fx.ZERO_TOUGHNESS]
    extra += [fx.STAR_CREATURE, fx.VEHICLE, fx.SOL_RING, fx.ARCANE_SIGNET, fx.SELESNYA_SIGNET]
    extra += [fx.COMMAND_TOWER, fx.TEMPLE_OF_THE_FALSE_GOD, fx.AVACYNS_PILGRIM]
    extra += [fx.IXALLIS_LOREKEEPER, fx.TEST_RAPTOR, fx.TEST_MOX, fx.TEST_EMBER]
    extra += [fx.SWORDS_TO_PLOWSHARES, fx.CHANDRAS_IGNITION, fx.DECIMATE, fx.TEST_WALL]
    extra += [fx.TEST_SHATTER, fx.TEST_TOTEM, fx.TEST_ARTIFACT_LAND_CREATURE]
    lands = [fx.PLAINS, fx.ISLAND, fx.SWAMP, fx.MOUNTAIN]
    return CardDatabase(parse_oracle_cards([*fx.default_cards(), *lands, *extra]))


def deck(forests: int = 6, elves: int = 4, *, commanders: Sequence[DeckCard] = ()) -> Deck:
    """A small deck: forests first, then elves (deck order is library order before 103.3)."""
    return Deck((FOREST,) * forests + (ELVES,) * elves, tuple(commanders))


def decks(players: int, forests: int = 6, elves: int = 4) -> list[Deck]:
    """One ``deck(forests, elves)`` per player."""
    return [deck(forests, elves) for _ in range(players)]


def start(players: int = 2, seed: int = 1, config: GameConfig | None = None) -> GameState:
    """A new game, paused at the first decision (103.1)."""
    return new_game(config or GameConfig.standard(), decks(players), seed)


def answer(state: GameState, value: AnswerValue) -> DecisionAnswer:
    """An answer to the pending decision, from the player it's for."""
    request = pending_decision(state)
    assert request is not None
    return DecisionAnswer(request.id, request.player, value)


def request_of(state: GameState) -> DecisionRequest:
    """The pending decision (the game must not be over)."""
    request = pending_decision(state)
    assert request is not None
    return request


class Passer:
    """An agent that keeps every hand and passes every priority (for turn-structure tests).

    It discards the first cards of its hand when it must (514.1) and keeps any order offered.
    ``requests`` records every request it answered, with the turn's number, phase and step at
    that moment.
    """

    def __init__(self) -> None:
        self.requests: list[tuple[DecisionRequest, tuple[int, Phase, Step | None] | None]] = []

    def decide(self, view: PlayerView, request: DecisionRequest) -> DecisionAnswer:
        turn = view.turn
        self.requests.append(
            (request, None if turn is None else (turn.number, turn.phase, turn.step))
        )
        space = request.space
        match request.kind, space:
            case DecisionKind.PRIORITY_ACTION, ChooseOne(options=options):
                value: AnswerValue = Pick(options.index(PassOption()))
            case DecisionKind.MULLIGAN, ChooseOne(options=options):
                value = Pick(options.index(KEEP))
            case DecisionKind.DISCARD, ChooseSubset(minimum=minimum):
                value = PickMany(tuple(range(minimum)))
            case DecisionKind.ORDER_CARDS, ChooseOrder(options=options):
                value = Order(tuple(range(len(options))))
            case _:
                raise AssertionError(f"Passer can't answer {request.kind}: {request.prompt}")
        return DecisionAnswer(request.id, request.player, value)


def pass_until(
    state: GameState,
    done: Callable[[GameState], bool],
    agent: Passer | None = None,
    limit: int = 2000,
) -> Passer:
    """Answer with a ``Passer`` until ``done(state)`` or the game is over; returns the agent."""
    agent = Passer() if agent is None else agent
    for _ in range(limit):
        if done(state) or state.result is not None:
            return agent
        request = request_of(state)
        submit(state, agent.decide(view_for(state, request.player), request))
    raise AssertionError(f"not done after {limit} answers")


def started_game(
    players: int = 2,
    *,
    starting: int = 0,
    forests: int = 10,
    elves: int = 10,
    seed: int = 1,
    config: GameConfig | None = None,
    decks: Sequence[Deck] | None = None,
) -> GameState:
    """A new game whose players all kept their opening hands: at the first turn's first decision."""
    if decks is None:
        decks = [deck(forests, elves) for _ in range(players)]
    state = new_game(config or GameConfig.standard(), decks, seed)
    submit(state, answer(state, Pick(starting)))
    pass_until(state, lambda s: s.turn is not None)
    return state


def choose_starting_player(state: GameState, index: int) -> NotImplementedRule | None:
    """Answer the 103.1 decision; returns the rules gap the game stopped at, if any."""
    try:
        submit(state, answer(state, Pick(index)))
    except NotImplementedRule as gap:
        return gap
    return None
