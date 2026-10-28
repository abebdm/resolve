"""The caster: a fuzz seat that casts what it can (docs/decisions.md, 2026-10-28, "M2.11").

Random seats seldom cast the expensive or instant-speed spells: they pass, tap lands for nothing
and try spells they can't pay for. ``CasterAgent`` plays like a player who always uses their
mana, so the fuzz runs reach every kind of spell, countering included. It is meant to be wrapped
by the auto-payer (``AutoPayAgent(CasterAgent(seed))``), which answers the payment decisions.
Its policy:

- **Priority** (117.1): it plays a land if it may (305.1, a special action: 116.2a); otherwise it
  casts a spell offered that it hasn't tried yet in this *window* (117.1a, 601.2), picked at
  random; otherwise it passes (117.3d). It never activates a mana ability with priority: the
  auto-payer does that while paying (601.2g).
- **The window** is what the auto-payer's plan depends on: the turn number, phase and step, the
  objects on the stack, and the deciding player's untapped permanents and mana pool. A spell the
  auto-payer can't pay for is reversed (118.3, 733.1), which restores all of that, so the caster
  doesn't try it again until the window changes. It remembers only the current window.
- **Casting during a resolution** (608.2g): it casts one of the spells offered, at random,
  rather than declining.
- **X** (107.3a) and any other number without an upper bound: from the minimum to
  ``CASTER_UNBOUNDED_SPAN`` more, an amount a fuzz deck's mana can pay.
- **Everything else** (mulligans, modes, targets, colors outside a payment, ...): at random,
  like ``RandomAgent``.

It sees only the view and the request (rule 4). Its randomness comes from its own ``Rng``, so its
answers are a function of its seed and the views and requests it was shown, in order.
"""

from __future__ import annotations

from resolve.agents.random_agent import RandomAgent
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.request import DecisionAnswer, DecisionRequest
from resolve.decisions.spaces import (
    AnswerValue,
    CastSpellOption,
    ChooseOne,
    Option,
    PassOption,
    Pick,
    PlayLandOption,
)
from resolve.engine.view import PlayerView

# How far above its minimum the caster picks a number without an upper bound (X, 107.3a).
CASTER_UNBOUNDED_SPAN = 3

# The window: turn number, phase, step, the stack's objects, and the deciding player's untapped
# permanents and mana pool (module docstring).
Window = tuple[object, ...]


class CasterAgent:
    """Plays a land, then casts every spell it may, then passes (module docstring); reproducible
    from ``seed``."""

    def __init__(self, seed: int) -> None:
        self.random = RandomAgent(seed, unbounded_span=CASTER_UNBOUNDED_SPAN)
        self.window: Window | None = None
        self.tried: list[CastSpellOption] = []

    def decide(self, view: PlayerView, request: DecisionRequest) -> DecisionAnswer:
        """The caster's answer to ``request``."""
        return DecisionAnswer(request.id, request.player, self.answer(view, request))

    def answer(self, view: PlayerView, request: DecisionRequest) -> AnswerValue:
        """The answer value (module docstring)."""
        space = request.space
        if isinstance(space, ChooseOne):
            options = space.options
            if request.kind is DecisionKind.PRIORITY_ACTION:
                return self._priority(view, request, options)
            if request.kind is DecisionKind.CAST_DURING_RESOLUTION:
                casts = [i for i, o in enumerate(options) if isinstance(o, CastSpellOption)]
                if casts:
                    return Pick(self._one_of(casts))
        return self.random.random_value(space)

    def _priority(
        self, view: PlayerView, request: DecisionRequest, options: tuple[Option, ...]
    ) -> AnswerValue:
        lands = [i for i, option in enumerate(options) if isinstance(option, PlayLandOption)]
        if lands:
            return Pick(self._one_of(lands))
        window = _window(view, request)
        if window != self.window:
            self.window, self.tried = window, []
        casts = [
            i
            for i, option in enumerate(options)
            if isinstance(option, CastSpellOption) and option not in self.tried
        ]
        if casts:
            index = self._one_of(casts)
            option = options[index]
            assert isinstance(option, CastSpellOption)
            self.tried.append(option)
            return Pick(index)
        if PassOption() in options:
            return Pick(options.index(PassOption()))
        return self.random.random_value(request.space)

    def _one_of(self, indices: list[int]) -> int:
        return indices[self.random.rng.randbelow(len(indices))]


def _window(view: PlayerView, request: DecisionRequest) -> Window:
    """The priority window of ``request`` (module docstring)."""
    player = request.for_player
    turn = view.turn
    when = None if turn is None else (turn.number, turn.phase, turn.step)
    untapped = tuple(
        obj.id for obj in view.battlefield if obj.controller == player and not obj.tapped
    )
    pool = next(summary.mana_pool for summary in view.players if summary.id == player)
    return (when, tuple(obj.id for obj in view.stack), untapped, pool)
