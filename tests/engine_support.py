"""Test-only tasks and events for exercising the engine loop (design.md §5).

They live in an importable module (not a test file) so that states holding them can be pickled.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

from resolve.agents.random_agent import RandomAgent
from resolve.cards.primitives.abilities import ActivatedManaAbility
from resolve.cards.primitives.costs import TapSelfCost
from resolve.cards.primitives.effects import AddMana
from resolve.cards.registry import CardDefinition
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.request import DecisionAnswer, DecisionRequest
from resolve.decisions.spaces import AnswerValue, ChooseNumber, ChooseOne, Number, PassOption, Pick
from resolve.engine.loop import run
from resolve.engine.setup import initial_state
from resolve.engine.view import PlayerView
from resolve.errors import EngineError, InvalidAnswer, NotImplementedRule
from resolve.events.base import Event, append_log
from resolve.events.cards import CardDrawn, CardsPutOnBottom
from resolve.events.game import GameEnded
from resolve.events.mana import ManaAdded
from resolve.events.pipeline import ApplyEvents
from resolve.state.checkpoint import Checkpoint, restore_checkpoint, take_checkpoint
from resolve.state.config import GameConfig
from resolve.state.game import GameObject, GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import Mana, ManaType
from resolve.tasks import Done, NeedDecision, Push, Task, TaskResult
from tests.game_fixtures import decks


@dataclass(frozen=True, kw_only=True)
class Marker(Event):
    """An event that changes nothing; its label shows in the log where it ran.

    A marker ``secret_for`` some players shows everyone else ``public_label`` instead, if given
    (its redacted form), and nothing otherwise.
    """

    label: str
    secret_for: tuple[PlayerId, ...] | None = None
    public_label: str | None = None

    def apply(self, state: GameState) -> None:
        return None

    def visible_to(self, state: GameState) -> tuple[PlayerId, ...] | None:
        return self.secret_for

    def redacted(self) -> Event | None:
        if self.public_label is None:
            return None
        return replace(self, label=self.public_label, public_label=None)


@dataclass(frozen=True, kw_only=True)
class Counted(Event):
    """Proposed without an outcome; applied, it records how long the log was (``seen``)."""

    seen: int | None = None

    def apply(self, state: GameState) -> Event:
        return replace(self, seen=len(state.event_log))


def markers(state: GameState) -> list[str]:
    """The labels of the Marker events in the log, in order."""
    return [entry.record.label for entry in state.event_log if isinstance(entry.record, Marker)]


@dataclass(slots=True)
class Mark(Task):
    """Log a marker, then finish."""

    label: str

    def run(self, state: GameState) -> TaskResult:
        return Push((ApplyEvents((Marker(label=self.label, rules=("117.1",)),)),))


@dataclass(slots=True)
class Parent(Task):
    """Run two children, then continue itself (``Push((child, child, self))``)."""

    step: int = 0

    def run(self, state: GameState) -> TaskResult:
        if self.step == 0:
            self.step = 1
            return Push((Mark("child a"), Mark("child b"), self))
        return Push((Mark("parent continued"),))


@dataclass(slots=True)
class AskTwice(Task):
    """Ask ``player`` for two numbers in turn; only even numbers are legal (``check_answer``)."""

    player: PlayerId
    received: tuple[int, ...] = ()

    def run(self, state: GameState) -> TaskResult:
        return self._ask()

    def _ask(self) -> TaskResult:
        return NeedDecision(
            player=self.player,
            kind=DecisionKind.CHOOSE_X,
            space=ChooseNumber(0, 10),
            prompt=f"Choose number {len(self.received) + 1}.",
            rules=("107.3a",),
        )

    def check_answer(self, state: GameState, request: DecisionRequest, answer: AnswerValue) -> None:
        assert isinstance(answer, Number)
        if answer.value % 2:
            raise InvalidAnswer("the number must be even")

    def resume(self, state: GameState, request: DecisionRequest, answer: AnswerValue) -> TaskResult:
        assert isinstance(answer, Number)
        self.received += (answer.value,)
        if len(self.received) < 2:
            return self._ask()
        return Push((Mark(f"got {self.received}"),))


@dataclass(slots=True)
class EndGame(Task):
    """End the game with these winners (104.1)."""

    winners: tuple[PlayerId, ...]

    def run(self, state: GameState) -> TaskResult:
        return Push((ApplyEvents((GameEnded(winners=self.winners, rules=("104.2a",)),)),))


@dataclass(slots=True)
class Meddler(Task):
    """Breaks the rules by changing the task stack itself."""

    def run(self, state: GameState) -> TaskResult:
        state.tasks.append(Mark("sneaky"))
        return Done()


@dataclass(slots=True)
class Forever(Task):
    """Never finishes: replaces itself forever."""

    def run(self, state: GameState) -> TaskResult:
        return Push((Forever(),))


@dataclass(slots=True)
class AskNobody(Task):
    """Asks a player who doesn't exist."""

    def run(self, state: GameState) -> TaskResult:
        return NeedDecision(
            player=PlayerId(99),
            kind=DecisionKind.MAY,
            space=ChooseNumber(0, 1),
            prompt="?",
            rules=("117.1",),
        )


