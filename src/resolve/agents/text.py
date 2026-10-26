"""A minimal text interface: render a ``PlayerView`` and read answers from a terminal.

``tools/play_cli.py`` plays games with it; it is also handy for printing a view while debugging.
It sees only what an agent sees (the deciding player's ``PlayerView`` and the request), so a
hot-seat game shows each player only their own view (design.md §9).

Answers are typed as option indices, starting at 0, matching the engine's ``Pick`` indices:

| Space          | Type                                    | Example |
|----------------|-----------------------------------------|---------|
| ``ChooseOne``    | one index                               | ``2``     |
| ``ChooseSubset`` | indices in any order, ``-`` for none    | ``3 0``   |
| ``ChooseOrder``  | every index, in the chosen order        | ``1 0 2`` |
| ``ChooseNumber`` | a number                                | ``4``     |
| ``Distribute``   | one amount per recipient, in order      | ``2 1``   |
| ``ChooseCounts`` | one amount per option, in order         | ``2 0``   |

Besides answers, ``view`` reprints the view, ``log`` prints the whole visible log, ``help``
explains the syntax, and ``quit`` (or the end of input) raises ``QuitGame``.
"""

from __future__ import annotations

import dataclasses
import sys
from typing import TextIO

from resolve.decisions.request import DecisionAnswer, DecisionRequest
from resolve.decisions.spaces import (
    ActivateAbilityOption,
    Amounts,
    AnswerSpace,
    AnswerValue,
    CastSpellOption,
    ChooseCounts,
    ChooseNumber,
    ChooseOne,
    ChooseOrder,
    ChooseSubset,
    ColorOption,
    Distribute,
    ManaActivationOption,
    ManaOption,
    ModesOption,
    NamedOption,
    Number,
    ObjectOption,
    Option,
    Order,
    PassOption,
    Pick,
    PickMany,
    PlayerOption,
    PlayLandOption,
)
from resolve.engine.view import ObjectView, PaymentView, PlayerView
from resolve.events.base import AnswerRecord, LogEntry
from resolve.state.ids import ObjectId
from resolve.state.mana import ForAbility, ForSpell, describe_mana
from resolve.state.spell import Target, TargetObject, TargetPlayer, describe_variant
from resolve.state.zones import ZoneKind

# How many of the newest log entries ``render_view`` shows.
RECENT_LOG = 8


class QuitGame(Exception):
    """The person at the terminal stopped the game."""


class AnswerSyntaxError(ValueError):
    """Typed text that isn't an answer of the right shape (the engine never sees it)."""


def _objects(view: PlayerView) -> dict[ObjectId, ObjectView]:
    found: dict[ObjectId, ObjectView] = {}
    for summary in view.players:
        for obj in summary.hand + summary.graveyard:
            found[obj.id] = obj
    for obj in view.battlefield + view.stack + view.exile + view.command:
        found[obj.id] = obj
    return found


def describe_object(obj: ObjectView) -> str:
    """``"Llanowar Elves #12"``, ``"Forest #3 (tapped)"``, or ``"hidden card #12"`` when its
    identity is hidden."""
    marks = (" (tapped)" if obj.tapped else "") + (f" ({obj.damage} damage)" if obj.damage else "")
    return f"{obj.name or 'hidden card'} #{obj.id}" + marks


def describe_option(option: Option, view: PlayerView) -> str:
    """An option in words, using only what ``view`` shows."""
    match option:
        case PlayerOption(player=player):
            return f"player {player}" + (" (you)" if player == view.viewer else "")
        case ObjectOption(object=obj):
            return _named(view, obj)
        case NamedOption(name=name):
            return name
        case PassOption():
            return "pass priority"
        case PlayLandOption(object=obj):
            return f"play {_named(view, obj)}"
        case CastSpellOption(object=obj, variant=variant, permission=permission):
            how = describe_variant(variant)
            zone = permission.zone
            named = "command zone" if zone is ZoneKind.COMMAND else zone.value
            where = "" if zone is ZoneKind.HAND else f" from the {named}"
            return f"cast {_named(view, obj)}" + (f" ({how})" if how else "") + where
        case ActivateAbilityOption(object=obj, ability=index):
            return f"activate ability {index} of {_named(view, obj)}"
        case ManaOption(mana=mana):
            source = "" if mana.source is None else f" from {_named(view, mana.source)}"
            restriction = "" if mana.restriction is None else f" ({mana.restriction.text})"
            return mana.type.symbol + source + restriction
        case ManaActivationOption(object=obj, ability=index):
            return f"reverse ability {index} of {_named(view, obj)}"
        case ModesOption(modes=modes):
            numbers = [str(mode + 1) for mode in modes]  # 700.2: as the bullets are printed
            listed = (
                numbers[0] if len(numbers) == 1 else ", ".join(numbers[:-1]) + " and " + numbers[-1]
            )
            return ("mode " if len(numbers) == 1 else "modes ") + listed
        case ColorOption(color=color):
            return color.name.lower()


