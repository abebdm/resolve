"""Building the state a game starts from (103; docs/decisions.md 2026-10-18).

``initial_state`` creates the players and every card's object in its starting zone, but runs no
task: ``new_game`` adds the ``StartGame`` task and runs it. Tests can use ``initial_state`` to get
a state and push their own tasks.

- Players sit in deck order, which is also clockwise order; deck ``i`` is player ``i``'s.
- Each player starts at the configured life total (103.4, 103.4c).
- Each card gets a ``CardId``, in seat order, commanders first, then in deck order.
- Each deck card becomes an object in its owner's library, in deck order. The libraries are
  shuffled by ``StartGame`` (103.3).
- With the Commander rules, each commander becomes a face-up object in the command zone
  (103.2c, 903.6).
"""

from __future__ import annotations

from collections.abc import Sequence

from resolve.engine.deck import Deck, DeckCard
from resolve.errors import DeckError
from resolve.state.config import GameConfig
from resolve.state.game import Card, GameState, Player, create_object
from resolve.state.ids import CardId, PlayerId
from resolve.state.rng import Rng
from resolve.state.zones import COMMAND, Zone


def initial_state(config: GameConfig, decks: Sequence[Deck], seed: int) -> GameState:
    """The state before the game starts: players, cards and objects, and no tasks yet."""
    if len(decks) < 2:
        raise DeckError(f"a game needs at least two players (100.1), got {len(decks)} deck(s)")
    for seat, deck in enumerate(decks):
        if deck.commanders and config.commander is None:
            raise DeckError(f"deck {seat} has commanders but the game has no Commander rules")

    state = GameState(
        config=config,
        seed=seed,
        rng=Rng.from_seed(seed),
        players=[Player(PlayerId(seat), config.starting_life) for seat in range(len(decks))],
    )
    for seat, deck in enumerate(decks):
        owner = PlayerId(seat)
        for deck_card in deck.commanders:
            card = _add_card(state, owner, deck_card)
            create_object(state, card=card.id, owner=owner, zone=COMMAND)
        for deck_card in deck.cards:
            card = _add_card(state, owner, deck_card)
            create_object(state, card=card.id, owner=owner, zone=Zone.library(owner))
    return state


def _add_card(state: GameState, owner: PlayerId, deck_card: DeckCard) -> Card:
    card = Card(CardId(len(state.cards) + 1), owner, deck_card.data, deck_card.definitions)
    state.cards[card.id] = card
    return card