HOLD_PROMPT = "Hold."


@dataclass(slots=True)
class Hold(Task):
    """Sits at the bottom of a test's task stack and holds the game at a decision forever."""

    def run(self, state: GameState) -> TaskResult:
        return NeedDecision(
            player=PlayerId(0),
            kind=DecisionKind.MAY,
            space=ChooseNumber(0, 0),
            prompt=HOLD_PROMPT,
            rules=("117.1",),
        )

    def resume(self, state: GameState, request: DecisionRequest, answer: AnswerValue) -> TaskResult:
        return self.run(state)


def holding(state: GameState) -> bool:
    """Whether the test tasks have all finished and ``Hold`` is waiting."""
    return state.pending is not None and state.pending.prompt == HOLD_PROMPT


@dataclass(slots=True)
class LeaksALibraryCard(Task):
    """Logs a draw by player 0 that still names the library object for other players.

    ``how``: ``"redacted"`` (a redacted form that hides nothing), ``"public"`` (the whole draw
    shown to everyone) or ``"bottom"`` (a bottoming whose redacted form names the cards).
    Each is a design.md §9 leak the fuzz oracle must catch.
    """

    how: str = "redacted"

    def run(self, state: GameState) -> TaskResult:
        player = state.players[0].id
        drawn = CardDrawn(player=player, drawn_from=ObjectId(999), drawn=None, rules=("121.1",))
        bottomed = CardsPutOnBottom(
            player=player, cards=(ObjectId(999),), count=1, rules=("103.5",)
        )
        match self.how:
            case "redacted":
                append_log(state, drawn, (player,), drawn)
            case "public":
                append_log(state, drawn, None)
            case _:
                append_log(state, bottomed, (player,), bottomed)
        return Done()


# --- Impure tasks, for the purity checker's negative tests ------------------------------------


@dataclass(slots=True)
class HoldsValue(Task):
    """A task holding an arbitrary value, pure or not."""

    value: object = None

    def run(self, state: GameState) -> TaskResult:
        return Done()


@dataclass
class LooseTask(Task):
    """A task without slots, so it can grow attributes outside its fields."""

    run_count: int = 0
    extras: dict[str, object] = field(default_factory=dict[str, object])

    def run(self, state: GameState) -> TaskResult:
        return Done()


def running(*tasks: Task, players: int = 2, seed: int = 1) -> GameState:
    """A fresh game whose task stack holds ``tasks`` (``tasks[0]`` runs first), run to a pause.

    A ``Hold`` task sits beneath them, so once they have all finished the game waits there.
    """
    state = initial_state(GameConfig.standard(), decks(players), seed)
    state.tasks = [Hold(), *reversed(tasks)]
    run(state)
    return state


def holds_object(state: GameState) -> GameObject:
    """Some object of the game, for the "held by reference" test."""
    return next(iter(state.objects.values()))


def a_function() -> Callable[[], int]:
    """A function value (not pure data)."""
    return lambda: 1


# --- Broken tasks, for the fuzz harness's negative tests ---------------------------------------

_UNREPEATABLE_CALLS: list[int] = []


@dataclass(slots=True)
class Unrepeatable(Task):
    """Breaks determinism: what it logs depends on a module-level counter, not on the state."""

    def run(self, state: GameState) -> TaskResult:
        return NeedDecision(
            player=PlayerId(0),
            kind=DecisionKind.MAY,
            space=ChooseNumber(0, 0),
            prompt="Unrepeatable.",
            rules=("117.1",),
        )

    def resume(self, state: GameState, request: DecisionRequest, answer: AnswerValue) -> TaskResult:
        _UNREPEATABLE_CALLS.append(1)
        return Push((Mark(f"call {len(_UNREPEATABLE_CALLS)}"),))


@dataclass(slots=True)
class CheckThatChanges(Task):
    """Breaks the rule that ``check_answer`` changes nothing: it costs life, then rejects 1."""

    def run(self, state: GameState) -> TaskResult:
        return NeedDecision(
            player=PlayerId(0),
            kind=DecisionKind.MAY,
            space=ChooseNumber(0, 1),
            prompt="Pick 0.",
            rules=("117.1",),
        )

    def check_answer(self, state: GameState, request: DecisionRequest, answer: AnswerValue) -> None:
        state.players[0].life -= 1
        if answer == Number(1):
            raise InvalidAnswer("pick 0")

    def resume(self, state: GameState, request: DecisionRequest, answer: AnswerValue) -> TaskResult:
        return Done()


@dataclass(frozen=True)
class LaxSpace(ChooseNumber):
    """An answer space whose ``validate`` accepts anything (an engine bug)."""

    def validate(self, answer: AnswerValue) -> None:
        return None


@dataclass(slots=True)
class AsksLaxly(Task):
    """Asks with a ``LaxSpace``, so answers outside the space get through."""

    def run(self, state: GameState) -> TaskResult:
        return NeedDecision(
            player=PlayerId(0),
            kind=DecisionKind.CHOOSE_X,
            space=LaxSpace(0, 3),
            prompt="Choose.",
            rules=("107.3a",),
        )

    def resume(self, state: GameState, request: DecisionRequest, answer: AnswerValue) -> TaskResult:
        return Done()