def _named(view: PlayerView, obj: ObjectId) -> str:
    known = _objects(view).get(obj)
    return describe_object(known) if known is not None else f"object #{obj}"


def _payment(view: PlayerView, payment: PaymentView) -> str:
    """``"{1}{G} for Grizzly Bears #4 (player 0)"`` (601.2g-h, 602.2b)."""
    match payment.purpose:
        case ForSpell(spell=spell):
            paid_for = _named(view, spell)
        case ForAbility(source=source, ability=ability):
            paid_for = f"ability {ability} of {_named(view, source)}"
    return f"{payment.cost.text} for {paid_for} (player {payment.payer})"


def describe_turn(view: PlayerView) -> str | None:
    """``"Turn 3, player 1's turn: draw step; player 0 has priority."``, or ``None``."""
    turn = view.turn
    if turn is None:
        return None
    where = f"{turn.step.value} step" if turn.step is not None else f"{turn.phase.value} phase"
    holder = (
        "nobody has priority" if turn.priority is None else (f"player {turn.priority} has priority")
    )
    return f"Turn {turn.number}, player {turn.active_player}'s turn: {where}; {holder}."


def _zone_line(label: str, objects: tuple[ObjectView, ...]) -> str:
    shown = ", ".join(describe_object(obj) for obj in objects) if objects else "(empty)"
    return f"  {label}: {shown}"


def _stack_line(view: PlayerView) -> str:
    """The stack, each spell with its targets (601.2c): ``Test Shock #5 (targeting player 1)``."""
    shown: list[str] = []
    for obj in view.stack:
        text = describe_object(obj)
        targets = () if obj.spell is None else obj.spell.targets
        chosen = [_target(view, target) for instance in targets for target in instance]
        shown.append(text + (f" (targeting {', '.join(chosen)})" if chosen else ""))
    return f"  Stack (top last): {', '.join(shown) if shown else '(empty)'}"


def _target(view: PlayerView, target: Target) -> str:
    match target:
        case TargetObject(object=obj):
            return _named(view, obj)
        case TargetPlayer(player=player):
            return f"player {player}" + (" (you)" if player == view.viewer else "")


def render_log_entry(entry: LogEntry) -> str:
    """One log entry: the event or answer with its fields and its CR rules."""
    record = entry.record
    if isinstance(record, AnswerRecord):
        text = f"player {record.player} answered {record.kind.value}: {record.value}"
    else:
        fields = ", ".join(
            f"{field.name}={getattr(record, field.name)!r}"
            for field in dataclasses.fields(record)
            if field.name != "rules"
        )
        text = f"{type(record).__name__}({fields})"
    return f"[{entry.index}] {text}  ({', '.join(record.rules)})"


def render_view(view: PlayerView, *, recent_log: int = RECENT_LOG) -> str:
    """The view as text: each player and their zones, the shared zones, and the recent log."""
    lines = [f"=== Player {view.viewer}'s view ==="]
    for summary in view.players:
        marks = [" (you)" if summary.id == view.viewer else ""]
        if summary.id == view.starting_player:
            marks.append(" (starting player)")
        if summary.lost:
            marks.append(" (lost)")
        if summary.left_game:
            marks.append(" (left the game)")
        pool = f", mana {describe_mana(summary.mana_pool)}" if summary.mana_pool else ""
        lines.append(
            f"Player {summary.id}{''.join(marks)}: life {summary.life}, "
            f"library {summary.library_size}{pool}"
        )
        lines.append(_zone_line("hand", summary.hand))
        lines.append(_zone_line("graveyard (top last)", summary.graveyard))
    lines.append(_zone_line("Battlefield", view.battlefield))
    lines.append(_stack_line(view))
    lines.append(_zone_line("Exile", view.exile))
    lines.append(_zone_line("Command zone", view.command))
    turn = describe_turn(view)
    if turn is not None:
        lines.append(turn)
    if view.payments:
        lines.append("Paying: " + "; ".join(_payment(view, p) for p in view.payments) + ".")
    if view.result is not None:
        if view.result.is_draw:
            lines.append("Game over: a draw.")
        else:
            winners = ", ".join(f"player {p}" for p in view.result.winners)
            lines.append(f"Game over: won by {winners}.")
    elif view.waiting_for is not None:
        waiting = view.waiting_for
        lines.append(f"Waiting for player {waiting.player} ({waiting.kind.value}).")
    if recent_log and view.log:
        lines.append("Recent log:")
        lines.extend(f"  {render_log_entry(entry)}" for entry in view.log[-recent_log:])
    return "\n".join(lines)


