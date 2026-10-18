"""The driver loop: ask each decision's player for an answer and submit it (design.md §3).

```python
while (request := pending_decision(state)) is not None:
    answer = agents[request.player].decide(view_for(state, request.player), request)
    submit(state, answer)
```

``play`` is that loop with two additions: it can stop after a number of answers, and it can let
an agent try again after a rejected answer (a human mistyping, a random agent hitting a rule the
answer space can't express). Engine errors, including ``NotImplementedRule``, propagate.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from resolve.agents.base import Agent
from resolve.engine.api import pending_decision, submit, view_for
from resolve.errors import EngineError, InvalidAnswer
from resolve.state.game import GameState

# How many rejected answers ``play`` accepts for one decision, when retrying is on, before it
# gives up. An agent answering inside the answer space can be rejected only by a task's
# ``check_answer``; a decision rejecting this many answers in a row is almost surely an engine
# bug (a space with no legal answer).
MAX_ATTEMPTS = 100


def agent_for(agents: Agent | Sequence[Agent], player: int) -> Agent:
    """The agent answering for ``player``: one agent for everyone, or one per seat."""
    if isinstance(agents, Sequence):
        if not 0 <= player < len(agents):
            raise EngineError(f"no agent for player {player} ({len(agents)} agents)")
        return agents[player]
    return agents


def play(
    state: GameState,
    agents: Agent | Sequence[Agent],
    *,
    max_answers: int | None = None,
    on_invalid: Callable[[InvalidAnswer], None] | None = None,
) -> int:
    """Answer decisions until the game is over, or ``max_answers`` answers were accepted.

    ``agents`` is one agent for every player, or one agent per seat (``agents[i]`` answers for
    player ``i``). Returns the number of answers accepted.

    A rejected answer raises ``InvalidAnswer``, unless ``on_invalid`` is given: then it is called
    with the error and the same agent is asked again, at most ``MAX_ATTEMPTS`` times per
    decision. The engine leaves the state unchanged after a rejected answer (design.md §3).
    """
    if max_answers is not None and max_answers < 0:
        raise ValueError(f"max_answers can't be negative: {max_answers}")
    accepted = 0
    while max_answers is None or accepted < max_answers:
        request = pending_decision(state)
        if request is None:
            break
        agent = agent_for(agents, request.player)
        for attempt in range(1, MAX_ATTEMPTS + 1):
            answer = agent.decide(view_for(state, request.player), request)
            try:
                submit(state, answer)
            except InvalidAnswer as error:
                if on_invalid is None or attempt == MAX_ATTEMPTS:
                    raise
                on_invalid(error)
            else:
                break
        accepted += 1
    return accepted
