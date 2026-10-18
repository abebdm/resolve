"""The engine's public API (design.md §3).

```python
state = new_game(config, decks, seed)
while (request := pending_decision(state)) is not None:
    answer = agents[request.player].decide(view_for(state, request.player), request)
    submit(state, answer)
```

After ``InvalidAnswer`` the same decision is still pending. After ``NotImplementedRule`` or
``EngineError`` the state must not be played further; ``pending_decision`` then raises
``EngineError``. Until the turn structure exists (roadmap M1), every game reaches
``NotImplementedRule("103.8: ...")`` once the mulligans are over.
"""

from __future__ import annotations

from collections.abc import Sequence

from resolve.decisions.request import DecisionAnswer, DecisionRequest
from resolve.engine.deck import Deck
from resolve.engine.loop import run, submit_answer
from resolve.engine.setup import initial_state
from resolve.engine.start import StartGame
from resolve.engine.view import PlayerView
from resolve.engine.view import view_for as _view_for
from resolve.errors import EngineError
from resolve.state.config import GameConfig
from resolve.state.game import GameState
from resolve.state.ids import PlayerId


def new_game(config: GameConfig, decks: Sequence[Deck], seed: int) -> GameState:
    """Start a game and run it to the first decision.

    Deck ``i`` belongs to player ``i``; players sit in that (clockwise) order. ``seed`` (an integer
    in ``[0, 2**64)``) determines all randomness. Raises ``DeckError`` for unusable decks.
    """
    state = initial_state(config, decks, seed)
    state.tasks.append(StartGame())
    run(state)
    return state


def pending_decision(state: GameState) -> DecisionRequest | None:
    """The decision the game is waiting for, or ``None`` if the game is over."""
    if state.result is not None:
        return None
    if state.pending is None:
        raise EngineError("the engine isn't waiting for a decision (it stopped with an error)")
    return state.pending


def view_for(state: GameState, player: PlayerId) -> PlayerView:
    """What ``player`` may see of the game (design.md §9)."""
    return _view_for(state, player)


def submit(state: GameState, answer: DecisionAnswer) -> None:
    """Answer the pending decision and run until the next one or the end of the game.

    Raises ``InvalidAnswer``, leaving the state unchanged, if the answer isn't legal.
    """
    submit_answer(state, answer)