def _answer_hint(space: AnswerSpace) -> str:
    match space:
        case ChooseOne():
            return "Type one option number."
        case ChooseSubset(minimum=minimum, maximum=maximum):
            return f"Type {minimum} to {maximum} option numbers ('-' for none)."
        case ChooseOrder():
            return "Type every option number, in the order you choose."
        case ChooseNumber(minimum=minimum, maximum=maximum):
            upper = "" if maximum is None else f" to {maximum}"
            return f"Type a number from {minimum}{upper}."
        case Distribute(total=total, minimum_each=minimum_each):
            return (
                f"Type one amount per recipient, at least {minimum_each} each, "
                f"adding up to {total}."
            )
        case ChooseCounts(maxima=maxima, total=total):
            return (
                f"Type one amount per option (at most {', '.join(map(str, maxima))}), "
                f"adding up to {total}."
            )
        case _:
            return "This kind of answer can't be typed yet."


def render_request(request: DecisionRequest, view: PlayerView) -> str:
    """The question: who decides, what, under which rules, the options and how to answer."""
    rules = ", ".join(request.rules)
    lines = [f"Player {request.player}: {request.prompt} ({request.kind.value}; CR {rules})"]
    space = request.space
    options: tuple[Option, ...] = ()
    if isinstance(space, ChooseOne | ChooseSubset | ChooseOrder | ChooseCounts):
        options = space.options
    elif isinstance(space, Distribute):
        options = space.recipients
    lines.extend(
        f"  {index}: {describe_option(option, view)}" for index, option in enumerate(options)
    )
    lines.append(_answer_hint(space))
    return "\n".join(lines)


def _numbers(text: str) -> tuple[int, ...]:
    try:
        return tuple(int(word) for word in text.replace(",", " ").split())
    except ValueError:
        raise AnswerSyntaxError(f"not a list of whole numbers: {text!r}") from None


def parse_answer(space: AnswerSpace, text: str) -> AnswerValue:
    """The answer value typed as ``text``; ``AnswerSyntaxError`` if it has the wrong shape.

    Only the shape is checked here; whether the answer is legal is the engine's job.
    """
    text = text.strip()
    if not text:
        raise AnswerSyntaxError("type an answer")
    match space:
        case ChooseOne() | ChooseNumber():
            numbers = _numbers(text)
            if len(numbers) != 1:
                raise AnswerSyntaxError("type exactly one number")
            return Pick(numbers[0]) if isinstance(space, ChooseOne) else Number(numbers[0])
        case ChooseSubset():
            return PickMany(() if text == "-" else tuple(sorted(_numbers(text))))
        case ChooseOrder():
            return Order(_numbers(text))
        case Distribute() | ChooseCounts():
            return Amounts(_numbers(text))
        case _:
            raise AnswerSyntaxError(f"a {type(space).__name__} can't be typed yet")


HELP = """\
Answer with option numbers (from 0) or numbers:
  one option: 2        a subset: 3 0 (or - for none)    an order: 1 0 2
  a number: 4          amounts per recipient or option: 2 1
Commands: view (show the game again), log (the whole log), help, quit."""


class TextAgent:
    """Asks a person at a terminal: prints the view and the question, reads the answer."""

    def __init__(
        self, input: TextIO | None = None, output: TextIO | None = None, *, show_view: bool = True
    ) -> None:
        self.input = sys.stdin if input is None else input
        self.output = sys.stdout if output is None else output
        self.show_view = show_view

    def say(self, text: str) -> None:
        """Print a line to the person."""
        print(text, file=self.output, flush=True)

    def decide(self, view: PlayerView, request: DecisionRequest) -> DecisionAnswer:
        """Show the question and read answers until one has the right shape."""
        if self.show_view:
            self.say(render_view(view))
        self.say(render_request(request, view))
        while True:
            self.output.write("> ")
            self.output.flush()
            line = self.input.readline()
            if not line:
                raise QuitGame("end of input")
            command = line.strip().lower()
            if command in ("quit", "q", "exit"):
                raise QuitGame("quit")
            if command == "view":
                self.say(render_view(view))
                self.say(render_request(request, view))
                continue
            if command == "log":
                self.say("\n".join(render_log_entry(entry) for entry in view.log) or "(no log)")
                continue
            if command in ("help", "?"):
                self.say(HELP)
                continue
            try:
                value = parse_answer(request.space, line)
            except AnswerSyntaxError as error:
                self.say(f"Not an answer: {error}. Type 'help' for the syntax.")
                continue
            return DecisionAnswer(request.id, request.player, value)
