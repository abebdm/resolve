"""An agent that answers uniformly at random inside the answer space (design.md §14).

The fuzz harness plays games with it. Its randomness comes from its own ``Rng`` (the engine's
generator, ``resolve.state.rng``), seeded when it is created, so a fuzz game is a pure function
of the game seed and the agents' seeds and can be reproduced from them.

For each answer space it picks:

- ``ChooseOne``: each option with equal probability.
- ``ChooseSubset``: a size uniformly between the bounds, then each subset of that size with equal
  probability.
- ``ChooseOrder``: each permutation with equal probability.
- ``ChooseNumber``: each number in range with equal probability. A space without an upper bound
  is capped at ``minimum + unbounded_span``; a random agent can't usefully pick "any" number.
- ``Distribute``: each division of the total with equal probability (stars and bars).

Answers inside the space can still break a rule only the asking task checks (``check_answer``);
the driver then asks again (``play(..., on_invalid=...)``), and the agent draws a fresh answer.
"""

from __future__ import annotations

from resolve.decisions.request import DecisionAnswer, DecisionRequest
from resolve.decisions.spaces import (
    Amounts,
    AnswerSpace,
    AnswerValue,
    ChooseNumber,
    ChooseOne,
    ChooseOrder,
    ChooseSubset,
    Distribute,
    Number,
    Order,
    Pick,
    PickMany,
)
from resolve.engine.view import PlayerView
from resolve.errors import EngineError
from resolve.state.rng import Rng

DEFAULT_UNBOUNDED_SPAN = 20


class RandomAgent:
    """Answers every decision uniformly at random; reproducible from ``seed``."""

    def __init__(self, seed: int, *, unbounded_span: int = DEFAULT_UNBOUNDED_SPAN) -> None:
        if unbounded_span < 0:
            raise ValueError(f"unbounded_span can't be negative: {unbounded_span}")
        self.rng = Rng.from_seed(seed)
        self.unbounded_span = unbounded_span

    def decide(self, view: PlayerView, request: DecisionRequest) -> DecisionAnswer:
        """A random answer inside ``request.space``."""
        return DecisionAnswer(request.id, request.player, self.random_value(request.space))

    def random_value(self, space: AnswerSpace) -> AnswerValue:
        """A random answer value inside ``space``."""
        rng = self.rng
        match space:
            case ChooseOne(options=options):
                return Pick(rng.randbelow(len(options)))
            case ChooseSubset(options=options, minimum=minimum, maximum=maximum):
                size = minimum + rng.randbelow(maximum - minimum + 1)
                return PickMany(tuple(sorted(self._sample(len(options), size))))
            case ChooseOrder(options=options):
                permutation = list(range(len(options)))
                rng.shuffle(permutation)
                return Order(tuple(permutation))
            case ChooseNumber(minimum=minimum, maximum=maximum):
                top = minimum + self.unbounded_span if maximum is None else maximum
                return Number(minimum + rng.randbelow(top - minimum + 1))
            case Distribute(recipients=recipients, total=total, minimum_each=minimum_each):
                return Amounts(self._division(len(recipients), total, minimum_each))
            case _:
                raise EngineError(f"RandomAgent can't answer a {type(space).__name__}")

    def _sample(self, population: int, size: int) -> list[int]:
        """``size`` distinct numbers from ``range(population)``, each set equally likely."""
        items = list(range(population))
        # A partial Fisher-Yates shuffle: the first ``size`` items are a uniform sample.
        for i in range(size):
            j = i + self.rng.randbelow(population - i)
            items[i], items[j] = items[j], items[i]
        return items[:size]

    def _division(self, recipients: int, total: int, minimum_each: int) -> tuple[int, ...]:
        """A uniformly random way to divide ``total``, at least ``minimum_each`` to each."""
        spare = total - recipients * minimum_each
        # Stars and bars: choosing where the recipients - 1 bars go among spare + recipients - 1
        # places picks each division of ``spare`` with equal probability.
        bars = sorted(self._sample(spare + recipients - 1, recipients - 1))
        bounds = [-1, *bars, spare + recipients - 1]
        return tuple(minimum_each + bounds[i + 1] - bounds[i] - 1 for i in range(recipients))