@dataclass(slots=True)
class RejectsEverything(Task):
    """Asks a question no answer satisfies (an engine bug)."""

    def run(self, state: GameState) -> TaskResult:
        return NeedDecision(
            player=PlayerId(0),
            kind=DecisionKind.MAY,
            space=ChooseNumber(0, 1),
            prompt="Impossible.",
            rules=("117.1",),
        )

    def check_answer(self, state: GameState, request: DecisionRequest, answer: AnswerValue) -> None:
        raise InvalidAnswer("no answer is legal")


@dataclass(slots=True)
class CrashOnAnswer(Task):
    """Raises an ``EngineError`` once answered."""

    def run(self, state: GameState) -> TaskResult:
        return NeedDecision(
            player=PlayerId(1),
            kind=DecisionKind.MAY,
            space=ChooseNumber(0, 0),
            prompt="Crash.",
            rules=("117.1",),
        )

    def resume(self, state: GameState, request: DecisionRequest, answer: AnswerValue) -> TaskResult:
        raise EngineError("crashed")


@dataclass(slots=True)
class GapOnAnswer(Task):
    """Raises ``NotImplementedRule`` for ``rule`` once answered."""

    rule: str

    def run(self, state: GameState) -> TaskResult:
        return NeedDecision(
            player=PlayerId(0),
            kind=DecisionKind.MAY,
            space=ChooseNumber(0, 0),
            prompt="Gap.",
            rules=("117.1",),
        )

    def resume(self, state: GameState, request: DecisionRequest, answer: AnswerValue) -> TaskResult:
        raise NotImplementedRule(f"{self.rule}: a test gap")


@dataclass(slots=True)
class LossyPickle(Task):
    """Copies faithfully with ``deepcopy`` but loses ``value`` when pickled (a state bug)."""

    value: int = 0

    def __deepcopy__(self, memo: dict[int, object]) -> LossyPickle:
        return LossyPickle(self.value)

    def __reduce__(self) -> tuple[type[LossyPickle], tuple[()]]:
        return (LossyPickle, ())

    def run(self, state: GameState) -> TaskResult:
        return Done()


# --- Agents for long fuzz games ----------------------------------------------------------------


class PatientAgent:
    """A random agent that usually passes priority, so random games last many turns.

    With priority it passes, except one time in ``patience`` (drawn from its own ``Rng``), when
    it answers uniformly at random like ``RandomAgent``; every other decision is random.
    """

    def __init__(self, seed: int, patience: int = 32) -> None:
        self.random = RandomAgent(seed)
        self.patience = patience

    def decide(self, view: PlayerView, request: DecisionRequest) -> DecisionAnswer:
        """Pass priority, mostly; otherwise a random answer."""
        space = request.space
        if (
            request.kind is DecisionKind.PRIORITY_ACTION
            and isinstance(space, ChooseOne)
            and PassOption() in space.options
            and self.random.rng.randbelow(self.patience) != 0
        ):
            return DecisionAnswer(
                request.id, request.player, Pick(space.options.index(PassOption()))
            )
        return self.random.decide(view, request)


@dataclass(slots=True)
class ReversesAfterDrawing(Task):
    """Takes a checkpoint, draws a card for ``player`` (121.1, an action involving a library),
    then tries to reverse back to the checkpoint (733.1 forbids it)."""

    player: PlayerId
    checkpoint: Checkpoint | None = None

    def run(self, state: GameState) -> TaskResult:
        if self.checkpoint is None:
            self.checkpoint = take_checkpoint(state)
            return Push((ApplyEvents((CardDrawn(player=self.player, rules=("121.1",)),)), self))
        restore_checkpoint(state, self.checkpoint)
        return Done()


@dataclass(frozen=True)
class AddManaPerCardInHand(AddMana):
    """Test-only: "Add one [mana] for each card in your hand", so what it adds depends on the
    moment it is activated (like Lion's Eye Diamond's "discard your hand", M4)."""

    def events(self, state: GameState, source: ObjectId, player: PlayerId) -> tuple[Event, ...]:
        count = len(state.player(player).hand)
        if count == 0:
            return ()
        added = tuple(Mana(self.mana[0], source) for _ in range(count))
        return (ManaAdded(player=player, mana=added, rules=("106.3", "106.4")),)

    @property
    def text(self) -> str:
        return f"Add {self.mana[0].symbol} for each card in your hand."


HAND_BLOOM_RECORD: dict[str, Any] = {
    "object": "card",
    "oracle_id": "oid-test-hand-bloom",
    "name": "Test Hand Bloom",
    "layout": "normal",
    "mana_cost": "{2}",
    "cmc": 2.0,
    "type_line": "Artifact",
    "oracle_text": "{T}: Add {G} for each card in your hand.",
    "colors": [],
    "color_identity": [],
    "keywords": [],
}
HAND_BLOOM = CardDefinition(
    "Test Hand Bloom",
    (ActivatedManaAbility((TapSelfCost(),), AddManaPerCardInHand((ManaType.GREEN,))),),
)
