"""Decks and games for engine tests, built from ``tests/scryfall_fixtures.py``.

Forests and Llanowar Elves use their real definitions (``resolve.cards.definitions``); the
other fixture cards use test-only definitions without abilities. Use these for tests that start a
game with ``new_game``; to set up a board state directly, use the scenario builder
(``tests/scenario.py``), which looks cards up in ``scenario_database()`` and
``scenario_registry()`` by default.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.cards.definitions import (
    basic_lands,
    card_draw,
    combat,
    cost_reducers,
    counterspells,
    keyword_examples,
    mana_creatures,
    mana_rocks,
    nonbasic_lands,
    removal,
    vanilla_creatures,
)
from resolve.cards.keywords import (
    ColorQuality,
    Everything,
    Flash,
    Flying,
    Haste,
    Hexproof,
    Indestructible,
    Menace,
    MulticoloredQuality,
    Protection,
    protection_from_each_color,
)
from resolve.cards.primitives.abilities import ActivatedManaAbility
from resolve.cards.primitives.combat import PowerBlockRestriction
from resolve.cards.primitives.cost_modifiers import CostModifier, ModifierStep, SpellCostModifier
from resolve.cards.primitives.costs import TapSelfCost
from resolve.cards.primitives.effects import AddMana, DealDamage, Destroy, DrawCards
from resolve.cards.primitives.refs import TargetRef
from resolve.cards.primitives.spells import Mode, ModeChoice, SpellAbility
from resolve.cards.primitives.statics import CantBeCountered
from resolve.cards.primitives.targets import ANY_TARGET, target
from resolve.cards.primitives.values import Fixed, X
from resolve.cards.primitives.words import ColorWord
from resolve.cards.registry import CardDefinition, CardRegistry
from resolve.data.cards import CardDatabase, parse_card, parse_oracle_cards
from resolve.data.mana_cost import ManaCost
from resolve.data.types import CardType, Color
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.request import DecisionAnswer, DecisionRequest
from resolve.decisions.spaces import (
    AnswerValue,
    Assignment,
    ChooseAssignment,
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
from resolve.state.mana import ManaType
from resolve.state.turn import Phase, Step
from tests import scryfall_fixtures as fx

if TYPE_CHECKING:
    from resolve.state.ids import ObjectId, PlayerId

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

# Test Blaze deals X damage to any target.
TEST_BLAZE = CardDefinition(
    "Test Blaze",
    spell=SpellAbility((Mode((ANY_TARGET,), (DealDamage(X(), (TargetRef(0),)),)),)),
)
# Test Twin Blaze ({X}{X}{R}) deals X damage to any target.
TEST_TWIN_BLAZE = CardDefinition("Test Twin Blaze", spell=TEST_BLAZE.spell)
# Choose two — • Destroy target artifact. • Destroy target enchantment. • Draw a card.
TEST_COMMAND = CardDefinition(
    "Test Command",
    spell=SpellAbility(
        (
            Mode((target(CardType.ARTIFACT),), (Destroy((TargetRef(0),)),)),
            Mode((target(CardType.ENCHANTMENT),), (Destroy((TargetRef(0),)),)),
            Mode((), (DrawCards(),)),
        ),
        ModeChoice(2, 2),
    ),
)

# The fixture cards of M2.8's keywords (docs/primitives.md).
_RED = ColorQuality(ColorWord(Color.RED))
TEST_REDPROOF_BEAR = CardDefinition("Test Redproof Bear", abilities=(Hexproof(_RED),))
TEST_MULTIPROOF_KNIGHT = CardDefinition(
    "Test Multiproof Knight", abilities=(Protection(MulticoloredQuality()),)
)
TEST_PRISMATIC_KNIGHT = CardDefinition(
    "Test Prismatic Knight", abilities=protection_from_each_color()
)
TEST_UNTOUCHABLE = CardDefinition("Test Untouchable", abilities=(Protection(Everything()),))
TEST_TWIN_FLASH = CardDefinition("Test Twin Flash", abilities=(Flash(), Flash()))
TEST_INDESTRUCTIBLE_WISP = CardDefinition("Test Indestructible Wisp", abilities=(Indestructible(),))
# Haste; {T}: Add {G}. (702.10c), and the same with two instances of haste (702.10d).
_TAP_FOR_GREEN = ActivatedManaAbility((TapSelfCost(),), AddMana((ManaType.GREEN,)))
TEST_HASTY_ELVES = CardDefinition("Test Hasty Elves", abilities=(Haste(), _TAP_FOR_GREEN))
TEST_TWICE_HASTY_ELVES = CardDefinition(
    "Test Twice Hasty Elves", abilities=(Haste(), Haste(), _TAP_FOR_GREEN)
)
# M3.4: Champion of Lambholt's restriction alone, and flying with menace (509.1b).
TEST_LAMBHOLT_WARDEN = CardDefinition("Test Lambholt Warden", abilities=(PowerBlockRestriction(),))
TEST_FLYING_BRUTE = CardDefinition("Test Flying Brute", abilities=(Flying(), Menace()))
# This spell can't be countered. Test Stubborn Spell deals 1 damage to any target.
TEST_STUBBORN_SPELL = CardDefinition(
    "Test Stubborn Spell",
    abilities=(CantBeCountered(),),
    spell=SpellAbility((Mode((ANY_TARGET,), (DealDamage(Fixed(1), (TargetRef(0),)),)),)),
)
# Test Gold Shock ({R}{W}) deals 2 damage to any target.
TEST_GOLD_SHOCK = CardDefinition("Test Gold Shock", spell=TEST_SHOCK.spell)
# An adventurer (715.2): Test Adventurer, a vanilla creature, and Test Quest, "Draw a card."
TEST_ADVENTURER = CardDefinition("Test Adventurer")
TEST_QUEST = CardDefinition("Test Quest", spell=TEST_PONDER.spell)


@dataclass(frozen=True)
class IncreaseGeneric(CostModifier):
    """Test-only: increase a cost by ``amount`` generic mana (601.2f). The first real increase is
    the commander tax (903.8, M7)."""

    amount: int

    @property
    def step(self) -> ModifierStep:
        return ModifierStep.INCREASE

    def apply(self, cost: ManaCost) -> ManaCost:
        return cost.with_generic(cost.generic + self.amount)


@dataclass(frozen=True)
class SpellCostIncrease(SpellCostModifier):
    """Test-only: "Spells cost {1} more to cast." (601.2f), for every spell, whoever casts it."""

    def modifier(
        self, state: GameState, source: ObjectId, spell: ObjectId, caster: PlayerId
    ) -> CostModifier | None:
        return IncreaseGeneric(1)

    @property
    def text(self) -> str:
        return "Spells cost {1} more to cast."


# Spells cost {1} more to cast.
TEST_THORN = CardDefinition("Test Thorn", abilities=(SpellCostIncrease(),))
# Test Growth ({X}{G}): a green sorcery with {X} and no text.
TEST_GROWTH = CardDefinition("Test Growth")
# Test Insight (no mana cost): "Draw a card."
TEST_INSIGHT = CardDefinition("Test Insight", spell=TEST_PONDER.spell)


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
    Test Ember ({1}{C}), Test Wall (0/4), Test Regrower (4/3) and Test Spawn (2/3), Test Totem
    (an enchantment), Test Artifact Land Creature, the keyword example cards, the combat-rules
    cards (Palace Guard, Phantom Warrior), Cryptic Command, M2.8's keyword fixtures, Test
    Lambholt Warden and Test Flying Brute (and an
    adventurer, Test Adventurer // Test Quest), the cost reducers, Test Thorn (a cost increase),
    Test Growth ({X}{G}), Rishkar's Expertise, Test Two-Tone ({1}{W/U}{W/U}, no text), Test
    Insight (no mana cost) and Test Quake // Test Pebble (a split card of mana value 8 whose
    right half is 2): the scenario builder's default."""
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
        "Test Regrower",
        "Test Spawn",
        "Test Totem",
        "Test Artifact Land Creature",
        "Test Artifact Totem",
        "Test Two-Tone",
        "Test Quake",
        "Test Pebble",
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
            TEST_BLAZE,
            TEST_TWIN_BLAZE,
            TEST_COMMAND,
            *keyword_examples.DEFINITIONS,
            *combat.DEFINITIONS,
            *counterspells.DEFINITIONS,
            TEST_REDPROOF_BEAR,
            TEST_MULTIPROOF_KNIGHT,
            TEST_PRISMATIC_KNIGHT,
            TEST_UNTOUCHABLE,
            TEST_TWIN_FLASH,
            TEST_INDESTRUCTIBLE_WISP,
            TEST_HASTY_ELVES,
            TEST_TWICE_HASTY_ELVES,
            TEST_LAMBHOLT_WARDEN,
            TEST_FLYING_BRUTE,
            TEST_STUBBORN_SPELL,
            TEST_GOLD_SHOCK,
            TEST_ADVENTURER,
            TEST_QUEST,
            *cost_reducers.DEFINITIONS,
            TEST_THORN,
            TEST_GROWTH,
            *card_draw.DEFINITIONS,
            TEST_INSIGHT,
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
    extra += [fx.TEST_REGROWER, fx.TEST_SPAWN]
    extra += [fx.TEST_SHATTER, fx.TEST_TOTEM, fx.TEST_ARTIFACT_LAND_CREATURE]
    extra += [fx.FIERY_CONFLUENCE, fx.TEST_BLAZE, fx.TEST_TWIN_BLAZE, fx.TEST_COMMAND]
    extra += [fx.TEST_ARTIFACT_TOTEM]
    extra += [fx.ASHCOAT_BEAR, fx.GLADECOVER_SCOUT, fx.HUMBLE_BUDOKA, fx.DARKSTEEL_RELIC]
    extra += [fx.DARKSTEEL_MYR, fx.REPENTANT_BLACKSMITH, fx.NACATL_SAVAGE, fx.CANCEL]
    extra += [fx.CRYPTIC_COMMAND, fx.TEST_REDPROOF_BEAR, fx.TEST_MULTIPROOF_KNIGHT]
    extra += [fx.TEST_PRISMATIC_KNIGHT, fx.TEST_UNTOUCHABLE, fx.TEST_TWIN_FLASH]
    extra += [fx.TEST_INDESTRUCTIBLE_WISP, fx.TEST_STUBBORN_SPELL, fx.TEST_GOLD_SHOCK]
    extra += [fx.TEST_HASTY_ELVES, fx.TEST_TWICE_HASTY_ELVES]
    extra += [fx.RAGING_GOBLIN, fx.ALABORN_GRENADIER, fx.WALL_OF_STONE, fx.PALACE_GUARD]
    extra += [fx.WIND_DRAKE, fx.GIANT_SPIDER, fx.DERANGED_WHELP, fx.HIGHBORN_GHOUL]
    extra += [fx.SEVERED_LEGION, fx.BOG_RAIDERS, fx.PHANTOM_WARRIOR]
    extra += [fx.TEST_LAMBHOLT_WARDEN, fx.TEST_FLYING_BRUTE]
    extra += [fx.TEST_ADVENTURER, fx.EMERALD_MEDALLION, fx.KINJALLIS_CALLER, fx.TEST_THORN]
    extra += [fx.TEST_GROWTH, fx.RISHKARS_EXPERTISE, fx.TEST_TWO_TONE, fx.TEST_INSIGHT]
    extra += [fx.BIG_SPLIT_CARD]
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
    """An agent that keeps every hand and passes every priority (for turn-structure tests), and
    declares no attackers or blockers.

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
            case DecisionKind.DECLARE_ATTACKERS, ChooseAssignment(items=items):
                value = Assignment(((),) * len(items))  # 508.1a: no creature attacks
            case DecisionKind.DECLARE_BLOCKERS, ChooseAssignment(items=items):
                value = Assignment(((),) * len(items))  # 509.1a: no creature blocks
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
