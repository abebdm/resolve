"""Decks and games for engine tests, built from ``tests/scryfall_fixtures.py``.

No real card is implemented yet, so these decks use test-only definitions: a ``CardDefinition``
holds only a name so far. The scenario builder (``tests/scenario.py``, later in M0) will replace
most of this.
"""

from __future__ import annotations

from collections.abc import Sequence

from resolve.cards.registry import CardDefinition, CardRegistry
from resolve.data.cards import CardDatabase, parse_card, parse_oracle_cards
from resolve.decisions.request import DecisionAnswer, DecisionRequest
from resolve.decisions.spaces import AnswerValue, Pick
from resolve.engine.api import new_game, pending_decision, submit
from resolve.engine.deck import Deck, DeckCard
from resolve.errors import NotImplementedRule
from resolve.state.config import GameConfig
from resolve.state.game import GameState
from tests import scryfall_fixtures as fx

FOREST = DeckCard(parse_card(fx.FOREST), (CardDefinition("Forest"),))
ELVES = DeckCard(parse_card(fx.LLANOWAR_ELVES), (CardDefinition("Llanowar Elves"),))
DAYBREAKER = DeckCard(
    parse_card(fx.TRANSFORM_CARD),
    (CardDefinition("Test Daybreaker"), CardDefinition("Test Nightfall")),
)


def registry() -> CardRegistry:
    """A registry implementing the fixture cards used by these decks."""
    return CardRegistry(
        [
            CardDefinition("Forest"),
            CardDefinition("Llanowar Elves"),
            CardDefinition("Test Daybreaker"),
            CardDefinition("Test Nightfall"),
        ]
    )


def database() -> CardDatabase:
    """The default fixture cards."""
    return CardDatabase(parse_oracle_cards(fx.default_cards()))


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


def choose_starting_player(state: GameState, index: int) -> NotImplementedRule:
    """Answer the 103.1 decision; returns the 103.5 gap that M0 games stop at."""
    try:
        submit(state, answer(state, Pick(index)))
    except NotImplementedRule as gap:
        return gap
    raise AssertionError("expected the game to stop at the 103.5 gap")
