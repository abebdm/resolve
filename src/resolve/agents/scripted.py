"""An agent that answers from a fixed script: for tests and for replays (design.md §12, §14).

A script is a sequence of steps, used one per decision, in order, whichever player is deciding.
Each step either gives the answer value outright (``Step``) or names the options to choose
(``Choose``), which is resolved against the request's answer space so a test doesn't depend on
the order the options are listed in. A step may also say which player and which kind of decision
it expects; a mismatch raises ``ScriptError``, so a test notices when the game asks something it
didn't expect.

A replay is a script: ``ScriptedAgent.from_log`` turns the answers recorded in an event log into
steps that expect the same players and kinds. Playing them from the same config, decks and seed
reproduces the game (design.md §12).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from resolve.decisions.kinds import DecisionKind
from resolve.decisions.request import DecisionAnswer, DecisionRequest
from resolve.decisions.spaces import (
    AnswerSpace,
    AnswerValue,
    ChooseOne,
    ChooseOrder,
    ChooseSubset,
    Option,
    Order,
    Pick,
    PickMany,
)
from resolve.engine.view import PlayerView
from resolve.events.base import AnswerRecord, LogEntry
from resolve.state.ids import PlayerId


class ScriptError(AssertionError):
    """The game asked something the script didn't expect, or the script ran out."""


@dataclass(frozen=True)
class Step:
    """Answer the next decision with ``value``, optionally checking who decides and what."""

    value: AnswerValue
    player: PlayerId | None = None
    kind: DecisionKind | None = None


@dataclass(frozen=True)
class Choose:
    """Answer the next decision by naming options rather than indices.

    - ``ChooseOne``: name exactly one option.
    - ``ChooseSubset``: name the chosen options, in any order.
    - ``ChooseOrder``: name every option, in the chosen order.
    """

    options: tuple[Option, ...]
    player: PlayerId | None = None
    kind: DecisionKind | None = None

    def resolve(self, space: AnswerSpace) -> AnswerValue:
        """The answer value that chooses these options in ``space``."""
        match space:
            case ChooseOne(options=listed):
                if len(self.options) != 1:
                    raise ScriptError(f"choose one option, not {len(self.options)}")
                return Pick(_index(listed, self.options[0]))
            case ChooseSubset(options=listed):
                indices = sorted(_index(listed, option) for option in self.options)
                if len(set(indices)) != len(indices):
                    raise ScriptError(f"an option is named twice: {self.options}")
                return PickMany(tuple(indices))
            case ChooseOrder(options=listed):
                return Order(tuple(_index(listed, option) for option in self.options))
            case _:
                raise ScriptError(f"options can't be chosen in a {type(space).__name__}")


def _index(listed: tuple[Option, ...], option: Option) -> int:
    matches = [index for index, candidate in enumerate(listed) if candidate == option]
    if len(matches) != 1:
        found = "isn't offered" if not matches else "is offered more than once"
        raise ScriptError(f"{option} {found}; the options are {listed}")
    return matches[0]


def choose(
    *options: Option, player: PlayerId | None = None, kind: DecisionKind | None = None
) -> Choose:
    """A ``Choose`` step naming ``options``: ``choose(PlayerOption(PlayerId(1)))``."""
    return Choose(options, player, kind)


ScriptStep = Step | Choose


class ScriptedAgent:
    """Answers decisions from ``steps``, one per decision, in order."""

    def __init__(self, steps: Iterable[ScriptStep]) -> None:
        self.steps: list[ScriptStep] = list(steps)
        self.used = 0

    @classmethod
    def from_log(cls, log: Iterable[LogEntry]) -> ScriptedAgent:
        """A script replaying every answer recorded in ``log``, in order (design.md §12)."""
        return cls(
            Step(entry.record.value, entry.record.player, entry.record.kind)
            for entry in log
            if isinstance(entry.record, AnswerRecord)
        )

    @property
    def remaining(self) -> int:
        """How many steps haven't been used yet."""
        return len(self.steps) - self.used

    def decide(self, view: PlayerView, request: DecisionRequest) -> DecisionAnswer:
        """The next step's answer; ``ScriptError`` if it doesn't fit the request."""
        if self.remaining == 0:
            raise ScriptError(
                f"the script ran out after {self.used} steps; the game asks player "
                f"{request.player} for {request.kind.value}: {request.prompt}"
            )
        step = self.steps[self.used]
        number = self.used + 1
        if step.player is not None and step.player != request.player:
            raise ScriptError(
                f"step {number} expects player {step.player}, but player {request.player} "
                f"is deciding {request.kind.value}"
            )
        if step.kind is not None and step.kind is not request.kind:
            raise ScriptError(
                f"step {number} expects {step.kind.value}, but the game asks for "
                f"{request.kind.value}: {request.prompt}"
            )
        value = step.value if isinstance(step, Step) else step.resolve(request.space)
        self.used += 1
        return DecisionAnswer(request.id, request.player, value)

    def check_finished(self) -> None:
        """Raise ``ScriptError`` if some steps were never used."""
        if self.remaining:
            raise ScriptError(f"{self.remaining} of {len(self.steps)} script steps were unused")
